"""Campaign creator: one campaign with a geo redirect stream and an offer stream."""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings
from app.keitaro import payloads
from app.keitaro.client import KeitaroClient, KeitaroError
from app.models import AuditLog, Campaign
from app.services.editor import sync_campaign
from app.services.offers import cached_offers

log = logging.getLogger(__name__)


class CreateError(ValueError):
    pass


@dataclass
class CreatedCampaign:
    campaign: Campaign
    countries: list[str]


def create_campaign(
    db: Session,
    client: KeitaroClient,
    settings: Settings,
    *,
    name: str,
    geo: str,
    offer_id: int,
) -> CreatedCampaign:
    name = name.strip()
    if not name:
        raise CreateError("Укажите название кампании")
    try:
        countries = payloads.parse_countries(geo)
    except payloads.PayloadError as exc:
        raise CreateError(str(exc)) from exc

    offers = cached_offers(db, client, settings.offers_cache_ttl, force=True)
    if not any(o.id == offer_id and o.state == "active" for o in offers):
        raise CreateError(f"Оффер {offer_id} не найден среди активных офферов Keitaro")

    campaign_body = payloads.campaign_payload(
        name=name,
        alias=payloads.make_alias(name),
        group_id=settings.keitaro_group_id,
        traffic_source_id=settings.keitaro_traffic_source_id,
        domain_id=settings.keitaro_domain_id,
    )
    created = client.create_campaign(campaign_body)
    campaign_id = created["id"]

    geo_body = payloads.geo_stream_payload(
        campaign_id=campaign_id, countries=countries, redirect_url=settings.geo_redirect_url
    )
    offer_body = payloads.offer_stream_payload(campaign_id=campaign_id, offer_id=offer_id)
    try:
        client.create_stream(geo_body)
        client.create_stream(offer_body)
    except KeitaroError:
        # Do not leave a half-built campaign behind.
        try:
            client.delete_campaign(campaign_id)
        except KeitaroError:
            log.exception("could not roll back campaign %s", campaign_id)
        raise

    campaign = Campaign(
        id=campaign_id, name=created["name"], alias=created["alias"], created_here=True
    )
    db.add(campaign)
    db.add(
        AuditLog(
            action="create_campaign",
            campaign_id=campaign_id,
            payload={"campaign": campaign_body, "streams": [geo_body, offer_body]},
        )
    )
    db.commit()
    sync_campaign(db, client, campaign_id)
    return CreatedCampaign(campaign=campaign, countries=countries)
