"""Stream offer editor with a draft, as in the reference "keitaro wrapper" video.

Add, remove, bring back and manual share changes edit a local draft and recount shares.
Push sends the draft to Keitaro, Cancel returns to what Keitaro had. Pins are local.
Offers switched off in Keitaro are left as they are and sent back switched off.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.keitaro import payloads
from app.keitaro.client import KeitaroClient
from app.models import (
    ACTIVE,
    DISABLED,
    REMOVED,
    AuditLog,
    Campaign,
    OfferCache,
    Stream,
    StreamOffer,
)
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
    present = set()
    for item in kt_offers:
        offer_id = item["offer_id"]
        present.add(offer_id)
        row = rows.get(offer_id)
        if row is None:
            row = StreamOffer(offer_id=offer_id, position=0, pinned=False)
            stream.offers.append(row)
        row.offer_name = names.get(offer_id) or row.offer_name or f"Оффер #{offer_id}"
        row.state = ACTIVE if (item.get("state") or "active") == "active" else DISABLED
        row.share = int(item.get("share") or 0)
        row.kt_share = row.share
        row.kt_link_id = item.get("id")
        row.synced = True
        if row.state == DISABLED:
            row.pinned = False

    for row in list(stream.offers):
        if row.offer_id in present:
            continue
        if not row.synced:
            stream.offers.remove(row)
            continue
        row.state = REMOVED
        row.share = 0
        row.kt_share = None
        row.kt_link_id = None
        row.pinned = False
    _renumber(stream)


# Draft operations


def get_stream(db: Session, stream_id: int) -> Stream:
    stream = db.get(Stream, stream_id)
    if stream is None:
        raise NotFound(f"Поток {stream_id} не найден, загрузите кампанию из Keitaro")
    return stream


def add_offer(db: Session, stream_id: int, offer_id: int) -> Stream:
    stream = _editable_stream(db, stream_id)
    row = _find_row(stream, offer_id)
    if row is not None:
        if row.state == REMOVED:
            return restore_offer(db, stream_id, offer_id)
        _require_not_disabled(row)
        raise EditorError(f"Оффер {offer_id} уже есть в потоке")

    _require_known_offer(db, offer_id)
    stream.offers.append(
        StreamOffer(
            offer_id=offer_id,
            offer_name=db.get(OfferCache, offer_id).name,
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
    _require_not_disabled(row)
    if row.state == REMOVED:
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
    if row.state != REMOVED:
        raise EditorError(f"Оффер {offer_id} и так в потоке")
    row.state = ACTIVE
    if row.kt_share is None:
        # Gone from Keitaro: it comes back at the end, as Keitaro adds it anew.
        row.position = _next_position(stream)
    # Still in Keitaro (removed in this draft only): back to its place there.
    _renumber(stream)
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
        if row.state == DISABLED:
            continue
        if row.kt_share is not None:
            row.state = ACTIVE
            row.share = row.kt_share
        elif row.synced:
            row.state = REMOVED
            row.share = 0
            row.pinned = False
        else:
            stream.offers.remove(row)
    _renumber(stream)
    db.commit()
    return stream


def push_stream(db: Session, client: KeitaroClient, stream_id: int) -> Stream:
    """Send the draft. The offers cache must be fresh: new offers are checked against it."""
    stream = _editable_stream(db, stream_id)
    rows = ordered_rows(stream)
    active = [r for r in rows if r.state == ACTIVE]
    try:
        validate_total([r.share for r in active])
    except ShareError as exc:
        raise EditorError(str(exc)) from exc
    # Offers already in the Keitaro stream may be hidden from this API key, so only offers
    # added or brought back in the draft are checked.
    for row in active:
        if row.kt_share is None:
            _require_known_offer(db, row.offer_id)

    # Refuse to overwrite changes made in Keitaro after our last sync.
    kt_stream = _kt_stream(client, stream)
    if kt_stream is None:
        raise Conflict("Поток удалён в Keitaro, загрузите кампанию заново")
    if _kt_snapshot(kt_stream.get("offers") or []) != _known_snapshot(rows):
        raise Conflict("Поток изменился в Keitaro после загрузки: нажмите «Загрузить из Keitaro»")

    body = payloads.stream_offers_payload(
        (r.offer_id, r.share if r.state == ACTIVE else r.kt_share, r.state)
        for r in rows
        if r.state in (ACTIVE, DISABLED)
    )
    response = client.update_stream(stream.id, body)
    if isinstance(response, dict) and isinstance(response.get("offers"), list):
        kt_offers = response["offers"]
    else:
        kt_offers = (_kt_stream(client, stream) or {}).get("offers") or []
    apply_kt_offers(stream, kt_offers, _offer_names(db))
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


_DISPLAY_GROUP = {ACTIVE: 0, DISABLED: 1, REMOVED: 2}


def display_rows(stream: Stream) -> list[StreamOffer]:
    """Active offers by share, largest first; then switched off, then removed."""
    rows = ordered_rows(stream)
    return sorted(rows, key=lambda r: (_DISPLAY_GROUP[r.state], -r.share if r.active else 0))


def is_dirty(stream: Stream) -> bool:
    for row in stream.offers:
        if row.state == DISABLED:
            continue
        in_kt = row.kt_share is not None
        if row.active != in_kt or (row.active and row.share != row.kt_share):
            return True
    return False


def is_editable(stream: Stream) -> bool:
    return stream.schema == OFFER_SCHEMA


# Internals


def _recount_and_save(db: Session, stream: Stream) -> Stream:
    rows = [r for r in ordered_rows(stream) if r.state != DISABLED]
    active = [r for r in rows if r.active]
    if active and all(r.pinned for r in active):
        # Pins cannot all hold when nothing else takes the remainder: drop them.
        for r in active:
            r.pinned = False
    try:
        shares = rebalance([ShareSlot(r.share, r.active, r.pinned) for r in rows])
    except ShareError as exc:
        db.rollback()
        raise EditorError(str(exc)) from exc
    for row, share in zip(rows, shares, strict=True):
        row.share = share
    db.commit()
    return stream


def _renumber(stream: Stream) -> None:
    """Offers in Keitaro in Keitaro's order (order of adding), then removed ones."""
    in_kt = sorted(
        (r for r in stream.offers if r.kt_share is not None),
        key=lambda r: (r.kt_link_id or 0, r.position),
    )
    rest = sorted((r for r in stream.offers if r.kt_share is None), key=lambda r: r.position)
    for n, row in enumerate(in_kt + rest, start=1):
        row.position = n


