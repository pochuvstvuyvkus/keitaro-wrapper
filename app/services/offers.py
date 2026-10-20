from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.keitaro.client import KeitaroClient
from app.models import OfferCache


def refresh_offers(db: Session, client: KeitaroClient) -> list[OfferCache]:
    rows = []
    now = datetime.now(UTC)
    fetched = client.list_offers()
    db.execute(delete(OfferCache))
    for item in fetched:
        row = OfferCache(
            id=item["id"],
            name=item.get("name") or f"Offer {item['id']}",
            state=item.get("state") or "active",
            countries=item.get("country") or [],
            synced_at=now,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


def cached_offers(
    db: Session, client: KeitaroClient, ttl_seconds: int, force: bool = False
) -> list[OfferCache]:
    rows = list(db.scalars(select(OfferCache).order_by(OfferCache.id.desc())))
    if force or not rows or _is_stale(rows[0].synced_at, ttl_seconds):
        rows = refresh_offers(db, client)
        rows.sort(key=lambda r: r.id, reverse=True)
    return rows


def search_offers(rows: list[OfferCache], query: str, limit: int = 20) -> list[OfferCache]:
    """Match by id or by any word of the name, case-insensitive; active offers only."""
    q = query.strip().lower()
    active = [r for r in rows if r.state == "active"]
    if not q:
        return active[:limit]
    return [r for r in active if q in str(r.id) or q in r.name.lower()][:limit]


def _is_stale(synced_at: datetime, ttl_seconds: int) -> bool:
    if synced_at.tzinfo is None:
        synced_at = synced_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - synced_at > timedelta(seconds=ttl_seconds)
