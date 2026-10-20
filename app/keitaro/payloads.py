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

# Codes people use that are not ISO 3166-1 alpha-2.
COUNTRY_ALIASES = {"UK": "GB"}


class PayloadError(ValueError):
    pass


def parse_countries(raw: str) -> list[str]:
    """'mx, AU;ro' -> ['MX', 'AU', 'RO']; unknown codes raise PayloadError."""
    codes: list[str] = []
    for part in re.split(r"[\s,;]+", raw.strip()):
        if not part:
            continue
        code = COUNTRY_ALIASES.get(part.upper(), part.upper())
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
    *,
    name: str,
    alias: str,
    group_id: int,
    traffic_source_id: int,
    domain_id: int,
    parameters: dict | None = None,
) -> dict:
    """Campaign settings as in the reference campaign.

    The admin UI copies the traffic source's parameters (utm_*, sub_id_*) into the campaign
    when a source is picked; the API does not, so they are passed explicitly.
    """
    body = {
        "name": name,
        "alias": alias,
        "type": "position",
        "state": "active",
        "cost_type": "CPC",
        "cost_value": 0,
        "cost_currency": "USD",
        # "Из параметра 'cost'" checkbox on the task screenshot.
        "cost_auto": True,
        "uniqueness_method": "ip_ua",
        "group_id": group_id,
        "traffic_source_id": traffic_source_id,
        "domain_id": domain_id,
    }
    if parameters:
        body["parameters"] = parameters
    return body


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


def stream_offers_payload(offers: Iterable[tuple[int, int, str]]) -> dict:
    """Body for PUT /streams/{id}: Keitaro replaces the stream's offer list with this one.

    Offers are (offer_id, share, state); a switched-off offer must be sent with its state,
    or the PUT would switch it back on.
    """
    return {
        "offers": [
            {"offer_id": offer_id, "share": share, "state": state}
            for offer_id, share, state in offers
        ]
    }
