"""HTTP API on top of the in-memory Keitaro: the creator and the editor flows."""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db import Base
from tests.fake_keitaro import SOURCE_PARAMETERS


def shares(stream: dict) -> dict[int, int]:
    return {o["offer_id"]: o["share"] for o in stream["offers"] if o["state"] == "active"}


def offer_stream(campaign: dict) -> dict:
    return next(s for s in campaign["streams"] if s["editable"])


# Creator


def test_create_campaign_sends_campaign_and_two_streams(api, fake):
    r = api.post("/api/campaigns", json={"name": "TG test", "geo": "mx, au", "offer_id": 18813})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["countries"] == ["MX", "AU"]
    assert created["admin_url"] == f"https://kt.test/admin/#!/campaigns/{created['id']}"

    posts = fake.calls("POST")
    assert [p[1] for p in posts] == ["/campaigns", "/streams", "/streams"]
    campaign_body, geo_body, offer_body = (p[2] for p in posts)
    assert campaign_body["group_id"] == 4970
    assert campaign_body["traffic_source_id"] == 473
    assert campaign_body["domain_id"] == 4622
    assert campaign_body["cost_auto"] is True
    # Copied from the traffic source, as the admin UI does.
    assert campaign_body["parameters"] == SOURCE_PARAMETERS
    assert geo_body["campaign_id"] == created["id"]
    assert geo_body["filters"][0]["payload"] == ["MX", "AU"]
    assert geo_body["action_payload"] == "https://google.com"
    assert offer_body["offers"] == [{"offer_id": 18813, "share": 100, "state": "active"}]

    campaign = api.get(f"/api/campaigns/{created['id']}").json()
    assert [s["name"] for s in campaign["streams"]] == ["Flow 2", "Flow 1"]
    assert shares(offer_stream(campaign)) == {18813: 100}
    assert campaign["created_here"] is True


def test_create_campaign_validates_input(api, fake):
    bad_geo = api.post("/api/campaigns", json={"name": "x", "geo": "XX", "offer_id": 18813})
    assert bad_geo.status_code == 400
    assert "XX" in bad_geo.json()["detail"]
    no_offer = api.post("/api/campaigns", json={"name": "x", "geo": "MX", "offer_id": 1})
    assert no_offer.status_code == 400
    disabled = api.post("/api/campaigns", json={"name": "x", "geo": "MX", "offer_id": 500})
    assert disabled.status_code == 400
    assert fake.calls("POST") == []


def test_create_campaign_rolls_back_when_stream_fails(api, fake):
    fake.fail_stream_create = True
    r = api.post("/api/campaigns", json={"name": "x", "geo": "MX", "offer_id": 18813})
    assert r.status_code == 502
    [(cid, campaign)] = fake.campaigns.items()
    assert campaign["state"] == "deleted"
    assert ("DELETE", f"/campaigns/{cid}", None) in fake.requests


def test_offer_search(api):
    found = api.get("/api/offers", params={"q": "miaflow"}).json()
    assert {o["id"] for o in found} == {3717, 3749}
    assert [o["id"] for o in api.get("/api/offers", params={"q": "1881"}).json()] == [18813]
    # Disabled offers are not offered.
    assert 500 not in {o["id"] for o in api.get("/api/offers").json()}


def test_meta(api):
    meta = api.get("/api/meta").json()
    assert meta["group"] == "FORTESTS"
    assert meta["traffic_source"] == "FORTESTS"


# Editor: the reference video, step by step


