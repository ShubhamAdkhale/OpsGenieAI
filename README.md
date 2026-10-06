# OpsGenie AI

**Predict the problem. Understand the impact. Take action.**

An AI-powered **Operations Control Tower** for cold-chain logistics. Not four tools
bolted together — one pipeline:

```
SENSE  →  PREDICT  →  QUANTIFY  →  DECIDE  →  ACT
```

A refrigeration unit degrading on the Predictive Maintenance page visibly changes the
risk score and route recommendation of the shipment it is carrying, live, in the same
demo. That cross-module link is the point.

> **What is real and what is not.** Weather is genuinely live — Open-Meteo, keyless,
> fourteen lane waypoints. Everything else is simulated by this application's own
> models: sensor telemetry, traffic, demand history, and workflow execution (which
> updates database rows and writes a log — no courier API, ERP or work-order system is
> called). The Melt Index is a transparent weighted formula, not a validated scientific
> measurement. Every value on screen carries a **LIVE / SIMULATED / PREDICTED** label,
> and a simulated reading is never shown as a live one.

---

## The one thing that makes this different

Most demo dashboards assign their numbers. This one **integrates them**.

There is no `meltIndex = 89` anywhere, and no scenario that could contain such a line.
A scenario may only name a **root cause** — an incident delay, a wear rate, an ambient
temperature offset — and then the simulation is advanced. What appears on screen is
whatever the model made of the new conditions.

The causal chain, end to end:

```
ambient weather (Open-Meteo, or a labelled fallback)
  + reefer cooling power (efficiency, itself integrated from a wear rate)
      → cargo temperature            Newton's law of cooling
      → minutes outside safe range   accrued ONLY while genuinely too warm
      → shelf-life burn rate         Q10 rule: warm cargo ages faster
traffic congestion + incidents + weather
      → route delay → ETA → ETA margin
all of the above
      → Melt Index → spoilage probability → expected loss → recommendation → workflow
```

The test suite enforces this rather than trusting it:

| Test | What it pins down |
|---|---|
| `test_no_scenario_can_assign_a_consequence` | a scenario's vocabulary is root causes only |
| `test_the_cold_chain_breach_is_earned_by_the_thermal_model` | excursion minutes require cargo actually above its safe threshold |
| `test_the_traffic_incident_only_touches_delay` | a traffic event does not reach past the route |
| `test_a_healthy_world_stays_calm_when_time_passes` | the simulation does not manufacture a crisis from nothing |
| `test_weather_actually_influences_the_risk_score` | ambient temperature alone moves the score |
| `test_arc_is_identical_three_times_in_a_row` | causal does not mean unrepeatable |

---

## Quick start (Windows, ~10 minutes)

Prerequisites: **Python 3.11+** and **Node 18+** on your PATH.

```powershell
cd OpsGenieAI
.\setup.ps1
```

That creates the venv, installs both dependency sets, trains the four models, seeds the
database and runs the test suite. Then, in two terminals:

```powershell
.\start-backend.ps1     # http://localhost:8000/docs
.\start-frontend.ps1    # http://localhost:5173
```

Open **http://localhost:5173**. The board is already moving — the simulated clock is
advancing, shelf life is burning down, congestion follows a rush-hour curve. Press the
Scenario Injector buttons at the bottom to drive the demo.

> Use `localhost`, not `127.0.0.1`, for the frontend — Vite binds the loopback *name*,
> which resolves to IPv6 `::1` on Windows.

