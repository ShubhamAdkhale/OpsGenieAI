"""Loads finish their trips, and the next load goes out on the same lane."""

from __future__ import annotations

from app.models import DELIVERED, Shipment, Workflow
from app.services import decision_engine
from app.simulation import engine, physics, scenarios


def _hero(db):
    return db.query(Shipment).filter(Shipment.code == "SC-1042").one()


def _arrive(db, shipment):
    """Put a load at its destination and let one tick notice."""
    shipment.progress_fraction = 1.0
    db.flush()
    physics.tick(db)


def test_the_hero_is_still_on_the_road_at_the_climax(db):
    # The board says "predicted to spoil before delivery" at the climax, so the
    # truck must not already be at the consignee. It used to be.
    for event in scenarios.ESCALATION_SEQUENCE:
        engine.trigger_event(db, event)
    hero = _hero(db)
    assert hero.status == "CRITICAL"
    assert hero.in_transit
    assert hero.progress_fraction < 0.9


def test_an_arrived_load_is_delivered_and_its_lane_gets_the_next_load(db):
    load = db.query(Shipment).filter(Shipment.code == "SC-1039").one()
    lane = (load.origin_city, load.destination_city, load.product_id, load.machine_id)
    _arrive(db, load)

    assert load.status == DELIVERED
    successor = (
        db.query(Shipment)
        .filter(
            Shipment.origin_city == lane[0],
            Shipment.destination_city == lane[1],
            Shipment.status != DELIVERED,
        )
        .one()
    )
    assert successor.code != load.code
    assert (successor.product_id, successor.machine_id) == lane[2:]
    # Leaves the dock in spec, at the setpoint, at the start of the lane.
    assert successor.minutes_outside_safe_range == 0.0
    assert successor.progress_fraction < 0.1
    assert successor.cargo_temperature_c <= successor.product.safe_transit_temp_c
    assert successor.routes and successor.assessments  # routed and scored at once


def test_the_network_keeps_its_size(db):
    before = db.query(Shipment).filter(Shipment.status != DELIVERED).count()
    for code in ("SC-1039", "SC-1051", "SC-1061"):
        _arrive(db, db.query(Shipment).filter(Shipment.code == code).one())
    assert db.query(Shipment).filter(Shipment.status != DELIVERED).count() == before


def test_delivered_loads_leave_the_board_but_stay_on_the_record(client, db):
    _arrive(db, db.query(Shipment).filter(Shipment.code == "SC-1039").one())
    db.commit()
    body = client.get("/api/dashboard").json()
    assert "SC-1039" not in {s["code"] for s in body["shipments"]}
    assert body["kpis"]["delivered"] == 1
    assert client.get("/api/shipments").status_code == 200


def test_a_decision_left_open_on_a_delivered_load_expires(db):
    load = db.query(Shipment).filter(Shipment.code == "SC-1044").one()
    pending = (
        db.query(Workflow)
        .filter(
            Workflow.related_shipment_id == load.id,
            Workflow.status == decision_engine.PENDING_APPROVAL,
        )
        .all()
    )
    assert pending, "baseline should hold an open reroute for the ice-cream load"
    _arrive(db, load)
    for workflow in pending:
        db.refresh(workflow)
        assert workflow.status == decision_engine.EXPIRED
        assert not workflow.requires_approval_now()