def test_editor_replays_reference_video(api, fake):
    cid, sid = fake.add_campaign("campaign 2", [(3749, 33), (3717, 33), (13972, 34)])
    base = f"/api/streams/{sid}"
    stream = offer_stream(api.get(f"/api/campaigns/{cid}").json())
    assert shares(stream) == {3749: 33, 3717: 33, 13972: 34}
    assert stream["dirty"] is False

    # Add a fourth offer: a draft with 25% each, nothing sent yet.
    stream = api.post(f"{base}/offers", json={"offer_id": 18813}).json()
    assert shares(stream) == {3749: 25, 3717: 25, 13972: 25, 18813: 25}
    assert stream["dirty"] is True
    assert fake.calls("PUT") == []

    # Push: Keitaro gets the full list of offers.
    stream = api.post(f"{base}/push").json()
    assert stream["dirty"] is False
    assert fake.calls("PUT")[-1] == (
        "PUT",
        f"/streams/{sid}",
        {
            "offers": [
                {"offer_id": o, "share": 25, "state": "active"} for o in (3749, 3717, 13972, 18813)
            ]
        },
    )

    # Remove one: it stays in the list as removed, the last offer takes the extra 1%.
    stream = api.post(f"{base}/offers/3717/remove").json()
    assert shares(stream) == {3749: 33, 13972: 33, 18813: 34}
    removed = [o for o in stream["offers"] if o["state"] == "removed"]
    assert [(o["offer_id"], o["share"]) for o in removed] == [(3717, 0)]
    stream = api.post(f"{base}/push").json()
    assert {o["offer_id"]: o["share"] for o in fake.streams[sid]["offers"]} == {
        3749: 33,
        13972: 33,
        18813: 34,
    }

    # Bring it back: 25% each again.
    stream = api.post(f"{base}/offers/3717/restore").json()
    assert shares(stream) == {3749: 25, 13972: 25, 18813: 25, 3717: 25}
    api.post(f"{base}/push")

    # Someone removes two offers right in Keitaro; fetch shows them as removed.
    fake.set_offers(sid, [(18813, 25), (3717, 25)])
    stream = offer_stream(api.post(f"/api/campaigns/{cid}/sync").json())
    assert shares(stream) == {18813: 25, 3717: 25}
    assert stream["total"] == 50
    assert {o["offer_id"] for o in stream["offers"] if o["state"] == "removed"} == {3749, 13972}

    # Pin 3717 at 25% and bring 3749 back: 3749 (last) 38, 18813 37, 3717 stays 25.
    stream = api.post(f"{base}/offers/3717/pin", json={"pinned": True}).json()
    assert stream["dirty"] is False
    stream = api.post(f"{base}/offers/3749/restore").json()
    assert shares(stream) == {18813: 37, 3717: 25, 3749: 38}
    # Display order: by share, largest first, removed at the bottom.
    assert [o["offer_id"] for o in stream["offers"]] == [3749, 18813, 3717, 13972]
    api.post(f"{base}/push")
    assert {o["offer_id"]: o["share"] for o in fake.streams[sid]["offers"]} == {
        18813: 37,
        3717: 25,
        3749: 38,
    }


def test_cancel_returns_to_keitaro_state(api, fake):
    cid, sid = fake.add_campaign("c", [(3749, 50), (3717, 50)])
    api.get(f"/api/campaigns/{cid}")
    base = f"/api/streams/{sid}"
    api.post(f"{base}/offers", json={"offer_id": 18813})
    api.post(f"{base}/offers/3749/remove")
    stream = api.post(f"{base}/cancel").json()
    assert stream["dirty"] is False
    assert shares(stream) == {3749: 50, 3717: 50}
    # The offer added only in the draft is gone completely.
    assert {o["offer_id"] for o in stream["offers"]} == {3749, 3717}


def test_manual_share_pins_offer(api, fake):
    cid, sid = fake.add_campaign("c", [(3749, 34), (3717, 33), (13972, 33)])
    api.get(f"/api/campaigns/{cid}")
    stream = api.post(f"/api/streams/{sid}/offers/3749/share", json={"share": 60}).json()
    assert shares(stream) == {3749: 60, 3717: 20, 13972: 20}
    assert next(o for o in stream["offers"] if o["offer_id"] == 3749)["pinned"] is True