<details>
<summary>Manual setup (macOS / Linux)</summary>

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m app.ml.train_all             # trains 4 models, ~30s
.venv/bin/python ../data/seed.py --force
.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# second terminal
cd frontend && cp .env.example .env && npm install && npm run dev
```
</details>

---

## The demo

See **[DEMO.md](DEMO.md)** for the full presenter script. The shape of the arc:

| Step | Root cause applied | Result |
|---|---|---|
| 0 | — (after Reset) | SC-1042 **SAFE**, cargo holding at −18 °C |
| 1 | incident delay **+95 min** | **LOW** — ETA margin shrinks; cargo still cold, *no* excursion |
| 2 | wear rate **→ 8 pts/h** on RF-204 | **HIGH** — efficiency falls, anomaly fires, shipment risk climbs |
| 3 | ambient **+11 °C**, lane → STORM | **CRITICAL** — cold chain breaches, excursion accrues, shelf life burns |
| 4 | manager approves the reroute | risk roughly halves, loss avoided booked |
| 5 | repair RF-204 | cargo cools again — nobody lowered a score |

The truck is genuinely **still on the road** throughout: about three-quarters of the
way to Pune at the climax, 88% after the repair. (An earlier arc advanced eight
simulated hours on a 2.5-hour lane, so the map showed the truck in Pune while the card
said it would spoil "before delivery". The lane is now a realistic four hours for a
loaded reefer truck, and the scenario time steps add up to 5 h 15 min.) Loads that do
arrive are **delivered**, and their lane gets the next load — see
`simulation/dispatch.py`.

Exact figures move with the model and with live weather, which is the correct behaviour
for a simulation rather than a script. The **shape** is asserted: monotonic escalation,
a CRITICAL climax, a reroute that wins on expected loss, and mandatory human approval
above ₹1,00,000 of impact.

**Always press Reset before a run.**

---

## Architecture

```
┌─────────────────────────────┐
│   React + Vite dashboard    │  polls /api/dashboard every 4s
└──────────────┬──────────────┘
               │ HTTP/JSON
┌──────────────┴──────────────┐
│      FastAPI backend        │
│                             │
│  simulation/physics.py   ← THE CAUSAL CORE. One tick every 3s advances
│                            6 simulated minutes: machine wear, sensor
│                            generation, cargo thermal integration, route
│                            delay, inventory drawdown — then re-derives
│                            every prediction from the state it produced.
│                             │
│  providers/                ← THE INGESTION BOUNDARY. One chain per stream,
│                            tried live → user → simulated, falling back per
│                            item. `registry.py` declares every stream; the
│                            provenance panel is rendered from it.
│                             │
│  services/weather.py       storage, banding and delay for what a chain returned
│  services/risk_engine.py   Melt Index, spoilage, expected loss, optimizer
│  services/maintenance.py   anomaly, failure probability, RUL
│  services/forecasting.py   demand, stockout, reorder
│  services/decision_engine  confidence/impact gating, workflow execution
│  services/priority.py      the dashboard's headline decision
│  services/provenance.py    LIVE / SIMULATED / PREDICTED labelling
│  services/explain.py       rule-based explanations (no LLM)
└──────────────┬──────────────┘
               │ SQLAlchemy
┌──────────────┴──────────────┐
│   SQLite (opsgenie.db)      │
└─────────────────────────────┘
```

Two background loops, both crash-isolated:

- **physics loop** — every 3s, advances the world. Runs for *every* asset. A control
  tower whose sensor feed stops between button presses is a slideshow.
- **weather loop** — every 600s, one batched Open-Meteo request. Deliberately separate,
  so a slow or unreachable API can never stall the simulation: the tick always reads the
  last stored observation.

**Everything funnels through `physics.tick()` → `risk_engine.recalculate()`.** Scenario
triggers apply their cause and then call `physics.settle()`, which runs the *same* tick.
A trigger therefore cannot produce a state the live simulation could not have reached on
its own.

### Why the clock is simulated

Time advances by a fixed step per tick rather than from the wall clock. That is what
keeps the demo repeatable without scripting it: N ticks of integration from the same
baseline always produce the same state. Reproducibility and causality are usually traded
off against each other; a simulated clock buys both.

---

## The thermal model

Two constants, and their **ratio** is what matters:

```
BOX_CONDUCTANCE_PER_HOUR = 0.30      # fraction of the ambient/cargo gap that leaks in
MAX_COOLING_C_PER_HOUR   = 19.2      # pull-down at 100% efficiency

T_equilibrium = T_ambient − (19.2 / 0.30) × efficiency
              = T_ambient − 64 × efficiency
