"""API tests — one happy path per §14 endpoint, plus the validation cases §34
promises (malformed simulation events, unknown ids)."""

from __future__ import annotations

import pytest


def _hero_id(client) -> int:
    shipments = client.get("/api/shipments").json()
    return next(s["id"] for s in shipments if s["code"] == "SC-1042")


def test_health_reports_model_load_state(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert set(body["models"]) == {
        "forecast_gbr.joblib",
        "maintenance_isolation_forest.joblib",
        "maintenance_failure_gbc.joblib",
        "spoilage_gbc.joblib",
    }


def test_dashboard_returns_every_kpi(client):
    body = client.get("/api/dashboard").json()
    assert set(body["kpis"]) >= {
        "active_shipments",
        "shipments_at_risk",
        "critical_alerts",
        "value_at_risk_inr",
        "loss_avoided_inr",
        "machines_at_risk",
    }
    assert body["kpis"]["active_shipments"] == 8
    assert body["shipments"]
    assert body["disclaimer"]


def test_list_shipments(client):
    body = client.get("/api/shipments").json()
    assert len(body) == 8
    hero = next(s for s in body if s["code"] == "SC-1042")
    assert hero["melt_index"] < 20
    assert hero["status"] == "SAFE"
    assert hero["machine_code"] == "RF-204"


def test_shipment_detail_carries_routes_and_explanation(client):
    body = client.get(f"/api/shipments/{_hero_id(client)}").json()
    assert len(body["routes"]) == 2
    assert body["explanation"]["bullets"]
    assert body["recommendation_text"]
    assert body["current_route_evaluation"]["expected_loss_inr"] > 0
    assert "pending_reroute_workflow" in body


def test_shipment_risk_breakdown(client):
    body = client.get(f"/api/shipments/{_hero_id(client)}/risk").json()
    assert set(body["components"]) == {
        "temperature_risk",
        "refrigeration_risk",
        "traffic_risk",
        "weather_risk",
        "shelf_life_risk",
        "eta_risk",
    }
    assert body["explanation"]["status"] == "SAFE"


def test_shipment_routes_endpoint_compares_expected_loss(client):
    body = client.get(f"/api/shipments/{_hero_id(client)}/routes").json()
    assert len(body["routes"]) == 2
    assert body["recommended_route_id"] is not None
    for route in body["routes"]:
        assert "expected_loss_inr" in route
        assert "arrives_within_shelf_life" in route


def test_shipment_404(client):
    assert client.get("/api/shipments/99999").status_code == 404


def test_list_and_detail_machines(client):
    machines = client.get("/api/machines").json()
    assert len(machines) == 12
    rf204 = next(m for m in machines if m["code"] == "RF-204")

    detail = client.get(f"/api/machines/{rf204['id']}").json()
    assert detail["readings"]
    assert detail["explanation"]["bullets"]
    assert "SC-1042" in detail["assigned_shipments"]


def test_manual_maintenance_workflow(client):
    machines = client.get("/api/machines").json()
    cm301 = next(m for m in machines if m["code"] == "CM-301")
    body = client.post(
        f"/api/machines/{cm301['id']}/maintenance-workflow", json={"note": "Manual check"}
    ).json()
    assert body["workflow_type"] == "MAINTENANCE"
    assert body["status"] == "PENDING_APPROVAL"


def test_forecast_and_inventory(client):
    forecast = client.get("/api/forecast").json()
    assert len(forecast["products"]) == 4
    for product in forecast["products"]:
        assert product["predicted_demand"] > 0
        assert product["model_source"] in {"gradient_boosting", "moving_average_7d"}
        assert 0.0 <= product["stockout_probability"] <= 1.0
        assert len(product["daily"]) == 21 + forecast["horizon_days"]

    inventory = client.get("/api/inventory").json()
    assert len(inventory) == 4
    assert all(row["stock_value_inr"] > 0 for row in inventory)


def test_alerts(client):
    alerts = client.get("/api/alerts").json()
    assert alerts
    assert {"severity", "message", "created_at"} <= set(alerts[0])


def test_scenarios_endpoint_drives_the_control_panel(client):
    body = client.get("/api/simulation/scenarios").json()
    assert body["escalation_sequence"] == [
        "traffic_incident",
        "refrigeration_degradation",
        "weather_deterioration",
    ]
    # The repair scenario is offered too, so recovery can be demonstrated.
    assert "maintenance_completed" in body["demo_sequence"]
    assert body["hero"]["shipment"] == "SC-1042"
    # Every button advertises the ROOT CAUSE it changes, and none of them can
    # name a consequence.
    for scenario in body["scenarios"]:
        assert scenario["cause"] in body["causes"]
        assert "expected_melt_index" not in scenario


def test_trigger_event_returns_the_new_state_immediately(client):
    """§25: the response already reflects the recalculation — no poll needed."""
    body = client.post(
        "/api/simulation/trigger-event", json={"event_type": "traffic_incident"}
    ).json()
    hero = next(s for s in body["shipments"] if s["code"] == "SC-1042")
    assert hero["melt_index"] > 20  # the incident moved it, derived not assigned
    assert body["cause"]["field"] == "incident_delay_minutes"
    assert body["cause"]["amount"] > 0
    assert body["simulated_minutes_advanced"] > 0


def test_trigger_event_rejects_an_unknown_event_type(client):
    response = client.post(
        "/api/simulation/trigger-event", json={"event_type": "not_a_real_event"}
    )
    assert response.status_code == 400
    assert "Unknown event_type" in response.json()["detail"]


def test_trigger_event_rejects_a_malformed_body(client):
    """§34: Pydantic rejects it before it reaches the engine."""
    assert client.post("/api/simulation/trigger-event", json={}).status_code == 422
    assert (
        client.post(
            "/api/simulation/trigger-event",
            json={"event_type": "traffic_incident", "target_id": -5},
        ).status_code
        == 422
    )


def test_full_demo_sequence_over_http(client):
    """The §35 demo script, driven entirely through the API."""
    for event in ("traffic_incident", "refrigeration_degradation", "weather_deterioration"):
        client.post("/api/simulation/trigger-event", json={"event_type": event})

    hero_id = _hero_id(client)
    detail = client.get(f"/api/shipments/{hero_id}").json()
    assert detail["status"] == "CRITICAL"
    assert detail["melt_index"] > 80
    # Expected loss is the product of value and probability, not a stored figure.
    assert detail["expected_loss_inr"] == pytest.approx(
        detail["shipment_value_inr"] * detail["spoilage_probability"], rel=0.02
    )
    assert detail["potential_loss_avoided_inr"] > 100_000.0
    assert detail["pending_reroute_workflow"]["status"] == "PENDING_APPROVAL"
    # The reefer's maintenance ticket is pending on this shipment too — the
    # Approve Reroute button must not pick it up by accident.
    assert len(detail["related_pending_workflows"]) > 1

    workflow_id = detail["pending_reroute_workflow"]["id"]
    approved = client.post(f"/api/workflows/{workflow_id}/approve", json={}).json()
    assert approved["status"] == "EXECUTED"

    after = client.get(f"/api/shipments/{hero_id}").json()
    assert after["status"] == "REROUTED"
    assert after["loss_avoided_inr"] > 100_000.0
    assert after["expected_loss_inr"] < detail["expected_loss_inr"]

    # The maintenance ticket was auto-created alongside (§35 step 9).
    workflows = client.get("/api/workflows").json()
    maintenance = [w for w in workflows if w["workflow_type"] == "MAINTENANCE"]
    assert maintenance
    assert any(w["workflow_type"] == "SPARE_PART_PURCHASE" for w in workflows)


def test_workflow_approve_is_idempotent_and_guarded(client):
    client.post("/api/simulation/trigger-event", json={"event_type": "traffic_incident"})
    pending = [
        w for w in client.get("/api/workflows").json() if w["status"] == "PENDING_APPROVAL"
    ]
    workflow_id = pending[0]["id"]

    assert client.post(f"/api/workflows/{workflow_id}/approve", json={}).status_code == 200
    # Second attempt is refused rather than silently re-executing (§23).
    assert client.post(f"/api/workflows/{workflow_id}/approve", json={}).status_code == 409
    assert client.post("/api/workflows/99999/approve", json={}).status_code == 404


def test_workflow_reject(client):
    client.post("/api/simulation/trigger-event", json={"event_type": "traffic_incident"})
    pending = [
        w
        for w in client.get("/api/workflows").json()
        if w["status"] == "PENDING_APPROVAL" and w["workflow_type"] == "REROUTE"
    ]
    body = client.post(
        f"/api/workflows/{pending[0]['id']}/reject", json={"note": "Driver past junction"}
    ).json()
    assert body["status"] == "REJECTED"


def test_workflow_summary_counts_what_the_workflows_show(client):
    client.post("/api/simulation/trigger-event", json={"event_type": "traffic_incident"})
    workflows = client.get("/api/workflows").json()
    summary = client.get("/api/workflows/summary").json()

    assert summary["total"] == len(workflows)
    assert summary["pending"] == sum(1 for w in workflows if w["status"] == "PENDING_APPROVAL")
    assert summary["pending_impact_inr"] == round(
        sum(w["impact_inr"] for w in workflows if w["status"] == "PENDING_APPROVAL")
    )
    if summary["automation_rate"] is not None:
        assert 0.0 <= summary["automation_rate"] <= 1.0

    # Approving moves one decision from pending to human-resolved.
    pending = next(w for w in workflows if w["status"] == "PENDING_APPROVAL")
    client.post(f"/api/workflows/{pending['id']}/approve", json={})
    after = client.get("/api/workflows/summary").json()
    assert after["pending"] == summary["pending"] - 1
    assert after["human_resolved"] == summary["human_resolved"] + 1
    assert after["median_seconds_to_human_decision"] is not None


def test_direct_reroute_rejects_a_route_from_another_shipment(client):
    shipments = client.get("/api/shipments").json()
    hero = next(s for s in shipments if s["code"] == "SC-1042")
    other = next(s for s in shipments if s["code"] != "SC-1042")
    foreign_route = client.get(f"/api/shipments/{other['id']}/routes").json()["routes"][0]

    response = client.post(
        f"/api/shipments/{hero['id']}/reroute", json={"route_id": foreign_route["route_id"]}
    )
    assert response.status_code == 400


def test_reset_restores_the_baseline_over_http(client):
    client.post("/api/simulation/trigger-event", json={"event_type": "traffic_incident"})
    assert client.post("/api/simulation/reset", json={}).json()["reset"] is True
    shipments = client.get("/api/shipments").json()
    hero = next(s for s in shipments if s["code"] == "SC-1042")
    assert hero["melt_index"] < 20
    assert hero["status"] == "SAFE"


def test_copilot_answers_from_structured_data(client):
    body = client.get("/api/copilot/ask", params={"q": "What is the risk on SC-1042?"}).json()
    assert "SC-1042" in body["answer"]
    assert body["engine"] == "rule-based"

    machine = client.get("/api/copilot/ask", params={"q": "How is RF-204 doing?"}).json()
    assert "RF-204" in machine["answer"]

    stock = client.get("/api/copilot/ask", params={"q": "Do I need to reorder stock?"}).json()
    assert stock["sources"]
