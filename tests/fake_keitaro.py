"""In-memory Keitaro Admin API for tests, served through httpx.MockTransport.

It behaves like the real tracker where it matters here: PUT /streams/{id} replaces the
offer list, keeps the link id of an offer that stays and gives a new id to a re-added one.
"""

import itertools
import json

import httpx


class FakeKeitaro:
    def __init__(self, offers: list[dict] | None = None):
        self.offers = offers or [
            {"id": 3717, "name": "Miaflow RO prize", "state": "active", "country": ["Romania"]},
            {"id": 3749, "name": "Miaflow RO spin", "state": "active", "country": ["Romania"]},
            {"id": 13972, "name": "another test offer 2", "state": "active", "country": []},
            {"id": 18813, "name": "Flexacil PE", "state": "active", "country": ["Peru"]},
            {"id": 500, "name": "Old disabled", "state": "disabled", "country": []},
        ]
        self.campaigns: dict[int, dict] = {}
        self.streams: dict[int, dict] = {}
        self.requests: list[tuple[str, str, dict | None]] = []
        self.fail_stream_create = False
        self._ids = itertools.count(1000)
        self._link_ids = itertools.count(50_000)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def calls(self, method: str | None = None) -> list[tuple[str, str, dict | None]]:
        return [r for r in self.requests if method is None or r[0] == method]

    def add_campaign(self, name: str, offers: list[tuple[int, int]]) -> tuple[int, int]:
        """Seed a campaign like the reference one; returns (campaign_id, offer_stream_id)."""
        cid = next(self._ids)
        self.campaigns[cid] = {"id": cid, "name": name, "alias": f"alias-{cid}", "state": "active"}
        self._new_stream(
            {
                "campaign_id": cid,
                "name": "Flow 1",
                "type": "regular",
                "position": 1,
                "schema": "redirect",
                "action_type": "http",
                "action_payload": "https://google.com",
                "filters": [{"name": "country", "mode": "accept", "payload": ["AU"]}],
            }
        )
        sid = self._new_stream(
            {
                "campaign_id": cid,
                "name": "Flow 2",
                "type": "regular",
                "position": 2,
                "schema": "landings",
                "action_type": "http",
                "offers": [{"offer_id": o, "share": s, "state": "active"} for o, s in offers],
            }
        )["id"]
        return cid, sid

    def set_offers(self, stream_id: int, offers: list[tuple[int, int]]) -> None:
        """Change the stream directly, as someone editing it in the Keitaro admin."""
        self._replace_offers(
            self.streams[stream_id], [{"offer_id": o, "share": s} for o, s in offers]
        )

    # transport

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Api-Key"] == "test-key"
        assert "Mozilla" in request.headers["User-Agent"]
        body = json.loads(request.content) if request.content else None
        path = request.url.path.removeprefix("/admin_api/v1")
        self.requests.append((request.method, path, body))
        parts = path.strip("/").split("/")
        method = request.method

        if parts == ["offers"] and method == "GET":
            return self._json(self.offers)
        if parts == ["groups"]:
            return self._json([{"id": 4970, "name": "FORTESTS", "type": "campaigns"}])
        if parts == ["traffic_sources"]:
            return self._json([{"id": 473, "name": "FORTESTS"}])
        if parts == ["campaigns"] and method == "GET":
            return self._json(list(self.campaigns.values()))
        if parts == ["campaigns"] and method == "POST":
            cid = next(self._ids)
            self.campaigns[cid] = {**body, "id": cid, "group": "FORTESTS"}
            return self._json(self.campaigns[cid])
        if parts[0] == "campaigns" and len(parts) >= 2:
            cid = int(parts[1])
            if cid not in self.campaigns:
                return httpx.Response(404, json={"error": "Not found"})
            if len(parts) == 3 and parts[2] == "streams":
                streams = [s for s in self.streams.values() if s["campaign_id"] == cid]
                return self._json(sorted(streams, key=lambda s: s["position"]))
            if method == "DELETE":
                self.campaigns[cid]["state"] = "deleted"
            return self._json(self.campaigns[cid])
        if parts == ["streams"] and method == "POST":
            if self.fail_stream_create:
                return httpx.Response(500, json={"error": "boom"})
            return self._json(self._new_stream(body))
        if parts[0] == "streams" and method == "PUT":
            stream = self.streams[int(parts[1])]
            if "offers" in body:
                self._replace_offers(stream, body["offers"])
            return self._json(stream)
        return httpx.Response(404, json={"error": f"unexpected {method} {path}"})

    # internals

    def _new_stream(self, body: dict) -> dict:
        sid = next(self._ids)
        stream = {"filters": [], "offers": [], **body, "id": sid}
        stream["offers"] = []
        self._replace_offers(stream, body.get("offers") or [])
        self.streams[sid] = stream
        return stream

    def _replace_offers(self, stream: dict, offers: list[dict]) -> None:
        old = {o["offer_id"]: o for o in stream["offers"]}
        new = []
        for item in offers:
            link = old.get(item["offer_id"])
            link_id = link["id"] if link else next(self._link_ids)
            new.append(
                {
                    "id": link_id,
                    "stream_id": stream["id"],
                    "offer_id": item["offer_id"],
                    "share": item["share"],
                    "state": item.get("state", "active"),
                }
            )
        stream["offers"] = sorted(new, key=lambda o: o["id"])

    @staticmethod
    def _json(data) -> httpx.Response:
        return httpx.Response(200, json=data)