```

So the box settles wherever heat ingress and cooling balance:

| Reefer efficiency | ambient 30 °C | 32 °C | 38 °C | 41 °C |
|---|---|---|---|---|
| 90.8% (standby RF-205) | −28.1 | −26.1 | −20.1 | −17.1 |
| 85.8% (RF-204 healthy) | −24.9 | −22.9 | −16.9 | **−13.9** |
| 70% | **−14.8** | **−12.8** | **−6.8** | **−3.8** |
| 60% | **−8.4** | **−6.4** | **−0.4** | **+2.6** |

Frozen goods must stay at −15 °C or colder in transit — the Codex quick-frozen rule
(held at −18 °C, brief rises to no warmer than −15 °C), and the setpoint is −18 °C.
Read that table and the demo writes itself: a healthy unit holds in any weather, a
moderately worn one holds until real heat arrives, a badly degraded one is already on
the limit on a mild day, and **degradation plus heat together** is what breaks the
cold chain. Neither constant was chosen to make a
demo land — the crossover falls out of the ratio.

Excursion minutes accrue only while cargo is above the product's safe maximum. Shelf
life then burns at `2^(excess °C / 10)` — the Q10 rule, capped at 6×.

`/api/shipments/{id}` returns this balance in words, computed in the backend:

> "Heat leaks in at 12.4 °C/h against 9.4 °C/h of cooling, so the box is heading for
> 3 °C. That is above the −15 °C safe maximum, so the cold chain fails."

---

## How the Melt Index works

A deliberately transparent weighted formula (**not** a learned model), so anyone can see
exactly why the number moved:

```
MeltIndex = 0.25·Temperature + 0.20·Refrigeration + 0.15·Traffic
          + 0.15·Weather     + 0.15·ShelfLife     + 0.10·ETA
```

| Component | How it's computed | Where its input comes from |
|---|---|---|
| Temperature | projected excursion ÷ 240 min × 100 | the thermal model above |
| Refrigeration | `100 − reefer health` | integrated from the machine's wear rate |
| Traffic | `delay ÷ 60 min × 100` | incident + congestion + weather delay |
| Weather | CLEAR 0 · RAIN 40 · STORM 70 · EXTREME 100 | Open-Meteo band, or labelled fallback |
| Shelf life | `100 × (1 − remaining ÷ window)` | Q10 burn under warm conditions |
| ETA | 100 if arrival misses the window, else `100 − margin_h × 20` | derived ETA |

Bands: 0–20 SAFE · 21–40 LOW · 41–60 MODERATE · 61–80 HIGH · 81–100 CRITICAL.

**Temperature and refrigeration risk are evaluated *per route*.** An alternative route
can transfer the load to a healthy standby reefer, which is why Route B wins on expected
loss despite what the map suggests. That is the optimizer's whole argument: it minimizes
**expected business loss**, not travel time.

---

## Route delay is never assigned

```
delay_minutes = incident_delay + congestion_delay + weather_delay
```

recomputed every tick, and asserted by `test_route_delay_is_always_the_sum_of_its_causes`.

- **incident** — set by a scenario, then sheds 6 min per simulated hour: jams clear.
- **congestion** — `base_ETA × band_factor × rush_hour_factor(sim_clock)`, a deterministic
  double-Gaussian peaking at 09:30 and 18:30.
- **weather** — `base_ETA × factor(band)`, 0 / 8% / 18% / 30%.

---

## Weather (the only live input)

`providers/weather/open_meteo.py` calls Open-Meteo once for all fourteen lane waypoints —
comma-separated coordinates, one request — and each reading is stored with a `source`:

| Source | Meaning | UI label |
|---|---|---|
| `LIVE_OPEN_METEO` | the API answered | **LIVE** |
| `SIMULATED_FALLBACK` | unreachable, or weather disabled → deterministic diurnal curve | **SIMULATED** |
| `SIMULATED_INJECTED` | a scenario is overriding ambient | **SIMULATED** |

Two things come out of each reading, and both do work:

- **`weather_level`** → the 0.15-weighted risk component *and* a route delay multiplier.
- **`temperature_c`** → the ambient in the thermal model. This is the link the requirement
  asks for: external temperature ↑ → more heat ingress → the reefer has to work harder →
  a degraded reefer loses that race → spoilage risk ↑.

Banding is transparent thresholds, not a model: WMO code, plus precipitation and wind,
plus a **heat rule** — ≥38 °C is STORM and ≥42 °C is EXTREME regardless of rain, because
a heat wave is a cold-chain event in its own right.

The live provider cannot take the app down. On any failure it returns `{}`, and
`ProviderChain` falls through to the simulator — per waypoint, so a partial answer keeps
the rows it did get. A reset **preserves** stored observations: weather is an external
fact, not part of the demo baseline, so pressing Reset must not silently downgrade the
feed to SIMULATED.

---

## The ingestion boundary

Every stream the dashboard runs on is declared once, in `providers/registry.py`, next to
the code that fetches it. A stream that ingests has a `ProviderChain`; a stream that
derives has none and is fixed at `PREDICTED`, because a formula's provenance is its
inputs and it has no source of its own.

```
ProviderChain("weather", [OpenMeteoProvider(), SimulatedWeatherProvider()])
                          └── live ──┘         └── terminal, cannot fail ──┘