def test_push_rejects_wrong_total_and_foreign_changes(api, fake):
    cid, sid = fake.add_campaign("c", [(3749, 30), (3717, 30)])
    api.get(f"/api/campaigns/{cid}")
    base = f"/api/streams/{sid}"
    # Keitaro has 60% in total: pushing as is is refused, recount fixes it.
    api.post(f"{base}/offers/3749/pin", json={"pinned": False})
    r = api.post(f"{base}/push")
    assert r.status_code == 400
    assert "60" in r.json()["detail"]
    stream = api.post(f"{base}/recount").json()
    assert shares(stream) == {3749: 50, 3717: 50}

    # The stream changed in Keitaro after our fetch: do not overwrite it.
    fake.set_offers(sid, [(3749, 100)])
    r = api.post(f"{base}/push")
    assert r.status_code == 409
    assert fake.calls("PUT") == []


def test_editor_errors(api, fake):
    cid, sid = fake.add_campaign("c", [(3749, 100)])
    campaign = api.get(f"/api/campaigns/{cid}").json()
    redirect_stream = next(s for s in campaign["streams"] if not s["editable"])
    base = f"/api/streams/{sid}"
    assert api.post(f"{base}/offers", json={"offer_id": 3749}).status_code == 400
    assert api.post(f"{base}/offers", json={"offer_id": 424242}).status_code == 400
    assert api.post(f"{base}/offers/3717/remove").status_code == 404
    assert (
        api.post(
            f"/api/streams/{redirect_stream['id']}/offers", json={"offer_id": 3717}
        ).status_code
        == 400
    )
    assert api.get("/api/campaigns/999999").status_code == 404
    # Removing the only offer leaves nothing to push.
    api.post(f"{base}/offers/3749/remove")
    assert api.post(f"{base}/push").status_code == 400


def test_campaign_list_marks_campaigns_created_here(api, fake):
    fake.add_campaign("foreign", [(3749, 100)])
    mine = api.post("/api/campaigns", json={"name": "TG mine", "geo": "MX", "offer_id": 18813})
    items = api.get("/api/campaigns").json()
    assert {i["name"]: i["created_here"] for i in items} == {"foreign": False, "TG mine": True}
    assert [i["id"] for i in api.get("/api/campaigns", params={"q": "tg"}).json()] == [
        mine.json()["id"]
    ]


# Migrations


def test_alembic_migrations_match_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
    for name, table in Base.metadata.tables.items():
        columns = {c["name"] for c in inspect(engine).get_columns(name)}
        assert columns == set(table.columns.keys()), name
    command.downgrade(cfg, "base")
    engine.dispose()


# Regressions found in review


def test_remove_and_bring_back_in_one_draft_changes_nothing(api, fake):
    cid, sid = fake.add_campaign("c", [(3749, 33), (3717, 33), (13972, 34)])
    api.get(f"/api/campaigns/{cid}")
    base = f"/api/streams/{sid}"
    api.post(f"{base}/offers/3749/remove")
    stream = api.post(f"{base}/offers/3749/restore").json()
    # Back at its Keitaro place, so the extra 1% stays with the last offer.
    assert shares(stream) == {3749: 33, 3717: 33, 13972: 34}
    assert stream["dirty"] is False


def test_cancel_restores_keitaro_order(api, fake):
    cid, sid = fake.add_campaign("c", [(3749, 33), (3717, 33), (13972, 34)])
    api.get(f"/api/campaigns/{cid}")
    base = f"/api/streams/{sid}"
    api.post(f"{base}/offers/3749/remove")
    api.post(f"{base}/offers", json={"offer_id": 18813})
    api.post(f"{base}/cancel")
    # Add and remove the same offer: a net-zero edit leaves the Keitaro state.
    api.post(f"{base}/offers", json={"offer_id": 18813})
    stream = api.post(f"{base}/offers/18813/remove").json()
    assert shares(stream) == {3749: 33, 3717: 33, 13972: 34}
    assert stream["dirty"] is False


