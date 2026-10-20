import re

import pytest

from app.keitaro import payloads


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MX", ["MX"]),
        ("mx, au;RO", ["MX", "AU", "RO"]),
        ("  MX  MX  ", ["MX"]),
        ("ro\nau", ["RO", "AU"]),
        ("UK, gb", ["GB"]),
    ],
)
def test_parse_countries(raw, expected):
    assert payloads.parse_countries(raw) == expected


@pytest.mark.parametrize("raw", ["", " , ", "XX", "MEX", "MX, ZZ"])
def test_parse_countries_rejects_bad_input(raw):
    with pytest.raises(payloads.PayloadError):
        payloads.parse_countries(raw)


def test_make_alias():
    assert re.fullmatch(r"tg-test-mx-[0-9a-f]{6}", payloads.make_alias("TG test MX"))
    assert re.fullmatch(r"campaign-[0-9a-f]{6}", payloads.make_alias("Кампания"))
    assert payloads.make_alias("a") != payloads.make_alias("a")


def test_campaign_payload_matches_reference_campaign():
    params = {"sub_id_1": {"name": "utm_placement", "placeholder": "{{placement}}"}}
    body = payloads.campaign_payload(
        name="TG test",
        alias="tg-test-abc123",
        group_id=4970,
        traffic_source_id=473,
        domain_id=4622,
        parameters=params,
    )
    assert body == {
        "name": "TG test",
        "alias": "tg-test-abc123",
        "type": "position",
        "state": "active",
        "cost_type": "CPC",
        "cost_value": 0,
        "cost_currency": "USD",
        "cost_auto": True,
        "uniqueness_method": "ip_ua",
        "group_id": 4970,
        "traffic_source_id": 473,
        "domain_id": 4622,
        "parameters": params,
    }


def test_campaign_payload_without_source_parameters():
    body = payloads.campaign_payload(
        name="x", alias="x-1", group_id=1, traffic_source_id=2, domain_id=3, parameters=None
    )
    assert "parameters" not in body


def test_geo_stream_payload_matches_reference_flow_1():
    body = payloads.geo_stream_payload(
        campaign_id=7, countries=["MX", "AU"], redirect_url="https://google.com"
    )
    assert body["campaign_id"] == 7
    assert body["position"] == 1
    assert body["type"] == "regular"
    assert body["schema"] == "redirect"
    assert body["action_type"] == "http"
    assert body["action_payload"] == "https://google.com"
    assert body["filters"] == [{"name": "country", "mode": "accept", "payload": ["MX", "AU"]}]
    assert "offers" not in body


def test_offer_stream_payload_matches_reference_flow_2():
    body = payloads.offer_stream_payload(campaign_id=7, offer_id=18813)
    assert body["position"] == 2
    assert body["schema"] == "landings"
    assert body["action_type"] == "http"
    assert body["offers"] == [{"offer_id": 18813, "share": 100, "state": "active"}]
    assert "filters" not in body


def test_stream_offers_payload():
    assert payloads.stream_offers_payload(
        [(1, 60, "active"), (2, 40, "active"), (3, 5, "disabled")]
    ) == {
        "offers": [
            {"offer_id": 1, "share": 60, "state": "active"},
            {"offer_id": 2, "share": 40, "state": "active"},
            {"offer_id": 3, "share": 5, "state": "disabled"},
        ]
    }