```

Four rules, hoisted out of the weather feed so they apply to every stream added later:

| Rule | Why |
|---|---|
| A provider reports a fine-grained `source`; the UI label is **derived** from it | Two stored columns that can disagree is how a simulated reading ends up wearing a LIVE chip |
| A provider that raises, times out or returns nothing is **skipped, not fatal** | A dead API must degrade the label, not 500 the dashboard |
| Fallback is **per item**, not per request | Twelve live waypoints and two simulated ones is a real state; discarding the twelve for consistency is worse data |
| The **last** provider in a chain cannot fail | Otherwise the stream has states where it returns nothing, and every consumer downstream needs its own null handling |

Labels are `LIVE` · `USER` · `SIMULATED` · `PREDICTED`, plus `MIXED` as a stream-level
verdict when items disagree or a scenario has perturbed stored values after the fact.
`USER` is declared and unused — it is the label for data the operator owns, which is what
replaces the seeded universe in a later phase.

Streams still generated in-process (sensors, traffic, demand, workflow execution) are
declared with an empty chain. Making one of them live means adding providers to the row
that already exists; the provenance panel updates itself, because it is rendered from the
registry rather than from a hand-maintained list.

---

## Where ML is actually used

Four trained scikit-learn models, trained offline at setup time on **synthetic** data,
saved as `.joblib`, loaded once at startup:

| Model | Algorithm | Used for | Sanity check at train time |
|---|---|---|---|
| Demand forecast | GradientBoostingRegressor, one per product | next 7 days of demand | must beat a 7-day moving average |
| Anomaly detection | IsolationForest on **normal-operation windows only** | `anomaly_score`, `anomaly_detected` | degraded windows must score lower |
| Failure within 24h | GradientBoostingClassifier | `ml_failure_probability` | held-out-trajectory ROC AUC > 0.95 on observable windows, and must beat the health rule |
| Spoilage | GradientBoostingClassifier | `spoilage_probability` when `USE_ML_SPOILAGE=true` | within 5% of the label-noise ceiling |

**The failure classifier was retrained on its own generator** (`failure_trajectories`).
The first version said 0.3% for RF-204 at 1% health: windows after the failure point
were labelled negative, and the live leak (5 pts/h) ran ten times faster than anything
it had seen. The new data covers slow wear, stable-but-worn units, fast leaks, repairs
and 0.2–5 h reading cadences, and labels a unit already below the floor as failing.
Evaluated on held-out *units*, not held-out windows:

| | ROC AUC | Brier |
|---|---|---|
| Classifier, all held-out windows | 0.900 | 0.076 |
| Health rule, same windows | 0.845 | 0.247 |
| Classifier, observable windows | 0.987 | |
| Health rule, observable windows | 0.927 | |

"Observable" excludes the 21.8% of positives whose fault has not begun by the end of
the window — a leak that has not happened yet is invisible to any sensor model, so
those set the ceiling. On the demo arc it tracks RF-204 at 3% → 91% (leak) → 99%
(heat) → 1% (repair), pinned by `tests/test_failure_model.py`.

Anomaly detection and demand forecasting are pure ML with no deterministic override.
**The anomaly detector now sees genuine drift**: sensor values are generated from the
machine's current efficiency every tick, so a rising wear rate produces a real
trajectory. The previous build injected an out-of-distribution reading to make the
detector fire; nothing is injected any more.

Two places deliberately use a **deterministic** calculation instead of the model:

- **`spoilage_probability`** defaults to a calibrated logistic curve on the Melt Index,
  so the causal chain stays inspectable end to end. The trained classifier ships and is
  one env flag away.
- **`failure_probability`** used by the "> 0.75 raises a workflow" rule is a monotone map
  from health score, so a live trigger cannot mis-fire. The UI calls it **Condition
  risk**, because that is what it measures: how worn a unit is. It is not a 24-hour
  forecast — CM-301 sits at 65% on it while losing 0.03 pts/h, some 400 hours from the
  floor. The UI's **Failure < 24h** is the trained classifier, which reads the trend.
  When the two disagree the page says which way and why.

**Every prediction has a non-ML fallback.** `ml/registry.py` cannot raise: a missing or
broken model returns `None` and the caller uses its rule-based path. Models are warmed
**single-threaded at startup** — the physics tick runs in a worker thread, and a
concurrent first import of scikit-learn can deadlock CPython's import lock. Check what
is live at [`/api/health`](http://localhost:8000/api/health).

---

## Decision rules

| Confidence | Impact | Action |
|---|---|---|
| — | > ₹1,00,000 | **Mandatory human approval**, never auto-executed |
| — | ₹25,000 – ₹1,00,000 | Recommend + `PENDING_APPROVAL` |
| HIGH (≥ 0.70) | < ₹25,000 | **Auto-execute**, logged as `AUTO_EXECUTED` |
| LOW (< 0.40) | any | Recommend only, flagged low confidence |

The top row is a **safety property**, not a UX preference: no high-impact action is ever
taken without a timestamped human approval.

**Plus a materiality floor on reroutes**, which the continuous simulation made necessary:

```
REROUTE_MIN_SAVING_INR = 15_000        # and
REROUTE_MIN_SAVING_FRACTION = 0.05     # of shipment value
```

A reroute is a physical action — a driver changes lane, a cold hub accepts a transfer.
Fed a continuously changing world, the optimizer will always find *some* marginally
better lane; without this floor it proposed sub-1% improvements every tick and the
auto-execute row quietly acted on them, rerouting a ₹5L shipment to save ₹9,000 before
anyone had looked at the dashboard. Now a saving must clear both an absolute floor and a
share of what is being protected.

Approvals are immutable — approving or rejecting a resolved workflow returns HTTP 409. A
manager can also **override** the AI's route choice, logged distinctly as `OVERRIDDEN`.

---

## The dashboard

The first screen answers five questions, in this order, and the **backend decides all
five**:

1. **What is wrong** — headline, lane, Melt Index
2. **What will happen** — spoilage probability
3. **Why** — the weighted components actually driving the score, plus the equipment
4. **How much is at risk** — `₹5,00,000 × 77% = ₹3,83,000`, arithmetic shown
5. **What to do** — the recommendation, its gate, and an Approve button

`services/priority.py` ranks, thresholds and words all of it. React renders `answers`
and `financial` verbatim: **no business logic is duplicated in the browser.** The card is
built from one live evaluation throughout, so it can't show "₹2,01,000 at risk" above
"expected loss falls from ₹95,000" — a bug the earlier mixed-source version had.

Below that: five KPIs and nothing more, a risk trend chart read off the recalculation
audit trail, and recent AI decisions. Everything else — the full shipment table,
equipment health, demand forecast, the map — is behind **progressive disclosure**. The
map is deliberately secondary and closed by default: it shows *where* things are, which
is the lesser job, and it was previously taking the most valuable space on the screen.

The **provenance line** sits above everything as a single sentence naming what is live
and what is not, expanding to per-stream detail and a per-waypoint weather table.

### Visual design

The dashboard is a light, low-chrome theme in which **only data and status carry colour**.
Surfaces, borders and labels are neutrals, so the reader's eye lands on the one thing that
is actually wrong rather than on the interface.

| Decision | Why |
|---|---|
| Light theme, three surface levels, one hairline weight | The dark control-room theme put saturated accents on every surface; everything competed at the same volume. |
| Three ink levels only | A fourth and fifth grey are indistinguishable and invite drift. |
| Four status tiers, not six | Nobody ranks six colours at a glance. SAFE/LOW collapse to one green, and the band name is always written beside the dot — status is never colour alone. |
| Two text sizes for status, split by contrast | The saturated fill steps are for marks; several sit under 3:1 on white, so text uses darker `status-ink` steps. |
| One chart series, not five | The trend was Melt Index plus four faint component lines. It is now one line over severity bands, with a **Drivers** toggle showing the current contributions as a ranked bar. |
| Sans + tabular figures for numbers | Monospace is reserved for identifiers (`SC-1042`, `RF-204`), where fixed width does identification work. |
| Provenance collapsed to one line | Eight permanent metadata chips competed with the decision. Honesty does not require volume. |

Chart colours come from a validated categorical palette (`#2a78d6` / `#eb6834` / `#1baf7a`),
checked against the actual `#ffffff` card surface for CVD separation and contrast rather than
picked by eye. Gridlines are solid hairlines — dashing is reserved for the forecast line,
where it genuinely means *projection*.

