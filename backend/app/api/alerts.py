from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.serializers import alert_payload
from app.database import get_db
from app.models import Alert

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    limit: int = Query(default=40, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    alerts = db.query(Alert).order_by(Alert.id.desc()).limit(limit).all()
    return [alert_payload(a) for a in alerts]


@router.post("/mark-read")
def mark_all_read(db: Session = Depends(get_db)) -> dict:
    updated = db.query(Alert).filter(Alert.is_read.is_(False)).update({"is_read": True})
    db.commit()
    return {"marked_read": updated}
