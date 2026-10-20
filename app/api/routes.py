from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, KeitaroDep, SettingsDep
from app.keitaro.payloads import country_list
from app.models import Campaign
from app.schemas import (
    CampaignCreate,
    CampaignCreated,
    CampaignListItem,
    CampaignOut,
    CountryOut,
    MetaOut,
    OfferOut,
    OfferRef,
    PinIn,
    ShareIn,
    StreamOut,
)
from app.services import creator, editor
from app.services.offers import cached_offers, search_offers

router = APIRouter(prefix="/api")


@router.get("/meta", response_model=MetaOut)
def meta(
    settings: SettingsDep,
    client: KeitaroDep,
):
    groups = {g["id"]: g["name"] for g in client.list_groups()}
    sources = {s["id"]: s["name"] for s in client.list_traffic_sources()}
    return MetaOut(
        keitaro_admin_url=settings.keitaro_admin_url,
        group=groups.get(settings.keitaro_group_id, f"#{settings.keitaro_group_id}"),
        traffic_source=sources.get(
            settings.keitaro_traffic_source_id, f"#{settings.keitaro_traffic_source_id}"
        ),
        domain_id=settings.keitaro_domain_id,
        geo_redirect_url=settings.geo_redirect_url,
    )


@router.get("/countries", response_model=list[CountryOut])
def countries():
    return country_list()


@router.get("/offers", response_model=list[OfferOut])
def offers(
    db: DbSession,
    settings: SettingsDep,
    client: KeitaroDep,
    q: str = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    refresh: bool = False,
):
    rows = cached_offers(db, client, settings.offers_cache_ttl, force=refresh)
    found = search_offers(rows, q, limit)
    return [OfferOut(id=r.id, name=r.name, countries=r.countries) for r in found]


@router.post("/campaigns", response_model=CampaignCreated, status_code=201)
def create_campaign(
    body: CampaignCreate,
    db: DbSession,
    settings: SettingsDep,
    client: KeitaroDep,
):
    result = creator.create_campaign(
        db, client, settings, name=body.name, geo=body.geo, offer_id=body.offer_id
    )
    c = result.campaign
    return CampaignCreated(
        id=c.id,
        name=c.name,
        alias=c.alias,
        countries=result.countries,
        admin_url=settings.campaign_admin_url(c.id),
    )


@router.get("/campaigns", response_model=list[CampaignListItem])
def list_campaigns(db: DbSession, client: KeitaroDep, q: str = ""):
    mine = {c.id for c in db.query(Campaign).filter(Campaign.created_here.is_(True))}
    needle = q.strip().lower()
    items = [
        CampaignListItem(
            id=c["id"],
            name=c.get("name") or "",
            alias=c.get("alias") or "",
            group=c.get("group"),
            state=c.get("state") or "",
            created_at=c.get("created_at"),
            created_here=c["id"] in mine,
        )
        for c in client.list_campaigns()
        if c.get("state") != "deleted"
    ]
    if needle:
        items = [
            i
            for i in items
            if needle in i.name.lower() or needle in str(i.id) or needle in i.alias.lower()
        ]
    return sorted(items, key=lambda i: i.id, reverse=True)


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(
    campaign_id: int,
    db: DbSession,
    settings: SettingsDep,
    client: KeitaroDep,
):
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.synced_at is None:
        cached_offers(db, client, settings.offers_cache_ttl)
        campaign = editor.sync_campaign(db, client, campaign_id)
    return CampaignOut.build(campaign, settings.campaign_admin_url(campaign.id))


@router.post("/campaigns/{campaign_id}/sync", response_model=CampaignOut)
def sync_campaign(
    campaign_id: int,
    db: DbSession,
    settings: SettingsDep,
    client: KeitaroDep,
):
    cached_offers(db, client, settings.offers_cache_ttl, force=True)
    campaign = editor.sync_campaign(db, client, campaign_id)
    return CampaignOut.build(campaign, settings.campaign_admin_url(campaign.id))


@router.post("/streams/{stream_id}/offers", response_model=StreamOut)
def add_offer(
    stream_id: int,
    body: OfferRef,
    db: DbSession,
    settings: SettingsDep,
    client: KeitaroDep,
):
    cached_offers(db, client, settings.offers_cache_ttl)
    return StreamOut.build(editor.add_offer(db, stream_id, body.offer_id))


@router.post("/streams/{stream_id}/offers/{offer_id}/remove", response_model=StreamOut)
def remove_offer(stream_id: int, offer_id: int, db: DbSession):
    return StreamOut.build(editor.remove_offer(db, stream_id, offer_id))


@router.post("/streams/{stream_id}/offers/{offer_id}/restore", response_model=StreamOut)
def restore_offer(stream_id: int, offer_id: int, db: DbSession):
    return StreamOut.build(editor.restore_offer(db, stream_id, offer_id))


@router.post("/streams/{stream_id}/offers/{offer_id}/pin", response_model=StreamOut)
def pin_offer(stream_id: int, offer_id: int, body: PinIn, db: DbSession):
    return StreamOut.build(editor.set_pinned(db, stream_id, offer_id, body.pinned))


@router.post("/streams/{stream_id}/offers/{offer_id}/share", response_model=StreamOut)
def set_share(stream_id: int, offer_id: int, body: ShareIn, db: DbSession):
    return StreamOut.build(editor.set_share(db, stream_id, offer_id, body.share))


@router.post("/streams/{stream_id}/recount", response_model=StreamOut)
def recount(stream_id: int, db: DbSession):
    return StreamOut.build(editor.recount(db, stream_id))


@router.post("/streams/{stream_id}/cancel", response_model=StreamOut)
def cancel(stream_id: int, db: DbSession):
    return StreamOut.build(editor.cancel_draft(db, stream_id))


@router.post("/streams/{stream_id}/push", response_model=StreamOut)
def push(stream_id: int, db: DbSession, settings: SettingsDep, client: KeitaroDep):
    # Offers added in the draft are checked against a fresh list.
    cached_offers(db, client, settings.offers_cache_ttl, force=True)
    return StreamOut.build(editor.push_stream(db, client, stream_id))