---

## API

Docs: **http://localhost:8000/docs**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/dashboard` | priority summary, provenance, environment, trend, KPIs, everything |
| GET | `/api/shipments/{id}` | full detail incl. `thermal` heat balance and route evaluations |
| GET | `/api/shipments/{id}/routes` | routes with expected loss each |
| POST | `/api/shipments/{id}/reroute` | `{route_id}` |
| GET | `/api/machines/{id}` | health, wear rate, sensors, risk factors |
| GET | `/api/forecast` · `/api/inventory` | demand, stockout, reorder |
| GET | `/api/workflows` · POST `/{id}/approve` · `/{id}/reject` | decision history and gating |
| GET | `/api/simulation/scenarios` | the injector buttons, each naming its root cause |
| POST | `/api/simulation/trigger-event` | apply one cause, settle, return the consequence |
| POST | `/api/simulation/tick` | advance one step by hand |
| GET | `/api/simulation/environment` | simulated clock + weather provenance |
| POST | `/api/simulation/refresh-weather` | re-fetch Open-Meteo now |
| POST | `/api/simulation/reset` | restore the baseline (keeps live weather) |
| GET | `/api/copilot/ask?q=` | rule-based Q&A over the database (no LLM) |
| GET | `/api/health` | which models loaded, which waypoints are live |

