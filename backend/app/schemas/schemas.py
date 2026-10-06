"""Pydantic request schemas.

§34: every POST body is validated here, so a malformed simulation event or an
unknown workflow id is rejected with a 4xx instead of reaching the engines.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SimulationTriggerRequest(BaseModel):
    event_type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="One of the scripted event types from GET /api/simulation/scenarios.",
    )
    target_id: int | None = Field(
        default=None,
        ge=1,
        description="Optional explicit target. Defaults to the scenario's own hero target.",
    )


class RerouteRequest(BaseModel):
    route_id: int = Field(..., ge=1, description="The route to switch the shipment onto.")


class ApproveRequest(BaseModel):
    override_route_id: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Set to approve with a DIFFERENT route than the AI recommended. "
            "Logged as OVERRIDDEN (§23)."
        ),
    )


class RejectRequest(BaseModel):
    note: str = Field(default="", max_length=500)


class MaintenanceWorkflowRequest(BaseModel):
    note: str = Field(default="", max_length=500)
