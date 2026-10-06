"""Single source of truth for seed data AND the scripted demo arc (§7 §29).

`data/seed.py`, the training scripts and `simulation/scenarios.py` all read
from here, so the demo numbers can never drift apart between the database, the
models and the trigger buttons.

EVERY value below is synthetic. No real company, customer, vehicle or sensor is
represented. Monetary values are in Indian Rupees.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Geography (lat/lon for the Leaflet map)
# ---------------------------------------------------------------------------

CITIES: dict[str, tuple[float, float]] = {
    "Mumbai": (19.0760, 72.8777),
    "Pune": (18.5204, 73.8567),
    "Delhi": (28.6139, 77.2090),
    "Bengaluru": (12.9716, 77.5946),
    "Hyderabad": (17.3850, 78.4867),
    "Ahmedabad": (23.0225, 72.5714),
    "Surat": (21.1702, 72.8311),
    "Chennai": (13.0827, 80.2707),
    "Nagpur": (21.1458, 79.0882),
}

# Lane waypoints. Weather is fetched PER WAYPOINT, not per shipment, so two
# routes out of the same city can sit under different conditions -- which is
# what lets the optimizer prefer a longer lane in better weather.
WAYPOINTS: dict[str, tuple[float, float]] = {
    "Lonavala": (18.7546, 73.4062),
    "Chakan": (18.7606, 73.8636),
    "Jaipur": (26.9124, 75.7873),
    "Ajmer": (26.4499, 74.6399),
    "Hosur": (12.7409, 77.8253),
    "Kolar": (13.1357, 78.1325),
    "Kurnool": (15.8281, 78.0373),
    "Raichur": (16.2120, 77.3439),
    "Vapi": (20.3893, 72.9106),
    "Valsad": (20.5992, 72.9342),
    "Udaipur": (24.5854, 73.7125),
    "Kota": (25.2138, 75.8648),
    "Adilabad": (19.6640, 78.5320),
    "Warangal": (17.9689, 79.5941),
}

# Cooling-efficiency points a healthy unit loses per operating hour. Normal
# wear -- slow enough that a machine drifts over a long demo but nothing
# alarming happens on its own.
BASELINE_DEGRADATION_RATE = 0.02

# ---------------------------------------------------------------------------
# Products (§29). `unit_shelf_life_hours` is the IN-TRANSIT safe window, which
# is what §18's ShelfLifeRisk divides by — not the retail shelf life.
# ---------------------------------------------------------------------------

PRODUCTS: list[dict] = [
    {
        "name": "Frozen Chicken",
        "category": "Frozen Meat",
        # Codex General Standard for Quick-Frozen Foods (CXS 8-1976 / CXG 8):
        # held at -18 C or colder, brief rises to no warmer than -15 C in
        # distribution. -15 C is therefore the transit limit for frozen goods.
        "safe_transit_temp_c": -15.0,
        "daily_demand_rate": 320.0,
        "unit_shelf_life_hours": 24.0,
        "unit_value_inr": 220.0,
        "warehouse_city": "Mumbai",
        "current_stock": 1850.0,
        # demand_series parameters
        "base": 320.0,
        "weekly_amplitude": 45.0,
        "trend_per_day": 0.9,
        "noise_sd": 22.0,
    },
    {
        "name": "Paneer",
        "category": "Dairy",
        "safe_transit_temp_c": 4.0,  # chilled dairy: 0-4 C
        "daily_demand_rate": 210.0,
        "unit_shelf_life_hours": 36.0,
        "unit_value_inr": 340.0,
        "warehouse_city": "Pune",
        "current_stock": 1200.0,
        "base": 210.0,
        "weekly_amplitude": 30.0,
        "trend_per_day": 0.4,
        "noise_sd": 15.0,
    },
    {
        "name": "Frozen Peas",
        "category": "Frozen Vegetables",
        "safe_transit_temp_c": -15.0,  # same quick-frozen limit as above
        "daily_demand_rate": 480.0,
        "unit_shelf_life_hours": 48.0,
        "unit_value_inr": 90.0,
        "warehouse_city": "Bengaluru",
        "current_stock": 4200.0,
        "base": 480.0,
        "weekly_amplitude": 40.0,
        "trend_per_day": -0.3,
        "noise_sd": 28.0,
    },
    {
        "name": "Ice Cream Tubs",
        "category": "Frozen Desserts",
        "safe_transit_temp_c": -15.0,
        "daily_demand_rate": 265.0,
        "unit_shelf_life_hours": 18.0,
        "unit_value_inr": 260.0,
        "warehouse_city": "Delhi",
        "current_stock": 900.0,
        "base": 265.0,
        "weekly_amplitude": 70.0,
        "trend_per_day": 1.6,
        "noise_sd": 24.0,
    },
]

# ---------------------------------------------------------------------------
# Machines (§29). The spec lists RF-201..RF-205; we run RF-201..RF-209 so every
# active shipment has its own reefer plus one standby, and keep CV-101/102 and
# CM-301 as the non-reefer equipment the maintenance page also monitors.
#
# The fleet is mostly HEALTHY on purpose. A real control tower is quiet: most
# units fine, a couple being watched, one crisis. An earlier seed had half the
# fleet in WARNING, so "6 units need attention" greeted a visitor before
# anything had happened and the one real story had nowhere to stand out.
# The three that are not healthy each carry a part of the demo: RF-202 (the
# ice-cream load at baseline), RF-204 (the hero) and CM-301 (a worn compressor
# awaiting overhaul - high condition risk, no fast decline).
# ---------------------------------------------------------------------------

HERO_MACHINE_CODE = "RF-204"
STANDBY_MACHINE_CODE = "RF-205"

MACHINES: list[dict] = [
    {"code": "RF-201", "type": "refrigeration_unit", "location": "Mumbai Cold Hub", "health_score": 92.0},
    {"code": "RF-202", "type": "refrigeration_unit", "location": "Delhi Cold Hub", "health_score": 68.0},
    {"code": "RF-203", "type": "refrigeration_unit", "location": "Bengaluru Cold Hub", "health_score": 85.0},
    # HERO: pre-seeded mid-degradation so it is ready for the scripted demo.
    {"code": "RF-204", "type": "refrigeration_unit", "location": "Mumbai Cold Hub", "health_score": 74.0, "is_hero": True},
    # Standby at Chakan — the unit Route B swaps the load onto. Deliberately
    # not assigned to any shipment.
    {"code": "RF-205", "type": "refrigeration_unit", "location": "Chakan Cold Hub", "health_score": 88.0, "is_hero": True},
    {"code": "RF-206", "type": "refrigeration_unit", "location": "Hyderabad Cold Hub", "health_score": 89.0},
    {"code": "RF-207", "type": "refrigeration_unit", "location": "Nagpur Cold Hub", "health_score": 86.0},
    {"code": "RF-208", "type": "refrigeration_unit", "location": "Ahmedabad Cold Hub", "health_score": 90.0},
    {"code": "RF-209", "type": "refrigeration_unit", "location": "Nagpur Cold Hub", "health_score": 91.0},
    {"code": "CV-101", "type": "conveyor_motor", "location": "Bhiwandi DC", "health_score": 95.0},
    {"code": "CV-102", "type": "conveyor_motor", "location": "Bhiwandi DC", "health_score": 87.0},
    {"code": "CM-301", "type": "compressor", "location": "Pune DC", "health_score": 38.0},
]

# ---------------------------------------------------------------------------
# Shipments and routes (§29)
#
# The hero shipment's baseline numbers are chosen so the §18 formula returns
# exactly 18 (SAFE). See tests/test_demo_arc.py, which asserts the whole arc.
# ---------------------------------------------------------------------------

HERO_SHIPMENT_CODE = "SC-1042"

SHIPMENTS: list[dict] = [
    {
        "code": "SC-1042",
        "product": "Frozen Chicken",
        "origin_city": "Mumbai",
        "destination_city": "Pune",
        "shipment_value_inr": 500_000.0,
        "machine": "RF-204",
        "remaining_shelf_life_hours": 16.0,
        # Left the dock in spec. (It used to start with 14 minutes of excursion
        # already on the clock, which nothing on screen explained.)
        "minutes_outside_safe_range": 0.0,
        "is_hero": True,
        "routes": [
            {
                "label": "Route A - NH-48 via Lonavala", "waypoint": "Lonavala",
                # A loaded reefer truck, Mumbai to Pune over the ghat: about
                # four hours door to door. It was 2.5 h - a car's time - which
                # also meant the truck reached Pune before the demo's climax.
                "eta_minutes": 240.0,
                "delay_minutes": 10.0,
                "traffic_level": "LOW",
                "weather_level": "CLEAR",
                "is_current": True,
                "is_selected": True,
                "notes": "Default lane. Stays on the failing RF-204 for the whole leg.",
            },
            {
                "label": "Route B - Expressway via Chakan cold hub", "waypoint": "Chakan",
                "eta_minutes": 258.0,  # the Chakan hub stop adds ~18 min
                "delay_minutes": 0.0,
                "traffic_level": "LOW",
                "weather_level": "CLEAR",
                "is_current": False,
                "is_selected": False,
                # Route B transfers the load to standby unit RF-205 (88% health)
                # at Chakan, which is why its refrigeration risk is far lower
                # despite the longer nominal ETA.
                "reefer_health_override": 88.0,
                "notes": "Longer on paper, but swaps the load to standby reefer RF-205 at Chakan.",
            },
        ],
    },
    {
        "code": "SC-1039",
        "product": "Paneer",
        "origin_city": "Pune",
        "destination_city": "Mumbai",
        "shipment_value_inr": 180_000.0,
        "machine": "RF-201",
        "remaining_shelf_life_hours": 28.0,
        "minutes_outside_safe_range": 6.0,
        "routes": [
            {"label": "Route A - Mumbai-Pune Expressway", "waypoint": "Lonavala", "eta_minutes": 165.0, "delay_minutes": 5.0, "traffic_level": "LOW", "weather_level": "CLEAR", "is_current": True, "is_selected": True},
            {"label": "Route B - Old NH-48", "waypoint": "Lonavala", "eta_minutes": 210.0, "delay_minutes": 0.0, "traffic_level": "LOW", "weather_level": "CLEAR"},
        ],
    },
    {
        "code": "SC-1044",
        "product": "Ice Cream Tubs",
        "origin_city": "Delhi",
        "destination_city": "Ahmedabad",
        "shipment_value_inr": 320_000.0,
        "machine": "RF-202",
        "remaining_shelf_life_hours": 11.0,
        "minutes_outside_safe_range": 22.0,
        "routes": [
            {"label": "Route A - NH-48 via Jaipur", "waypoint": "Jaipur", "eta_minutes": 300.0, "delay_minutes": 45.0, "traffic_level": "HIGH", "weather_level": "RAIN", "is_current": True, "is_selected": True},
            {"label": "Route B - NH-52 via Ajmer", "waypoint": "Ajmer", "eta_minutes": 330.0, "delay_minutes": 10.0, "traffic_level": "MEDIUM", "weather_level": "CLEAR"},
        ],
    },
    {
        "code": "SC-1051",
        "product": "Frozen Peas",
        "origin_city": "Bengaluru",
        "destination_city": "Chennai",
        "shipment_value_inr": 140_000.0,
        "machine": "RF-203",
        "remaining_shelf_life_hours": 30.0,
        "minutes_outside_safe_range": 10.0,
        "routes": [
            {"label": "Route A - NH-44 via Hosur", "waypoint": "Hosur", "eta_minutes": 240.0, "delay_minutes": 15.0, "traffic_level": "MEDIUM", "weather_level": "CLEAR", "is_current": True, "is_selected": True},
            {"label": "Route B - NH-48 via Kolar", "waypoint": "Kolar", "eta_minutes": 285.0, "delay_minutes": 0.0, "traffic_level": "LOW", "weather_level": "CLEAR"},
        ],
    },
    {
        "code": "SC-1055",
        "product": "Frozen Chicken",
        "origin_city": "Hyderabad",
        "destination_city": "Bengaluru",
        "shipment_value_inr": 260_000.0,
        "machine": "RF-206",
        "remaining_shelf_life_hours": 18.0,
        "minutes_outside_safe_range": 12.0,
        "routes": [
            {"label": "Route A - NH-44 via Kurnool", "waypoint": "Kurnool", "eta_minutes": 330.0, "delay_minutes": 20.0, "traffic_level": "MEDIUM", "weather_level": "CLEAR", "is_current": True, "is_selected": True},
            {"label": "Route B - NH-150 via Raichur", "waypoint": "Raichur", "eta_minutes": 375.0, "delay_minutes": 0.0, "traffic_level": "LOW", "weather_level": "CLEAR"},
        ],
    },
    {
        "code": "SC-1058",
        "product": "Ice Cream Tubs",
        "origin_city": "Mumbai",
        "destination_city": "Surat",
        "shipment_value_inr": 210_000.0,
        "machine": "RF-207",
        "remaining_shelf_life_hours": 9.0,
        "minutes_outside_safe_range": 30.0,
        "routes": [
            {"label": "Route A - NH-48 via Vapi", "waypoint": "Vapi", "eta_minutes": 285.0, "delay_minutes": 30.0, "traffic_level": "HIGH", "weather_level": "RAIN", "is_current": True, "is_selected": True},
            {"label": "Route B - Coastal SH-6", "waypoint": "Valsad", "eta_minutes": 300.0, "delay_minutes": 5.0, "traffic_level": "LOW", "weather_level": "CLEAR"},
        ],
    },
    {
        "code": "SC-1061",
        "product": "Paneer",
        "origin_city": "Ahmedabad",
        "destination_city": "Delhi",
        "shipment_value_inr": 195_000.0,
        "machine": "RF-208",
        "remaining_shelf_life_hours": 26.0,
        "minutes_outside_safe_range": 8.0,
        "routes": [
            {"label": "Route A - NH-48 via Udaipur", "waypoint": "Udaipur", "eta_minutes": 540.0, "delay_minutes": 10.0, "traffic_level": "LOW", "weather_level": "CLEAR", "is_current": True, "is_selected": True},
            {"label": "Route B - NH-58 via Kota", "waypoint": "Kota", "eta_minutes": 585.0, "delay_minutes": 0.0, "traffic_level": "LOW", "weather_level": "CLEAR"},
        ],
    },
    {
        "code": "SC-1067",
        "product": "Frozen Peas",
        "origin_city": "Nagpur",
        "destination_city": "Hyderabad",
        "shipment_value_inr": 130_000.0,
        "machine": "RF-209",
        "remaining_shelf_life_hours": 38.0,
        "minutes_outside_safe_range": 5.0,
        "routes": [
            {"label": "Route A - NH-44 via Adilabad", "waypoint": "Adilabad", "eta_minutes": 420.0, "delay_minutes": 10.0, "traffic_level": "LOW", "weather_level": "CLEAR", "is_current": True, "is_selected": True},
            {"label": "Route B - NH-63 via Warangal", "waypoint": "Warangal", "eta_minutes": 465.0, "delay_minutes": 0.0, "traffic_level": "LOW", "weather_level": "CLEAR"},
        ],
    },
]

# ---------------------------------------------------------------------------
# The demo scenarios (causal, not scripted).
#
# Each entry perturbs a ROOT CAUSE and nothing else. There is no
# `minutes_outside_delta`, no `shelf_life_delta_hours` and no
# `expected_melt_index` any more, because none of those are causes -- they are
# consequences, and the physics tick derives them.
#
#   traffic_incident            -> adds incident delay to a lane
#   refrigeration_degradation   -> raises a unit's wear RATE (a refrigerant
#                                  leak), so efficiency falls on its own
#   weather_deterioration       -> injects a heat + storm front into ambient
#
# After applying the cause, the trigger integrates the world forward for
# `settle_minutes` of simulated time. The Melt Index that comes out is whatever
# the formula makes of the resulting state. Nobody tells it what to be.
#
# The settle times add up to 5 h 15 min, inside the hero's ~4 h lane plus its
# delays, so the truck is genuinely still on the road at the climax (about
# three-quarters of the way) and after the repair. They used to add up to 8 h
# on a 2.5 h lane: the board said "predicted to spoil before delivery" about a
# truck the map showed already in Pune.
# ---------------------------------------------------------------------------

DEMO_EVENTS: dict[str, dict] = {
    "traffic_incident": {
        "label": "Traffic incident on the lane",
        "description": (
            "Accident on NH-48 near Lonavala. Adds incident delay to Route A, which "
            "lengthens transit, eats the ETA margin and keeps the cargo in a warm "
            "truck for longer."
        ),
        "order": 1,
        "target_type": "shipment",
        "target_code": HERO_SHIPMENT_CODE,
        "cause": "incident_delay_minutes",
        "amount": 95.0,
        "traffic_level": "HIGH",
        "settle_minutes": 45.0,
    },
    "refrigeration_degradation": {
        "label": "Refrigerant leak on RF-204",
        "description": (
            "RF-204 starts losing cooling efficiency at 8 points per operating "
            "hour. Sensors drift, the anomaly detector fires, health falls, and the "
            "unit progressively loses the race against heat ingress."
        ),
        "order": 2,
        "target_type": "machine",
        "target_code": HERO_MACHINE_CODE,
        "cause": "degradation_rate_per_hour",
        "amount": 8.0,
        "settle_minutes": 150.0,
    },
    "weather_deterioration": {
        "label": "Heat + storm front",
        "description": (
            "A heat wave with a storm front over the Western Ghats. Ambient rises "
            "11 C above the observed value and the lane re-bands to STORM, so heat "
            "ingress and weather delay both climb."
        ),
        "order": 3,
        "target_type": "environment",
        "target_code": "",
        "cause": "ambient_offset_c",
        "amount": 11.0,
        "settle_minutes": 120.0,
    },
    "maintenance_completed": {
        "label": "Repair RF-204",
        "description": (
            "Close out the maintenance workflow: the leak is fixed, so the wear rate "
            "returns to normal and efficiency is restored. Risk should fall over the "
            "following ticks without anyone setting it."
        ),
        "order": 4,
        "target_type": "machine",
        "target_code": HERO_MACHINE_CODE,
        "cause": "repair",
        "amount": 0.0,
        "settle_minutes": 45.0,
    },
}

# The demo arc is asserted by shape, not by hardcoded figures: the Melt Index
# must rise monotonically through the three escalations, the recommended lane
# must be the cheaper one in expected loss, and a high-impact action must stop
# for human approval. See tests/test_demo_arc.py.
DEMO_ARC_MIN_ESCALATION = 6.0  # Melt Index points each step must add, at least