---

## Reliability

The demo must never depend on a live external service, so:

| Failure | What happens |
|---|---|
| Open-Meteo unreachable / slow / rate-limited | deterministic simulated diurnal curve, labelled **SIMULATED** in the UI |
| A model file is missing or errors | deterministic rule-based fallback; `/api/health` shows it |
| One physics tick raises | logged, loop continues; the world is never left half-advanced |
| No internet (map tiles unreachable) | MapView probes one tile and falls back to a route **table** |
| Backend down | visible banner; the last good data stays on screen |
| Database corrupted | disposable — `python data/seed.py --force` rebuilds in seconds |
| LLM | there isn't one. Explanations are string templates over stored rows |

The tick prunes after itself (240 sensor readings per machine, 180 assessments per
shipment, 120 alerts, 12 hours of weather) and only writes an audit row when the Melt
Index actually moved, so a dashboard left running for hours does not grow without bound.

**Alerts deduplicate on state, not on message text.** The messages embed figures the tick
recomputes every few seconds, so text matching never matched and one shipment sitting in
a single risk band produced a fresh alert every three seconds — 70-odd entries within
minutes. Alerts are now keyed on the state they describe (`shipment-risk:SC-1042:HIGH`):
a new entry appears when the band changes, and while it holds the existing entry's
message is refreshed in place so the numbers stay current. Measured over 300 ticks the
feed settles at 13 entries instead of growing without limit.

---

