# OpsGenie AI

### Predict the problem. Understand the impact. Take action.

**OpsGenie AI is an AI-powered control tower for cold-chain logistics** — the trucks,
fridges and warehouses that keep frozen and chilled food safe. It watches shipments and
equipment in real time, predicts what is about to go wrong, tells you how much money is
at risk, and recommends (or takes) the action that saves the most.

---

## At a glance

| | |
|---|---|
| **Problem** | Frozen cargo spoils when a fridge unit weakens, the weather turns hot, or a truck gets stuck in traffic. Operators find out too late, after the loss has already happened. |
| **Our solution** | One connected system that goes from **sensor data → prediction → money at risk → decision → action**, with a clear explanation at every step. |
| **Who it's for** | Cold-chain operations managers, fleet managers and warehouse planners. |
| **What makes it special** | The modules are **linked**. A fridge unit wearing out on the Maintenance page raises the risk of the shipment it is carrying, and changes the recommended route, live and on the same screen. |
| **Safety** | The AI acts on its own only for small, high-confidence decisions. Anything above **₹1,00,000** of impact **always** needs a human to approve it. |
| **Honesty** | Every number on screen is labelled **LIVE**, **SIMULATED** or **PREDICTED**. A simulated value is never passed off as live. |

---

## The problem

In cold-chain logistics, one bad hour can destroy a whole truckload. Usually several
small things go wrong together:

-  **The fridge unit (reefer) slowly degrades**, so it cools less and less well
-  **The weather gets hot**, so more heat leaks into the box
-  **Traffic delays the truck**, so the cargo spends longer on the road

Each one on its own looks harmless. **Together they spoil the cargo.** Most tools show
these as separate dashboards, so nobody connects the dots in time.

## Our solution: one pipeline, not four separate tools

```
SENSE  →  PREDICT  →  QUANTIFY  →  DECIDE  →  ACT
```

| Stage | What OpsGenie AI does | Example |
|---|---|---|
| **Sense** | Reads weather, sensor, traffic and inventory data | Live temperature on the Mumbai → Pune lane is 38 °C |
| **Predict** | Uses ML models and a physics-based model to forecast trouble | Reefer RF-204 has a 91% chance of failing within 24 h |
| **Quantify** | Turns risk into money | 77% spoilage chance × ₹5,00,000 cargo = **₹3,83,000 at risk** |
| **Decide** | Compares options and picks the one with the lowest expected loss | Reroute via a cold hub and move the load to a healthy standby reefer |
| **Act** | Starts a workflow, either automatically or after manager approval | Impact is over ₹1 lakh, so it waits for a manager to click Approve |

---

## What you'll see in the app

| Page | What it answers |
|---|---|
| **Control Tower** (home) | The one shipment that needs attention right now: what is wrong, what will happen, why, how much is at risk, and what to do |
| **Shipment Detail** | Cargo temperature, shelf life, route options and expected loss for each route, plus a plain-English explanation of the heat balance |
| **Predictive Maintenance** | Health of each fridge unit and machine, anomaly alerts, chance of failure within 24 hours, remaining useful life |
| **Supply Chain Forecast** | 7-day demand forecast, stockout risk and reorder suggestions |
| **Workflows** | Every AI decision: auto-executed, waiting for approval, approved, rejected or overridden by a manager |

The home screen answers **five questions, in order**:

1. **What is wrong?** The headline shipment and its risk score (the *Melt Index*)
2. **What will happen?** The probability that the cargo spoils
3. **Why?** The factors driving the score (temperature, fridge health, traffic, weather…)
4. **How much is at risk?** The calculation shown in full, e.g. `₹5,00,000 × 77% = ₹3,83,000`
5. **What should we do?** The recommendation, with an Approve button

---

## What makes it different

1. **Cause and effect, not scripted numbers.** The demo never sets a risk score
   directly. Each scenario button only changes a *root cause*, such as "add 95 min of
   traffic delay" or "turn the outside temperature up by 11 °C". The simulation then
   works out what happens next. If the cargo spoils, it is because the model actually
   warmed it up. Automated tests check this.
2. **The modules are connected.** Machine health, weather and traffic all feed the same
   shipment risk score, so a problem in one area shows up everywhere it matters.
