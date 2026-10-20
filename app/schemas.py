from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_serializer

from app.models import REMOVED, Campaign, Stream
from app.services import editor


class OfferOut(BaseModel):
    id: int
    name: str
    countries: list[str] = []


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geo: str = Field(min_length=2, description="Country codes, e.g. 'MX' or 'MX, AU'")
    offer_id: int


class CampaignCreated(BaseModel):
    id: int
    name: str
    alias: str
    countries: list[str]
    admin_url: str


class CampaignListItem(BaseModel):
    id: int
    name: str
    alias: str
    group: str | None = None
    state: str
    created_at: str | None = None
    created_here: bool = False


class StreamOfferOut(BaseModel):
    offer_id: int
    name: str
    share: int
    kt_share: int | None
    pinned: bool
    state: str
    changed: bool


class StreamOut(BaseModel):
    id: int
    name: str
    type: str
    position: int
    schema_: str = Field(alias="schema", serialization_alias="schema")
    action_type: str | None
    action_payload: str | None
    filters: list[dict]
    editable: bool
    dirty: bool
    total: int
    offers: list[StreamOfferOut]

    @classmethod
    def build(cls, stream: Stream) -> "StreamOut":
        rows = editor.display_rows(stream)
        return cls(
            id=stream.id,
            name=stream.name,
            type=stream.type,
            position=stream.position,
            schema=stream.schema,
            action_type=stream.action_type,
            action_payload=stream.action_payload,
            filters=stream.filters or [],
            editable=editor.is_editable(stream),
            dirty=editor.is_dirty(stream),
            total=sum(r.share for r in rows if r.active),
            offers=[
                StreamOfferOut(
                    offer_id=r.offer_id,
                    name=r.offer_name,
                    share=r.share,
                    kt_share=r.kt_share,
                    pinned=r.pinned,
                    state=r.state,
                    changed=(r.active and r.share != r.kt_share)
                    or (r.state == REMOVED and r.kt_share is not None),
                )
                for r in rows
            ],
        )


class CampaignOut(BaseModel):
    id: int
    name: str
    alias: str
    created_here: bool
    synced_at: datetime | None
    admin_url: str
    streams: list[StreamOut]

    @field_serializer("synced_at")
    def _as_utc(self, value: datetime | None):
        # SQLite drops the timezone; the app stores UTC.
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat() if value else None

    @classmethod
    def build(cls, campaign: Campaign, admin_url: str) -> "CampaignOut":
        # Streams with offers first, like the reference editor.
        streams = sorted(campaign.streams, key=lambda s: (not editor.is_editable(s), s.position))
        return cls(
            id=campaign.id,
            name=campaign.name,
            alias=campaign.alias,
            created_here=campaign.created_here,
            synced_at=campaign.synced_at,
            admin_url=admin_url,
            streams=[StreamOut.build(s) for s in streams],
        )


class OfferRef(BaseModel):
    offer_id: int


class PinIn(BaseModel):
    pinned: bool


class ShareIn(BaseModel):
    share: int = Field(ge=0, le=100)


class MetaOut(BaseModel):
    keitaro_admin_url: str
    group: str
    traffic_source: str
    domain_id: int
    geo_redirect_url: str