def _kt_stream(client: KeitaroClient, stream: Stream) -> dict | None:
    current = client.campaign_streams(stream.campaign_id)
    return next((s for s in current if s["id"] == stream.id), None)


def _kt_snapshot(kt_offers: list[dict]) -> dict[int, tuple[int, str]]:
    return {
        o["offer_id"]: (
            int(o.get("share") or 0),
            ACTIVE if (o.get("state") or "active") == "active" else DISABLED,
        )
        for o in kt_offers
    }


def _known_snapshot(rows: list[StreamOffer]) -> dict[int, tuple[int, str]]:
    return {
        r.offer_id: (r.kt_share, DISABLED if r.state == DISABLED else ACTIVE)
        for r in rows
        if r.kt_share is not None
    }


def _editable_stream(db: Session, stream_id: int) -> Stream:
    stream = get_stream(db, stream_id)
    if not is_editable(stream):
        raise EditorError("В этом потоке нет офферов: он делает редирект")
    return stream


def _require_known_offer(db: Session, offer_id: int) -> None:
    offer = db.get(OfferCache, offer_id)
    if offer is None or offer.state != "active":
        raise EditorError(f"Оффер {offer_id} не найден среди активных офферов Keitaro")


def _require_not_disabled(row: StreamOffer) -> None:
    if row.state == DISABLED:
        raise EditorError(f"Оффер {row.offer_id} выключен в самом Keitaro: включите его там")


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