3. **It optimises for money, not speed.** The route optimiser picks the route with the
   **lowest expected business loss**, not the fastest one.
4. **Explainable by design.** The main risk score is a simple weighted formula anyone
   can check, and every recommendation comes with a written reason.
5. **A human stays in control.** High-impact actions always need a timestamped manager
   approval. Managers can also override the AI's choice, and the override is logged.
6. **It never crashes the demo.** If the weather API, a model file or the internet is
   unavailable, the app falls back safely and labels the data honestly.

---

## The 4-minute demo

The full presenter script is in **[DEMO.md](DEMO.md)**. There is also a **▶ Guided
demo** button in the app header that runs the whole story by itself.

**Always press Reset before a run.** Then press the Scenario Injector buttons at the
bottom of the Control Tower:

| Step | What we change (root cause only) | What the system works out by itself |
|---|---|---|
| 0 | Nothing (after Reset) | Shipment SC-1042 is **SAFE**, with cargo holding at −18 °C |
| 1 | Traffic incident: **+95 min delay** | **LOW**: the arrival margin shrinks, but the cargo is still cold |
| 2 | Fridge unit RF-204 starts wearing out fast | **HIGH**: cooling weakens, the anomaly detector fires, risk climbs |
| 3 | Heatwave: **+11 °C**, storm on the lane | **CRITICAL**: cargo warms past the safe limit and shelf life burns |
| 4 | Manager approves the suggested reroute | Risk roughly halves and the avoided loss is recorded |
| 5 | Repair RF-204 | The cargo cools down again on its own; nobody "lowered the score" |

The truck is still on the road throughout the story (about three-quarters of the way
to Pune at the climax). Exact numbers vary a little between runs because the weather
is live. **The shape of the story is always the same**, and the tests check this.

---

## What is real and what is simulated

We are upfront about this:

| Data | Status |
|---|---|
| **Weather** | ✅ **Live** from Open-Meteo (free, no API key) for 14 points along the routes |
| Sensor readings, traffic, demand history | 🔁 **Simulated** by the app's own models |
| Workflow execution | 🔁 **Simulated**: updates the database and writes a log, but no real courier or ERP system is called |
| Risk scores, forecasts, failure probabilities | 🔮 **Predicted** by the app's models |

The **Melt Index** is a transparent weighted formula, not a scientifically validated
measurement. If the internet is down, the weather falls back to a simulated daily
temperature curve and is labelled **SIMULATED** on screen.

---

## How to run it

### Option 1: Docker (simplest, any OS)

```bash
docker build -t opsgenie-ai .
docker run -p 8000:8000 opsgenie-ai
```

Open **http://localhost:8000**. The UI, API and API docs are all served from this one
address.

### Option 2: Windows (about 10 minutes)

You need **Python 3.11+** and **Node 18+** installed.

```powershell
cd OpsGenieAI
.\setup.ps1             # installs everything, trains the 4 models, seeds the database, runs tests
```

Then, in two separate terminals:

```powershell
.\start-backend.ps1     # API at http://localhost:8000/docs
.\start-frontend.ps1    # App at http://localhost:5173
```

Open **http://localhost:5173**. Use `localhost`, not `127.0.0.1`.

<details>
<summary><b>Option 3: macOS / Linux (manual setup)</b></summary>

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

When the app opens, the board is **already moving**: the simulated clock is running,
shelf life is ticking down, and traffic follows a rush-hour pattern.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React + Vite, Tailwind CSS |
| Backend | Python, FastAPI, SQLAlchemy |
| Database | SQLite (switching to PostgreSQL needs one setting change) |
| Machine learning | scikit-learn: Gradient Boosting, Isolation Forest |
| Live data | Open-Meteo weather API |
| Deployment | Docker, Render |

---

## How it works (technical deep dive)

> This section is for technical reviewers. Click any heading to expand it.

<details>
<summary><b>Architecture</b></summary>

