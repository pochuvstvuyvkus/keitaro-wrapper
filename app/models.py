"""Local mirror of Keitaro campaigns and streams.

Campaign and stream rows use Keitaro ids as primary keys. StreamOffer rows hold the editor
state: the draft share the user is working on and the share last seen in Keitaro, so the
draft can be cancelled, and removed offers stay in the list to be brought back.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ACTIVE = "active"
REMOVED = "removed"
# Switched off in Keitaro: kept as is, not edited and not counted in the 100%.
DISABLED = "disabled"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str] = mapped_column(String(255))
    # True when the campaign was made by the creator form of this app.
    created_here: Mapped[bool] = mapped_column(Boolean, default=False)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    streams: Mapped[list["Stream"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="Stream.position",
    )


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer, default=0)
    schema: Mapped[str] = mapped_column(String(32))
    action_type: Mapped[str | None] = mapped_column(String(64))
    action_payload: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(32), default="active")
    filters: Mapped[list] = mapped_column(JSON, default=list)

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream",
        cascade="all, delete-orphan",
        order_by="StreamOffer.position",
    )


class StreamOffer(Base):
    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id", name="uq_stream_offer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"))
    offer_id: Mapped[int] = mapped_column(Integer)
    offer_name: Mapped[str] = mapped_column(String(512), default="")
    # Order of adding; the rounding remainder goes to the last offers in this order.
    position: Mapped[int] = mapped_column(Integer, default=0)

    # Draft state edited by the user.
    state: Mapped[str] = mapped_column(String(16), default=ACTIVE)
    share: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    # State last seen in Keitaro: None means the offer is not in the stream there.
    kt_share: Mapped[int | None] = mapped_column(Integer)
    # The offer has been in this stream in Keitaro at some point (a removed row is kept).
    synced: Mapped[bool] = mapped_column(Boolean, default=False)
    # Id of the stream-offer link in Keitaro; it grows in the order offers were added there.
    kt_link_id: Mapped[int | None] = mapped_column(Integer)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    stream: Mapped[Stream] = relationship(back_populates="offers")

    @property
    def active(self) -> bool:
        return self.state == ACTIVE


class OfferCache(Base):
    """Offers from Keitaro, cached for the autocomplete and for names in the editor."""

    __tablename__ = "offers_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(512))
    state: Mapped[str] = mapped_column(String(32), default="active")
    countries: Mapped[list] = mapped_column(JSON, default=list)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """What the app sent to Keitaro: campaign creation and stream pushes."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(64))
    campaign_id: Mapped[int | None] = mapped_column(Integer)
    stream_id: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