def test_offer_re_added_in_keitaro_goes_to_the_end(api, fake):
    cid, sid = fake.add_campaign("c", [(3749, 50), (3717, 50)])
    api.get(f"/api/campaigns/{cid}")
    fake.set_offers(sid, [(3717, 100)])
    api.post(f"/api/campaigns/{cid}/sync")
    fake.set_offers(sid, [(3717, 50), (3749, 50)])  # 3749 re-added: new link id, last
    api.post(f"/api/campaigns/{cid}/sync")
    stream = api.post(f"/api/streams/{sid}/offers", json={"offer_id": 13972}).json()
    # 3 offers, the extra 1% goes to the last added: 13972, after 3749.
    assert shares(stream) == {3717: 33, 3749: 33, 13972: 34}
    api.post(f"/api/streams/{sid}/offers/13972/remove")
    stream = api.post(f"/api/streams/{sid}/offers", json={"offer_id": 18813}).json()
    assert shares(stream)[18813] == 34


def test_disabled_offer_is_kept_switched_off(api, fake):
    cid, sid = fake.add_campaign("c", [(3749, 50), (3717, 50)])
    fake.set_offers(sid, [(3749, 50), (3717, 50), (13972, 10, "disabled")])
    stream = offer_stream(api.get(f"/api/campaigns/{cid}").json())
    assert stream["total"] == 100
    assert [o["state"] for o in stream["offers"]] == ["active", "active", "disabled"]
    base = f"/api/streams/{sid}"
    assert api.post(f"{base}/offers/13972/remove").status_code == 400
    stream = api.post(f"{base}/offers", json={"offer_id": 18813}).json()
    assert shares(stream) == {3749: 33, 3717: 33, 18813: 34}
    assert api.post(f"{base}/push").status_code == 200
    assert (13972, 10, "disabled") in fake.stream_offers(sid)


def test_bring_back_of_offer_gone_from_keitaro_is_checked_on_push(api, fake):
    cid, sid = fake.add_campaign("c", [(3749, 50), (3717, 50)])
    api.get(f"/api/campaigns/{cid}")
    base = f"/api/streams/{sid}"
    api.post(f"{base}/offers/3717/remove")
    api.post(f"{base}/push")
    fake.offers = [o for o in fake.offers if o["id"] != 3717]  # offer deleted in Keitaro
    api.post(f"/api/campaigns/{cid}/sync")
    assert api.post(f"{base}/offers/3717/restore").status_code == 200
    r = api.post(f"{base}/push")
    assert r.status_code == 400
    assert "3717" in r.json()["detail"]


def test_only_pinned_offers_left_are_unpinned(api, fake):
    cid, sid = fake.add_campaign("c", [(3749, 30), (3717, 30), (13972, 40)])
    api.get(f"/api/campaigns/{cid}")
    base = f"/api/streams/{sid}"
    api.post(f"{base}/offers/3749/pin", json={"pinned": True})
    api.post(f"{base}/offers/3717/pin", json={"pinned": True})
    stream = api.post(f"{base}/offers/13972/remove").json()
    assert shares(stream) == {3749: 50, 3717: 50}
    assert not any(o["pinned"] for o in stream["offers"])


def test_create_succeeds_when_first_sync_fails(api, fake, monkeypatch):
    from app.keitaro.client import KeitaroError
    from app.services import creator

    def broken_sync(*args, **kwargs):
        raise KeitaroError("Keitaro 500: boom", 500)

    monkeypatch.setattr(creator, "sync_campaign", broken_sync)
    r = api.post("/api/campaigns", json={"name": "x", "geo": "MX", "offer_id": 18813})
    assert r.status_code == 201
    assert len(fake.campaigns) == 1
    # The editor loads it from Keitaro on first open.
    monkeypatch.undo()
    campaign = api.get(f"/api/campaigns/{r.json()['id']}").json()
    assert shares(offer_stream(campaign)) == {18813: 100}


def test_offer_search_limit_is_bounded(api):
    assert api.get("/api/offers", params={"limit": 0}).status_code == 422
    assert api.get("/api/offers", params={"limit": 1000}).status_code == 422
