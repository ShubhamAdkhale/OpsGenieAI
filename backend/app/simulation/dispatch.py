"""Arrivals and dispatch: loads finish their trips, and the next load goes out.

Nothing in the twin used to finish. A truck that reached its destination sat at
100% progress with its shelf life still burning, until the board filled with
loads at "0.0 h shelf life left" that were, on the map, already parked at the
consignee. That is the most visible way a simulation gives itself away.

Now a load that reaches 100% is DELIVERED: it gets an arrival alert saying
whether it arrived in spec, drops out of everything that describes the network
right now, and stays on the record. Its lane immediately gets a new load - the
same product on the same reefer, as a truck that returns and reloads would -
leaving the dock in spec with a new shipment code. The network keeps its size
and keeps moving, instead of emptying or decaying.

Open decisions about a delivered load are closed as EXPIRED: approving a reroute
for a truck that is already at the consignee would be nonsense.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import DELIVERED, Machine, Product, Shipment, Workflow
from app.services.alerts import raise_alert
from app.simulation import clock

CODE_PATTERN = re.compile(r"^SC-(\d+)$")


def _next_code(db: Session) -> str:
    numbers = [
        int(match.group(1))
        for (code,) in db.query(Shipment.code).all()
        if (match := CODE_PATTERN.match(code or ""))
    ]
    return f"SC-{max(numbers, default=1000) + 1}"


def _lane_spec(shipment: Shipment) -> dict | None:
    """The seed spec for this shipment's lane and product, if it has one."""
    from app.seed_config import SHIPMENTS

    product_name = shipment.product.name if shipment.product else None
    for spec in SHIPMENTS:
        if (
            spec["origin_city"] == shipment.origin_city
            and spec["destination_city"] == shipment.destination_city
            and spec["product"] == product_name
        ):
            return spec
    return None


def _arrival_message(shipment: Shipment) -> str:
    condition = (
        "arrived in spec"
        if shipment.minutes_outside_safe_range <= 0
        else f"arrived after {shipment.minutes_outside_safe_range:.0f} min outside the safe range"
    )
    return (
        f"{shipment.code} delivered to {shipment.destination_city}: {condition}, "
        f"{shipment.remaining_shelf_life_hours:.1f} h of shelf life left."
    )


def _expire_open_decisions(db: Session, shipment: Shipment) -> None:
    from app.services.decision_engine import EXPIRED, OPEN_STATUSES

    for workflow in (
        db.query(Workflow)
        .filter(
            Workflow.related_shipment_id == shipment.id,
            Workflow.status.in_(OPEN_STATUSES),
        )
        .all()
    ):
        workflow.status = EXPIRED
        workflow.resolved_at = clock.now()
        workflow.resolution_note = "Load delivered before a decision was taken."


def deliver_arrivals(db: Session) -> list[Shipment]:
    """Deliver every load that has reached its destination; dispatch the next ones.

    Returns the newly dispatched loads, so the caller can derive their routes
    and risk in the same tick rather than showing them unscored for one.
    """
    from app.seeding import add_shipment

    arrived = (
        db.query(Shipment)
        .filter(Shipment.status != DELIVERED, Shipment.progress_fraction >= 1.0)
        .all()
    )
    dispatched: list[Shipment] = []
    for shipment in arrived:
        shipment.status = DELIVERED
        _expire_open_decisions(db, shipment)
        raise_alert(
            db,
            "INFO",
            _arrival_message(shipment),
            related_type="shipment",
            related_id=shipment.id,
            dedupe=False,
        )

        spec = _lane_spec(shipment)
        if spec is None:
            continue
        product = shipment.product or db.query(Product).filter_by(name=spec["product"]).one()
        machine = (
            db.query(Machine).filter_by(code=spec["machine"]).one_or_none()
            if spec.get("machine")
            else None
        )
        # The demo's scripted load is SC-1042 alone; its successor is ordinary.
        dispatched.append(
            add_shipment(
                db,
                spec,
                product=product,
                machine=machine,
                code=_next_code(db),
                is_hero=False,
                fresh=True,
            )
        )
    db.flush()
    return dispatched