```
┌─────────────────────────────┐
│   React + Vite dashboard    │  refreshes from /api/dashboard every 4s
└──────────────┬──────────────┘
               │ HTTP/JSON
┌──────────────┴──────────────┐
│      FastAPI backend        │
│                             │
│  simulation/physics.py   ← THE CORE. Every 3s it advances the world by
│                            6 simulated minutes: machine wear, sensor
│                            readings, cargo temperature, route delay,
│                            inventory, then recalculates every prediction.
│                             │
│  providers/                ← DATA INPUTS. Each data stream tries
│                            live → user → simulated, item by item.
│                             │
│  services/risk_engine.py   Melt Index, spoilage, expected loss, route optimiser
│  services/maintenance.py   anomaly, failure probability, remaining life
│  services/forecasting.py   demand, stockout, reorder
│  services/decision_engine  approval rules, workflow execution
│  services/priority.py      picks the dashboard's headline decision
│  services/provenance.py    LIVE / SIMULATED / PREDICTED labels
│  services/explain.py       written explanations (rule-based, no LLM)
└──────────────┬──────────────┘
               │ SQLAlchemy
┌──────────────┴──────────────┐
│   SQLite (opsgenie.db)      │
└─────────────────────────────┘
```

Two background loops run independently, so one can't block the other:

- **Physics loop** (every 3 s) advances the simulated world.
- **Weather loop** (every 10 min) makes one batched Open-Meteo request. A slow or
  unreachable API can never freeze the simulation.

Everything goes through the same path: `physics.tick()` → `risk_engine.recalculate()`.
Scenario buttons apply their cause and then run the **same** tick, so a button can
never produce a state the live simulation couldn't reach by itself.

The clock is **simulated** (a fixed step per tick), which makes the demo repeatable
without scripting it: the same starting point always produces the same result.
</details>

<details>
<summary><b>The cause-and-effect chain</b></summary>

```
outside weather (live from Open-Meteo, or a labelled fallback)
  + fridge cooling power (falls as the unit wears out)
      → cargo temperature            Newton's law of cooling
      → minutes outside safe range   counted ONLY while cargo is actually too warm
      → shelf-life burn rate         Q10 rule: warm cargo ages faster
traffic congestion + incidents + weather
      → route delay → arrival time → time to spare
all of the above
      → Melt Index → spoilage probability → expected loss → recommendation → workflow
```

These tests make sure the chain is real, not faked:

| Test | What it proves |
|---|---|
| `test_no_scenario_can_assign_a_consequence` | scenarios can only change causes, never results |
| `test_the_cold_chain_breach_is_earned_by_the_thermal_model` | a breach only happens if the cargo really got too warm |
| `test_the_traffic_incident_only_touches_delay` | a traffic event only affects the route |
| `test_a_healthy_world_stays_calm_when_time_passes` | the simulation doesn't invent a crisis |
| `test_weather_actually_influences_the_risk_score` | outside temperature alone moves the score |
| `test_arc_is_identical_three_times_in_a_row` | the demo is repeatable |
</details>

<details>
<summary><b>The Melt Index (the risk score)</b></summary>

A simple weighted formula, deliberately **not** a black-box model, so anyone can see why
the number moved:

```
MeltIndex = 0.25·Temperature + 0.20·Refrigeration + 0.15·Traffic
          + 0.15·Weather     + 0.15·ShelfLife     + 0.10·ETA
```

| Component | How it's calculated | Where the input comes from |
|---|---|---|
| Temperature | projected minutes outside safe range ÷ 240 × 100 | the thermal model |
| Refrigeration | `100 − fridge health` | the machine's wear over time |
| Traffic | `delay ÷ 60 min × 100` | incident + congestion + weather delay |
| Weather | CLEAR 0 · RAIN 40 · STORM 70 · EXTREME 100 | Open-Meteo, or labelled fallback |
| Shelf life | `100 × (1 − remaining ÷ window)` | Q10 burn under warm conditions |
| ETA | 100 if it will arrive late, else `100 − hours_to_spare × 20` | calculated arrival time |

**Risk bands:** 0–20 SAFE · 21–40 LOW · 41–60 MODERATE · 61–80 HIGH · 81–100 CRITICAL

Risk is calculated **separately for each route option**. An alternative route can move
the load to a healthy standby fridge unit, which is why it can win on expected loss
even when it is longer.
</details>

