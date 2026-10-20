"""Request bodies for the Keitaro Admin API.

The shape follows the reference campaign from the task (campaign 2, id 93212): two regular
streams, the first redirects visitors from the given countries, the second sends everyone
else to the offers.
"""

import re
import secrets
import unicodedata
from collections.abc import Iterable

import pycountry

GEO_STREAM_NAME = "Flow 1"
OFFER_STREAM_NAME = "Flow 2"


class PayloadError(ValueError):
    pass


def parse_countries(raw: str) -> list[str]:
    """'mx, AU;ro' -> ['MX', 'AU', 'RO']; unknown codes raise PayloadError."""
    codes: list[str] = []
    for part in re.split(r"[\s,;]+", raw.strip()):
        if not part:
            continue
        code = part.upper()
        if pycountry.countries.get(alpha_2=code) is None:
            raise PayloadError(f"Неизвестный код страны: {part}")
        if code not in codes:
            codes.append(code)
    if not codes:
        raise PayloadError("Укажите хотя бы одну страну, например MX")
    return codes


def make_alias(name: str) -> str:
    """URL alias like the ones Keitaro makes: slug of the name plus a random suffix."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:40] or "campaign"
    return f"{slug}-{secrets.token_hex(3)}"


def campaign_payload(
    *, name: str, alias: str, group_id: int, traffic_source_id: int, domain_id: int
) -> dict:
    return {
        "name": name,
        "alias": alias,
        "type": "position",
        "state": "active",
        "cost_type": "CPC",
        "group_id": group_id,
        "traffic_source_id": traffic_source_id,
        "domain_id": domain_id,
    }


def geo_stream_payload(*, campaign_id: int, countries: list[str], redirect_url: str) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": GEO_STREAM_NAME,
        "position": 1,
        "weight": 100,
        "state": "active",
        "schema": "redirect",
        "action_type": "http",
        "action_payload": redirect_url,
        "collect_clicks": True,
        "filter_or": False,
        "filters": [{"name": "country", "mode": "accept", "payload": countries}],
    }


def offer_stream_payload(*, campaign_id: int, offer_id: int) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": OFFER_STREAM_NAME,
        "position": 2,
        "weight": 100,
        "state": "active",
        "schema": "landings",
        "action_type": "http",
        "collect_clicks": True,
        "filter_or": False,
        "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
    }


def stream_offers_payload(offers: Iterable[tuple[int, int]]) -> dict:
    """Body for PUT /streams/{id}: Keitaro replaces the stream's offer list with this one."""
    return {
        "offers": [
            {"offer_id": offer_id, "share": share, "state": "active"} for offer_id, share in offers
        ]
    }