## Tests

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q      # ~2.5 min
```

The suite is slower than before because it now drives real integration rather than
asserting stored constants.

| File | Covers |
|---|---|
| `test_demo_arc.py` | the causal arc: escalation, earned breach, cross-module link, gating, recovery, 3× repeatability |
| `test_pipeline.py` | weather classification and fallback, provenance labelling, tick invariants, priority summary |
| `test_providers.py` | the ingestion boundary: per-item fallback, label derivation, a raising source degrading instead of propagating |
| `test_risk_engine.py` | formula, band boundaries, clamping, per-route evaluation, optimizer trade-off |
| `test_decision_engine.py` | one test per rule-table row, workflow lifecycle, immutability, override |
| `test_api.py` | a happy path per endpoint, validation rejections, full demo over HTTP |
| `test_formatting.py` | Indian-numbering rupee output |

**These tests assert properties, not figures.** The previous suite pinned exact numbers
(Melt Index 18/36/64/89, expected loss ₹4,10,000) which was only meaningful while the
simulator applied deltas tuned to produce them — it tested that the script still said
what the script said. Tests that assert derived numbers must assert relationships:
monotonic escalation, `expected_loss == value × probability`, breach requires cargo above
threshold, recommendation minimizes expected loss.

---

## Configuration

`backend/.env` (see `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./opsgenie.db` | swap for a Postgres URL to move to a server |
| `CORS_ORIGINS` | `http://localhost:5173,...` | restricted to the known dev origin |
| `PHYSICS_ENABLED` | `true` | `false` freezes the world at its seeded state |
| `PHYSICS_TICK_SECONDS` | `3` | wall-clock seconds between ticks |
| `SIM_MINUTES_PER_TICK` | `6` | demo pace: 1 real minute ≈ 2 simulated hours |
| `SETTLE_STEP_MINUTES` | `15` | integration step while a trigger settles |
| `AUTO_RESET_ENABLED` | `true` | bound the demo world into an episode (see below) |
| `IDLE_PAUSE_SECONDS` | `90` | no dashboard poll for this long pauses the tick |
| `IDLE_RESET_MINUTES` | `20` | first request after this much silence resets to baseline |
| `EPISODE_SIM_HOURS` | `24` | simulated hours before an unattended episode restarts |
| `ACTION_GRACE_MINUTES` | `5` | ...but never within this long of a button press |
| `WEATHER_ENABLED` | `true` | `false` forces the labelled offline path |
| `WEATHER_TIMEOUT_SECONDS` | `4` | |
| `WEATHER_REFRESH_SECONDS` | `600` | |
| `USE_ML_SPOILAGE` | `false` | `true` routes spoilage through the trained classifier |

`frontend/.env`: `VITE_API_BASE_URL` and `VITE_POLL_INTERVAL_MS` (default 4000).

**Why the world resets itself.** Nothing in the simulation ever finishes —
shipments never deliver and stock is never replenished — so a board left
running for a day drifts to empty warehouses and spent shelf lives. For a hosted
link that a judge may open days later, `simulation/lifecycle.py` treats the world
as a bounded episode: it pauses while nobody is watching, resets for a visitor
returning after a long absence, and restarts an unattended episode after
`EPISODE_SIM_HOURS` — never while someone is mid-demo. Set
`AUTO_RESET_ENABLED=false` to get the old run-forever behaviour.

Authentication is **explicitly out of scope** for this single-user demo build.

---

## Known limits

Stated plainly so nothing here reads as more than it is:

- **The thermal model is plausible, not validated.** Newton cooling with one lumped
  conductance is a reasonable first-order model of an insulated box, and the Q10 rule is
  a real food-science heuristic, but neither is fitted to measured trailer data. The
  constants are named and their ratio is explained; that makes them auditable, not
  correct.
- **The Melt Index weights are hand-tuned**, not fitted to outcome data. Nothing in this
  repo validates them against real spoilage.
- **All training data is synthetic.** The models have learned `ml/synthetic.py`'s
  generator, which is not the same as learning cold-chain physics.
- **The spoilage classifier's ceiling is set by label noise** (labels are Bernoulli draws
  from a probability), so its ROC AUC is ~0.67 — near-optimal for the data, but not a
  number to quote out of context.
- **RUL is a linear extrapolation** of the cooling-efficiency decline rate, not a survival
  model. The UI says "efficiency floor in", not "failure in".
- **Euler integration.** A 15-minute settle step against a ~3.3 hour time constant is
  fine; it would not be at 4 hours.
- **Traffic and demand are synthetic.** A rush-hour Gaussian is not a routing API. They
  are declared in the stream registry with an empty chain, which is exactly where a real
  provider gets plugged in.
- **Polling, not websockets.** Single user, no auth, SQLite, one process. At a 4-second
  poll against a 3-second tick the dashboard is visually indistinguishable from push,
  and there is one less thing to debug.
- **Exact demo figures vary between runs** when live weather differs, because ambient
  temperature is a genuine input. Only the arc's shape is guaranteed.

## What would come next

Real IoT ingestion, traffic and routing as providers on the streams that already declare
them (`providers/weather/` shows the shape: fetch, label, store, fall back); PostgreSQL (one connection-string change);
websocket push instead of polling; real ERP/WMS execution; an LLM copilot with
function-calling into these APIs — keeping the rule that the language layer never
computes the risk score.
