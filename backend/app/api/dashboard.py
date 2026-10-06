from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.serializers import (
    iso,
    DISCLAIMER,
    alert_payload,
    machine_summary,
    shipment_summary,
    workflow_payload,
)
from app.config import settings
from app.database import get_db
from app.models import DELIVERED, Alert, Machine, Product, RiskAssessment, Shipment, Workflow
from app.services import forecasting, priority, provenance
from app.simulation import clock, lifecycle, physics

router = APIRouter(tags=["dashboard"])

AT_RISK_STATUSES = {"HIGH", "CRITICAL"}
MACHINE_AT_RISK_STATUSES = {"WARNING", "CRITICAL"}

# Points plotted in the control tower's trend chart.
TREND_POINTS = 40


def _sim_clock(sim_minutes: float) -> str:
    """The simulated wall clock, so congestion and the diurnal curve make sense."""
    total = int(sim_minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _trend(db: Session, summary: dict) -> dict:
    """Melt Index history for whichever shipment is currently top priority.

    Read straight off the RiskAssessment audit trail, so the chart is the same
    data the explainability panel uses rather than a second source of truth.
    """
    subject = (summary or {}).get("subject")
    if not subject:
        return {"subject_code": None, "series": []}
    rows = (
        db.query(RiskAssessment)
        .filter(RiskAssessment.shipment_id == subject["id"])
        .order_by(RiskAssessment.id.desc())
        .limit(TREND_POINTS)
        .all()
    )
    return {
        "subject_code": subject["code"],
        "series": [
            {
                "computed_at": iso(r.computed_at),
                "melt_index": round(r.melt_index, 1),
                "temperature_risk": round(r.temperature_risk, 1),
                "refrigeration_risk": round(r.refrigeration_risk, 1),
                "traffic_risk": round(r.traffic_risk, 1),
                "weather_risk": round(r.weather_risk, 1),
            }
            for r in reversed(rows)
        ],
    }


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)) -> dict:
    """The aggregated numbers behind the top KPI cards (§14, §27)."""
    everything = db.query(Shipment).all()
    # Delivered loads are history: they leave the map, the table and every
    # figure that describes the network now, but loss avoided on them counts.
    shipments = [s for s in everything if s.status != DELIVERED]
    delivered = [s for s in everything if s.status == DELIVERED]
    machines = db.query(Machine).all()
    workflows = db.query(Workflow).order_by(Workflow.id.desc()).all()

    active = [s for s in shipments if s.status != "REROUTED"]
    at_risk = [s for s in active if s.status in AT_RISK_STATUSES]
    critical_alerts = (
        db.query(Alert).filter(Alert.severity == "CRITICAL", Alert.is_read.is_(False)).count()
    )
    machines_at_risk = [m for m in machines if m.status in MACHINE_AT_RISK_STATUSES]
    pending = [w for w in workflows if w.status == "PENDING_APPROVAL"]

    value_at_risk = sum(float(s.expected_loss_inr) for s in active)
    loss_avoided = sum(float(s.loss_avoided_inr) for s in everything)
    total_in_transit = sum(float(s.shipment_value_inr) for s in active)

    forecasts = [
        forecasting.forecast_product(db, p).to_payload()
        for p in db.query(Product).order_by(Product.id).all()
    ]
    stockout_risks = [f for f in forecasts if f["stockout_probability"] >= 0.5]

    state = physics.environment(db)
    summary = priority.summarize(db)

    return {
        # THE decision, chosen and worded in the backend. The dashboard renders
        # this; it does not rank, threshold or compute anything itself.
        "priority": summary,
        "provenance": provenance.summary(db),
        "environment": {
            "sim_minutes": state.sim_minutes,
            "sim_clock": _sim_clock(state.sim_minutes),
            "tick_count": state.tick_count,
            "weather_mode": state.weather_mode,
            "ambient_offset_c": round(state.ambient_offset_c, 2),
            "tick_seconds": settings.physics_tick_seconds,
            "sim_minutes_per_tick": settings.sim_minutes_per_tick,
            "physics_enabled": settings.physics_enabled,
            "episode": lifecycle.episode_payload(state.sim_minutes),
            "twin_time": iso(clock.now()),
        },
        "trend": _trend(db, summary),
        "kpis": {
            "active_shipments": len(active),
            "shipments_at_risk": len(at_risk),
            "critical_alerts": critical_alerts,
            "value_at_risk_inr": round(value_at_risk),
            "loss_avoided_inr": round(loss_avoided),
            "machines_at_risk": len(machines_at_risk),
            "pending_approvals": len(pending),
            "total_value_in_transit_inr": round(total_in_transit),
            "products_at_stockout_risk": len(stockout_risks),
            "delivered": len(delivered),
            "delivered_in_spec": sum(1 for s in delivered if s.minutes_outside_safe_range <= 0),
        },
        "shipments": [shipment_summary(s) for s in sorted(
            shipments, key=lambda s: s.melt_index, reverse=True
        )],
        "machines": [
            machine_summary(m) for m in sorted(machines, key=lambda m: m.health_score)
        ],
        "alerts": [
            alert_payload(a)
            for a in db.query(Alert).order_by(Alert.id.desc()).limit(12).all()
        ],
        "recommendations": [
            {
                "workflow_id": w.id,
                "workflow_type": w.workflow_type,
                "status": w.status,
                "confidence": w.confidence,
                "impact_inr": w.impact_inr,
                "text": w.recommendation_text,
                "shipment_id": w.related_shipment_id,
                "machine_id": w.related_machine_id,
            }
            for w in workflows[:6]
        ],
        "workflow_activity": {
            "total": len(workflows),
            "pending_approval": len(pending),
            "auto_executed": len([w for w in workflows if w.status == "AUTO_EXECUTED"]),
            "executed": len([w for w in workflows if w.status in {"EXECUTED", "OVERRIDDEN"}]),
            "rejected": len([w for w in workflows if w.status == "REJECTED"]),
            "recent": [workflow_payload(w) for w in workflows[:5]],
        },
        "forecast_summary": [
            {
                "product_name": f["product_name"],
                "predicted_demand": f["predicted_demand"],
                "current_stock": f["current_stock"],
                "projected_inventory": f["projected_inventory"],
                "stockout_probability": f["stockout_probability"],
                "recommended_reorder_qty": f["recommended_reorder_qty"],
            }
            for f in forecasts
        ],
        "disclaimer": DISCLAIMER,
    }
