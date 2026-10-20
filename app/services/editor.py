"""Stream offer editor with a draft, as in the reference "keitaro wrapper" video.

Add, remove, bring back and manual share changes edit a local draft and recount shares.
Push sends the draft to Keitaro, Cancel returns to what Keitaro had. Pins are local.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.keitaro import payloads
from app.keitaro.client import KeitaroClient
from app.models import ACTIVE, REMOVED, AuditLog, Campaign, OfferCache, Stream, StreamOffer
from app.services.shares import TOTAL, ShareError, ShareSlot, rebalance, validate_total

OFFER_SCHEMA = "landings"


class EditorError(ValueError):
    pass


class NotFound(EditorError):
    pass


class Conflict(EditorError):
    pass


# Sync from Keitaro


def sync_campaign(db: Session, client: KeitaroClient, campaign_id: int) -> Campaign:
    """Load the campaign and its streams from Keitaro; Keitaro state replaces any draft."""
    kt_campaign = client.get_campaign(campaign_id)
    kt_streams = client.campaign_streams(campaign_id)
    names = _offer_names(db)

    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        campaign = Campaign(id=campaign_id, created_here=False)
        db.add(campaign)
    campaign.name = kt_campaign.get("name") or f"Campaign {campaign_id}"
    campaign.alias = kt_campaign.get("alias") or ""
    campaign.synced_at = datetime.now(UTC)

    seen = set()
    for item in kt_streams:
        seen.add(item["id"])
        stream = db.get(Stream, item["id"])
        if stream is None:
            stream = Stream(id=item["id"], campaign=campaign)
            db.add(stream)
        stream.campaign_id = campaign_id
        stream.name = item.get("name") or f"Stream {item['id']}"
        stream.type = item.get("type") or "regular"
        stream.position = item.get("position") or 0
        stream.schema = item.get("schema") or ""
        stream.action_type = item.get("action_type")
        stream.action_payload = item.get("action_payload")
        stream.state = item.get("state") or "active"
        stream.filters = [
            {"name": f.get("name"), "mode": f.get("mode"), "payload": f.get("payload")}
            for f in item.get("filters") or []
        ]
        apply_kt_offers(stream, item.get("offers") or [], names)

    for stream in list(campaign.streams):
        if stream.id not in seen:
            campaign.streams.remove(stream)

    db.commit()
    db.refresh(campaign)
    return campaign


def apply_kt_offers(stream: Stream, kt_offers: list[dict], names: dict[int, str]) -> None:
    """Make the rows match the offers Keitaro has in the stream, keeping removed history."""
    rows = {row.offer_id: row for row in stream.offers}
    next_position = _next_position(stream)
    present = set()
    # Keitaro lists offers in the order they were added to the stream.
    for item in sorted(kt_offers, key=lambda o: o.get("id") or 0):
        offer_id = item["offer_id"]
        present.add(offer_id)
        row = rows.get(offer_id)
        if row is None:
            row = StreamOffer(offer_id=offer_id, position=next_position, pinned=False)
            next_position += 1
            stream.offers.append(row)
        row.offer_name = names.get(offer_id) or row.offer_name or f"Оффер #{offer_id}"
        row.state = ACTIVE
        row.share = int(item.get("share") or 0)
        row.kt_share = row.share
        row.synced = True

    for row in list(stream.offers):
        if row.offer_id in present:
            continue
        if not row.synced:
            stream.offers.remove(row)
            continue
        row.state = REMOVED
        row.share = 0
        row.kt_share = None
        row.pinned = False


# Draft operations


def get_stream(db: Session, stream_id: int) -> Stream:
    stream = db.get(Stream, stream_id)
    if stream is None:
        raise NotFound(f"Поток {stream_id} не найден, загрузите кампанию из Keitaro")
    return stream


def add_offer(db: Session, stream_id: int, offer_id: int) -> Stream:
    stream = _editable_stream(db, stream_id)
    row = _find_row(stream, offer_id)
    if row is not None and row.active:
        raise EditorError(f"Оффер {offer_id} уже есть в потоке")
    if row is not None:
        return restore_offer(db, stream_id, offer_id)

    offer = db.get(OfferCache, offer_id)
    if offer is None or offer.state != "active":
        raise EditorError(f"Оффер {offer_id} не найден среди активных офферов Keitaro")
    stream.offers.append(
        StreamOffer(
            offer_id=offer_id,
            offer_name=offer.name,
            position=_next_position(stream),
            state=ACTIVE,
            share=0,
            synced=False,
        )
    )
    return _recount_and_save(db, stream)


def remove_offer(db: Session, stream_id: int, offer_id: int) -> Stream:
    stream = _editable_stream(db, stream_id)
    row = _require_row(stream, offer_id)
    if not row.active:
        raise EditorError(f"Оффер {offer_id} уже удалён")
    if not row.synced:
        # Added in this draft only: nothing to keep in history.
        stream.offers.remove(row)
    else:
        row.state = REMOVED
        row.share = 0
        row.pinned = False
    return _recount_and_save(db, stream)


def restore_offer(db: Session, stream_id: int, offer_id: int) -> Stream:
    stream = _editable_stream(db, stream_id)
    row = _require_row(stream, offer_id)
    if row.active:
        raise EditorError(f"Оффер {offer_id} и так в потоке")
    row.state = ACTIVE
    # Brought back offers go to the end, as Keitaro adds them anew.
    row.position = _next_position(stream)
    return _recount_and_save(db, stream)


def set_pinned(db: Session, stream_id: int, offer_id: int, pinned: bool) -> Stream:
    stream = _editable_stream(db, stream_id)
    row = _require_row(stream, offer_id)
    if not row.active:
        raise EditorError("Закрепить можно только активный оффер")
    row.pinned = pinned
    db.commit()
    return stream


def set_share(db: Session, stream_id: int, offer_id: int, share: int) -> Stream:
    """Manual share: the offer is pinned at this value and the others are recounted."""
    stream = _editable_stream(db, stream_id)
    row = _require_row(stream, offer_id)
    if not row.active:
        raise EditorError("Долю можно задать только активному офферу")
    if not 0 <= share <= TOTAL:
        raise EditorError("Доля должна быть от 0 до 100")
    if not any(r.active and not r.pinned and r is not row for r in stream.offers):
        raise EditorError("Нет других незакреплённых офферов, чтобы забрать остаток")
    row.share = share
    row.pinned = True
    return _recount_and_save(db, stream)


def recount(db: Session, stream_id: int) -> Stream:
    return _recount_and_save(db, _editable_stream(db, stream_id))


def cancel_draft(db: Session, stream_id: int) -> Stream:
    stream = _editable_stream(db, stream_id)
    for row in list(stream.offers):
        if row.kt_share is not None:
            row.state = ACTIVE
            row.share = row.kt_share
        elif row.synced:
            row.state = REMOVED
            row.share = 0
            row.pinned = False
        else:
            stream.offers.remove(row)
    db.commit()
    return stream


def push_stream(db: Session, client: KeitaroClient, stream_id: int) -> Stream:
    stream = _editable_stream(db, stream_id)
    active = [r for r in ordered_rows(stream) if r.active]
    try:
        validate_total([r.share for r in active])
    except ShareError as exc:
        raise EditorError(str(exc)) from exc

    # Refuse to overwrite changes made in Keitaro after our last sync.
    current = client.campaign_streams(stream.campaign_id)
    kt_stream = next((s for s in current if s["id"] == stream.id), None)
    if kt_stream is None:
        raise Conflict("Поток удалён в Keitaro, загрузите кампанию заново")
    kt_now = {o["offer_id"]: int(o.get("share") or 0) for o in kt_stream.get("offers") or []}
    known = {r.offer_id: r.kt_share for r in stream.offers if r.kt_share is not None}
    if kt_now != known:
        raise Conflict("Поток изменился в Keitaro после загрузки: нажмите «Загрузить из Keitaro»")

    body = payloads.stream_offers_payload((r.offer_id, r.share) for r in active)
    response = client.update_stream(stream.id, body)
    apply_kt_offers(stream, response.get("offers") or [], _offer_names(db))
    db.add(
        AuditLog(
            action="push_stream", campaign_id=stream.campaign_id, stream_id=stream.id, payload=body
        )
    )
    db.commit()
    return stream


# Read helpers


def ordered_rows(stream: Stream) -> list[StreamOffer]:
    return sorted(stream.offers, key=lambda r: r.position)


def display_rows(stream: Stream) -> list[StreamOffer]:
    """Active offers by share, largest first; removed ones at the bottom."""
    rows = ordered_rows(stream)
    return sorted(rows, key=lambda r: (not r.active, -r.share if r.active else 0))


def is_dirty(stream: Stream) -> bool:
    for row in stream.offers:
        in_kt = row.kt_share is not None
        if row.active != in_kt or (row.active and row.share != row.kt_share):
            return True
    return False


def is_editable(stream: Stream) -> bool:
    return stream.schema == OFFER_SCHEMA


# Internals


def _recount_and_save(db: Session, stream: Stream) -> Stream:
    rows = ordered_rows(stream)
    try:
        shares = rebalance([ShareSlot(r.share, r.active, r.pinned) for r in rows])
    except ShareError as exc:
        db.rollback()
        raise EditorError(str(exc)) from exc
    for row, share in zip(rows, shares, strict=True):
        row.share = share
    db.commit()
    return stream


def _editable_stream(db: Session, stream_id: int) -> Stream:
    stream = get_stream(db, stream_id)
    if not is_editable(stream):
        raise EditorError("В этом потоке нет офферов: он делает редирект")
    return stream


def _find_row(stream: Stream, offer_id: int) -> StreamOffer | None:
    return next((r for r in stream.offers if r.offer_id == offer_id), None)


def _require_row(stream: Stream, offer_id: int) -> StreamOffer:
    row = _find_row(stream, offer_id)
    if row is None:
        raise NotFound(f"Оффера {offer_id} нет в потоке")
    return row


def _next_position(stream: Stream) -> int:
    return max((r.position for r in stream.offers), default=0) + 1


def _offer_names(db: Session) -> dict[int, str]:
    return {o.id: o.name for o in db.scalars(select(OfferCache))}