<details>
<summary><b>The thermal model (how the cargo warms up)</b></summary>

Two constants, and the **ratio between them** is what matters:

```
BOX_CONDUCTANCE_PER_HOUR = 0.30      # how fast outside heat leaks in
MAX_COOLING_C_PER_HOUR   = 19.2      # cooling power at 100% efficiency

T_equilibrium = T_outside − 64 × efficiency
```

Where the cargo temperature settles:

| Fridge efficiency | 30 °C outside | 32 °C | 38 °C | 41 °C |
|---|---|---|---|---|
| 90.8% (standby RF-205) | −28.1 | −26.1 | −20.1 | −17.1 |
| 85.8% (RF-204, healthy) | −24.9 | −22.9 | −16.9 | **−13.9** |
| 70% | **−14.8** | **−12.8** | **−6.8** | **−3.8** |
| 60% | **−8.4** | **−6.4** | **−0.4** | **+2.6** |

**Bold = unsafe.** Frozen food must stay at −15 °C or colder in transit (Codex
quick-frozen food rule). A healthy unit holds in any weather. A worn unit holds until a
heatwave arrives. **Wear plus heat together** is what breaks the cold chain. That
pattern comes out of the physics; it wasn't tuned to make the demo work.

When the cargo is too warm, shelf life burns faster: `2^(excess °C / 10)` (the Q10
rule, capped at 6×). The app explains this in plain English, for example:

> "Heat leaks in at 12.4 °C/h against 9.4 °C/h of cooling, so the box is heading for
> 3 °C. That is above the −15 °C safe maximum, so the cold chain fails."
</details>

<details>
<summary><b>Route delay and weather</b></summary>

Delay is always **calculated**, never typed in:

```
delay_minutes = incident_delay + congestion_delay + weather_delay
```

- **Incident:** set by a scenario, then clears at 6 min per simulated hour
- **Congestion:** follows a rush-hour curve that peaks at 09:30 and 18:30
- **Weather:** adds 0% / 8% / 18% / 30% to travel time depending on conditions

Weather affects two things:

