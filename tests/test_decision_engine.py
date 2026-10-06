"""Unit tests for the §21 rule table and the §22 workflow state machine."""

from __future__ import annotations

import pytest

from app.services import decision_engine as de


class TestRuleTable:
    """One test per row of the §21 table."""

    def test_high_confidence_low_impact_auto_executes(self):
        decision = de.decide(confidence_score=0.85, impact_inr=18_000.0)
        assert decision.confidence == "HIGH"
        assert decision.impact_band == "LOW"
        assert decision.status == de.AUTO_EXECUTED

    @pytest.mark.parametrize("confidence", [0.45, 0.65, 0.95])
    def test_medium_impact_always_needs_approval(self, confidence):
        decision = de.decide(confidence_score=confidence, impact_inr=60_000.0)
        assert decision.impact_band == "MEDIUM"
        assert decision.status == de.PENDING_APPROVAL

    @pytest.mark.parametrize("confidence", [0.41, 0.75, 0.99])
    def test_high_impact_is_never_auto_executed(self, confidence):
        """The safety property from §34: no HIGH-impact action without a human."""
        decision = de.decide(confidence_score=confidence, impact_inr=305_000.0)
        assert decision.impact_band == "HIGH"
        assert decision.status == de.PENDING_APPROVAL

    @pytest.mark.parametrize("impact", [1_000.0, 60_000.0, 500_000.0])
    def test_low_confidence_always_needs_approval(self, impact):
        """LOW confidence overrides the auto-execute row, even at tiny impact."""
        decision = de.decide(confidence_score=0.2, impact_inr=impact)
        assert decision.confidence == "LOW"
        assert decision.status == de.PENDING_APPROVAL
        assert "Low model confidence" in decision.rationale


def test_impact_band_boundaries():
    assert de.classify_impact(24_999.0) == "LOW"
    assert de.classify_impact(25_000.0) == "MEDIUM"
    assert de.classify_impact(100_000.0) == "MEDIUM"
    assert de.classify_impact(100_001.0) == "HIGH"


def test_confidence_band_boundaries():
    assert de.classify_confidence(0.39) == "LOW"
    assert de.classify_confidence(0.40) == "MEDIUM"
    assert de.classify_confidence(0.69) == "MEDIUM"
    assert de.classify_confidence(0.70) == "HIGH"


def test_confidence_is_the_probability_margin_from_half():
    assert de.confidence_from_probabilities(0.82, 0.21) == pytest.approx(0.64, abs=0.01)
    # Two coin flips carry no confidence at all.
    assert de.confidence_from_probabilities(0.5, 0.5) == pytest.approx(0.0)


def test_flagship_impact_stops_for_approval():
    """§21: the ₹3,05,000 demo impact must always reach the manager."""
    decision = de.decide(confidence_score=0.64, impact_inr=305_000.0)
    assert decision.status == de.PENDING_APPROVAL


class TestWorkflowLifecycle:
    def test_approve_executes_the_reroute_and_flips_the_route(self, db):
        from app.models import Shipment
        from app.simulation import engine

        for event in ("traffic_incident", "refrigeration_degradation", "weather_deterioration"):
            engine.trigger_event(db, event)

        shipment = db.query(Shipment).filter(Shipment.code == "SC-1042").one()
        workflow = de.open_workflow(db, "REROUTE", shipment_id=shipment.id)
        assert workflow is not None
        assert workflow.status == de.PENDING_APPROVAL

        proposed_route_id = workflow.proposed_route_id
        de.approve(db, workflow)
        db.commit()
        db.refresh(shipment)

        assert workflow.status == de.EXECUTED
        assert workflow.resolved_at is not None
        assert shipment.status == "REROUTED"
        selected = [r for r in shipment.routes if r.is_selected]
        assert len(selected) == 1
        assert selected[0].id == proposed_route_id
        assert shipment.loss_avoided_inr > 0

    def test_reject_takes_no_action(self, db):
        from app.models import Shipment
        from app.simulation import engine

        engine.trigger_event(db, "traffic_incident")
        shipment = db.query(Shipment).filter(Shipment.code == "SC-1042").one()
        workflow = de.open_workflow(db, "REROUTE", shipment_id=shipment.id)
        route_before = next(r for r in shipment.routes if r.is_selected).id

        de.reject(db, workflow, note="Driver already past the junction.")
        db.commit()
        db.refresh(shipment)

        assert workflow.status == de.REJECTED
        assert shipment.status != "REROUTED"
        assert next(r for r in shipment.routes if r.is_selected).id == route_before

    def test_resolved_workflows_are_immutable(self, db):
        from app.simulation import engine

        engine.trigger_event(db, "traffic_incident")
        workflow = de.open_workflow(db, "REROUTE")
        de.reject(db, workflow)
        db.commit()

        # A second approve must not resurrect it (§23).
        de.approve(db, workflow)
        assert workflow.status == de.REJECTED

    def test_override_is_logged_distinctly(self, db):
        from app.models import Shipment
        from app.simulation import engine

        engine.trigger_event(db, "traffic_incident")
        shipment = db.query(Shipment).filter(Shipment.code == "SC-1042").one()
        workflow = de.open_workflow(db, "REROUTE", shipment_id=shipment.id)
        other = next(r for r in shipment.routes if r.id != workflow.proposed_route_id)

        de.approve(db, workflow, override_route_id=other.id)
        db.commit()

        assert workflow.status == de.OVERRIDDEN
        assert workflow.executed_route_id == other.id
        assert "Overridden by ops manager" in workflow.resolution_note
