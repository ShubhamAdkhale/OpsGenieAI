from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.serializers import machine_detail, machine_summary, workflow_payload
from app.database import get_db
from app.models import Machine
from app.schemas import MaintenanceWorkflowRequest
from app.services import decision_engine, maintenance

router = APIRouter(prefix="/machines", tags=["machines"])


def _get_machine(db: Session, machine_id: int) -> Machine:
    machine = db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")
    return machine


@router.get("")
def list_machines(db: Session = Depends(get_db)) -> list[dict]:
    machines = db.query(Machine).order_by(Machine.health_score.asc()).all()
    return [machine_summary(m) for m in machines]


@router.get("/{machine_id}")
def get_machine(machine_id: int, db: Session = Depends(get_db)) -> dict:
    return machine_detail(db, _get_machine(db, machine_id))


@router.post("/{machine_id}/maintenance-workflow")
def create_maintenance_workflow(
    machine_id: int,
    payload: MaintenanceWorkflowRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Manually raise a maintenance workflow — mirrors the auto-created one (§14)."""
    machine = _get_machine(db, machine_id)
    assessment = maintenance.assess(machine)
    if assessment.insufficient_data:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{machine.code} has fewer than "
                f"{maintenance.MIN_READINGS_FOR_PREDICTION} sensor readings — "
                "prediction skipped rather than guessed."
            ),
        )
    workflow = decision_engine.create_maintenance_workflow(db, machine, assessment)
    if payload.note:
        workflow.resolution_note = f"{workflow.resolution_note} | {payload.note}".strip(" |")
    db.commit()
    return workflow_payload(workflow)