- the **weather risk** component and the route delay
- the **outside temperature** in the thermal model (hotter outside → more heat leaks
  in → a worn fridge can't keep up → spoilage risk rises)

A heat rule treats ≥38 °C as STORM and ≥42 °C as EXTREME even without rain, because a
heatwave is a cold-chain emergency in its own right.

| Weather source | Meaning | Label on screen |
|---|---|---|
| `LIVE_OPEN_METEO` | the API answered | **LIVE** |
| `SIMULATED_FALLBACK` | API unreachable → simulated daily curve | **SIMULATED** |
| `SIMULATED_INJECTED` | a demo scenario is overriding the temperature | **SIMULATED** |

If only some waypoints respond, the live ones are kept and only the missing ones are
simulated.
</details>

<details>
<summary><b>Where machine learning is used</b></summary>

Four scikit-learn models, trained at setup on **synthetic** data:

| Model | Algorithm | What it predicts | Quality check |
|---|---|---|---|
| Demand forecast | Gradient Boosting (one per product) | demand for the next 7 days | must beat a 7-day moving average |
| Anomaly detection | Isolation Forest (trained on normal operation only) | unusual sensor behaviour | degraded readings must score as more abnormal |
| Failure within 24 h | Gradient Boosting Classifier | chance a machine fails in the next day | ROC AUC 0.987 on observable cases, beats the simple health rule |
| Spoilage | Gradient Boosting Classifier | chance cargo spoils (optional, via `USE_ML_SPOILAGE=true`) | within 5% of the best achievable on this data |

**Failure model results** (tested on machines it had never seen):

| | ROC AUC | Brier score (lower is better) |
|---|---|---|
| ML classifier, all cases | **0.900** | **0.076** |
| Simple health rule, all cases | 0.845 | 0.247 |
| ML classifier, observable cases | **0.987** | |
| Simple health rule, observable cases | 0.927 | |

"Observable" leaves out cases where the fault hadn't started yet, which no sensor could
detect. In the demo the model tracks RF-204 from 3% → 91% (fault) → 99% (heat) → 1%
(after repair).

The anomaly detector sees **real drift**: sensor readings are generated from the
machine's actual condition every tick, so nothing is injected to trigger it.

Two places use a simple formula on purpose instead of ML, so they stay predictable and
explainable:

- **Spoilage probability** defaults to a calibrated curve on the Melt Index (the ML
  version is one setting away).
- **Condition risk**, which decides whether a maintenance workflow is raised, comes
  straight from the health score. The separate **Failure < 24h** figure is the ML model.

**Every prediction has a fallback.** If a model file is missing or broken, the app uses
a rule-based calculation instead and keeps running. Check what is loaded at
[`/api/health`](http://localhost:8000/api/health).
</details>

<details>
<summary><b>Decision rules (when the AI may act on its own)</b></summary>

| Confidence | Money at stake | What happens |
|---|---|---|
| any | more than ₹1,00,000 | **A human must approve.** Never automatic |
| any | ₹25,000 – ₹1,00,000 | Recommended, waits for approval |
| HIGH (≥ 0.70) | less than ₹25,000 | **Done automatically** and logged |
| LOW (< 0.40) | any | Recommended only, flagged as low confidence |

A reroute is only suggested if it saves **at least ₹15,000 and at least 5%** of the
shipment value. This stops the system from rerouting trucks for tiny gains.

Decisions can't be changed once made (a second approval returns HTTP 409). Managers can
**override** the AI's route choice, and this is logged as `OVERRIDDEN`.
</details>

<details>
<summary><b>Reliability: what happens when things fail</b></summary>

| Failure | What the app does |
|---|---|
| Weather API down or slow | switches to a simulated daily curve, labelled **SIMULATED** |
| A model file is missing | uses a rule-based fallback; `/api/health` shows it |
| One simulation step errors | logs it and carries on; the world is never left half-updated |
| No internet for map tiles | shows the routes as a table instead |
| Backend down | shows a banner and keeps the last good data on screen |
| Database corrupted | rebuild in seconds with `python data/seed.py --force` |

Other safeguards:

- **Old data is pruned automatically**, so the app can run for hours without growing.
- **Alerts don't spam.** A new alert appears only when a shipment's risk band changes.
- **The demo resets itself** if left alone for a long time, so a judge opening a hosted
  link days later still sees a fresh, meaningful demo. It never resets while someone is
  using it.
</details>

<details>
<summary><b>Dashboard design choices</b></summary>

- **Only data and status use colour.** Everything else is neutral, so your eye goes
  straight to what is wrong.
- **Four status colours, not six**, and the band name is always written next to the
  colour, so it works for colour-blind users.
- **One clear trend line** with a **Drivers** toggle, instead of five overlapping lines.
- **Progressive disclosure:** the full shipment table, equipment health, forecast and map
  are one click away, so the home screen stays focused on the decision.
- **No business logic in the browser.** The backend calculates everything and the
  frontend displays it, so the numbers on screen always agree with each other.
- Chart colours are checked for colour-blind safety and contrast, not picked by eye.
</details>

<details>
<summary><b>Tests</b></summary>

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q      # ~2.5 min
```

| File | What it covers |
|---|---|
| `test_demo_arc.py` | the full story: escalation, a real breach, linked modules, approvals, recovery, repeatability |
| `test_pipeline.py` | weather handling, data labelling, simulation rules, the headline summary |
| `test_providers.py` | data inputs: fallbacks, labelling, failing sources handled safely |
| `test_risk_engine.py` | Melt Index formula, risk bands, per-route scoring, route optimiser |
| `test_decision_engine.py` | every approval rule, workflow lifecycle, overrides |
| `test_failure_model.py` | the failure model's behaviour across the demo |
| `test_clock.py` · `test_dispatch.py` · `test_lifecycle.py` | simulated clock, deliveries and next loads, automatic demo reset |
| `test_api.py` | every API endpoint, input validation, full demo over HTTP |
| `test_formatting.py` | Indian rupee formatting (₹1,00,000) |

The tests check **relationships, not fixed numbers**: risk always rises as conditions
worsen, `expected_loss = value × probability`, a breach requires the cargo to actually be
too warm, and the recommendation always has the lowest expected loss.
</details>

<details>
<summary><b>API reference</b></summary>

Interactive docs: **http://localhost:8000/docs**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/dashboard` | everything the home screen needs |
| GET | `/api/shipments/{id}` | full shipment detail, including heat balance and routes |
| GET | `/api/shipments/{id}/routes` | route options with expected loss for each |
| POST | `/api/shipments/{id}/reroute` | reroute a shipment (`{route_id}`) |
| GET | `/api/machines/{id}` | machine health, wear rate, sensors |
| GET | `/api/forecast` · `/api/inventory` | demand, stockout, reorder |
| GET | `/api/workflows` · POST `/{id}/approve` · `/{id}/reject` | decision history and approvals |
| GET | `/api/simulation/scenarios` | the demo scenario buttons |
| POST | `/api/simulation/trigger-event` | apply one root cause and return the result |
| POST | `/api/simulation/tick` | advance the simulation by one step |
| GET | `/api/simulation/environment` | simulated clock and weather source |
| POST | `/api/simulation/refresh-weather` | fetch live weather now |
| POST | `/api/simulation/reset` | reset to the starting state (keeps live weather) |
| GET | `/api/copilot/ask?q=` | rule-based Q&A over the data (no LLM) |
| GET | `/api/health` | which models and weather points are live |
</details>

<details>
<summary><b>Configuration</b></summary>

`backend/.env` (see `.env.example`):

| Variable | Default | What it does |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./opsgenie.db` | use a Postgres URL to move to a server |
| `CORS_ORIGINS` | `http://localhost:5173,...` | allowed frontend addresses |
| `PHYSICS_ENABLED` | `true` | `false` freezes the simulation |
| `PHYSICS_TICK_SECONDS` | `3` | real seconds between simulation steps |
| `SIM_MINUTES_PER_TICK` | `6` | 1 real minute ≈ 2 simulated hours |
| `SETTLE_STEP_MINUTES` | `15` | step size when a scenario button is pressed |
| `AUTO_RESET_ENABLED` | `true` | reset the demo automatically when idle |
| `IDLE_PAUSE_SECONDS` | `90` | pause the simulation when nobody is watching |
| `IDLE_RESET_MINUTES` | `20` | reset for a visitor returning after this long |
| `EPISODE_SIM_HOURS` | `24` | restart an unattended demo after this many simulated hours |
| `ACTION_GRACE_MINUTES` | `5` | never auto-reset within this long of a button press |
| `WEATHER_ENABLED` | `true` | `false` forces simulated weather |
| `WEATHER_TIMEOUT_SECONDS` | `4` | |
| `WEATHER_REFRESH_SECONDS` | `600` | |
| `USE_ML_SPOILAGE` | `false` | `true` uses the ML spoilage model |

`frontend/.env`: `VITE_API_BASE_URL` and `VITE_POLL_INTERVAL_MS` (default 4000).

Authentication is out of scope for this single-user demo.
</details>

---

## Known limitations

We'd rather state these clearly than overclaim:

- **The thermal model is reasonable, not validated.** It uses standard physics (Newton's
  law of cooling) and a real food-science rule (Q10), but it hasn't been fitted to real
  truck data.
- **The Melt Index weights were chosen by hand**, not learned from real spoilage data.
- **All ML training data is synthetic.** The models learned from our data generator, not
  from real cold-chain operations.
- **The ML spoilage model's ROC AUC is ~0.67.** That is close to the best possible on
  this deliberately noisy data, but it shouldn't be quoted out of context.
- **Remaining useful life is a straight-line estimate**, not a full survival model.
- **Traffic and demand are simulated.** Real providers can be plugged in where the
  weather provider already is.
- **The dashboard refreshes every 4 seconds** rather than using live push (websockets).
  For one user this looks the same.
- **Exact demo numbers vary slightly** between runs because the weather is live. The
  story is always the same.

## What's next

- Real IoT sensor feeds, plus live traffic and routing APIs, plugged in the same way
  weather already is
- PostgreSQL (a one-line setting change) and live websocket updates
- Real ERP / warehouse / courier integration, so workflows trigger real actions
- An LLM copilot that can answer questions by calling these APIs, while the risk score
  itself stays calculated by the transparent engine, never by the language model
