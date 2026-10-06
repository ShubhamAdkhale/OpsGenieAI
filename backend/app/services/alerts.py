"""Alert helpers.

Deduplication is keyed on the STATE an alert describes, not on its text.

The messages here embed live figures ("Melt Index 63, Rs 2,60,000 at risk"),
and the physics tick recomputes those every few seconds. Matching on message
text therefore never matched, and a shipment sitting in the same risk band
produced a new alert on every tick until the feed was unreadable. Keying on
something like "shipment-risk:SC-1042:HIGH" means one alert per state: it
appears when the band changes, and while the band holds its message is
refreshed in place so the numbers on screen stay current.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Alert
from app.simulation import clock

# Keep the feed to a length a person can actually read during a demo.
MAX_ALERTS = 120


def raise_alert(
    db: Session,
    severity: str,
    message: str,
    related_type: str = "system",
    related_id: int | None = None,
    dedupe: bool = True,
    dedupe_key: str | None = None,
) -> Alert:
    """Create an alert, or refresh the existing one for the same state."""
    key = dedupe_key if dedupe_key is not None else message
    if dedupe:
        existing = (
            db.query(Alert)
            .filter(
                Alert.related_type == related_type,
                Alert.related_id == related_id,
                Alert.dedupe_key == key,
            )
            .order_by(Alert.id.desc())
            .first()
        )
        if existing is not None:
            # Same state, newer numbers: update rather than pile up.
            existing.message = message
            existing.severity = severity
            db.flush()
            return existing

    alert = Alert(
        severity=severity,
        message=message,
        related_type=related_type,
        related_id=related_id,
        dedupe_key=key,
    )
    db.add(alert)
    db.flush()
    return alert


def prune(db: Session, keep: int = MAX_ALERTS) -> int:
    """Drop the oldest read/resolved alerts once the feed gets long."""
    total = db.query(Alert).count()
    if total <= keep:
        return 0
    stale = (
        db.query(Alert.id)
        .order_by(Alert.id.asc())
        .limit(total - keep)
        .all()
    )
    ids = [row[0] for row in stale]
    db.query(Alert).filter(Alert.id.in_(ids)).delete(synchronize_session=False)
    return len(ids)


def cutoff(hours: float) -> datetime:
    return clock.now().replace(tzinfo=None) - timedelta(hours=hours)
