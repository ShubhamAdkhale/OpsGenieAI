# OpsGenie AI — presenter script

**Total time: 4 minutes.** One browser tab, one terminal running the backend.

> **Press Reset before every run.** The Scenario Injector at the bottom of the
> Control Tower has the button.

---

## Before you start

```powershell
.\start-backend.ps1     # wait for "Weather refreshed: 14/14 waypoints live"
.\start-frontend.ps1
```

Open **http://localhost:5173**. Check the top strip says **LIVE Weather**. If it
says SIMULATED, you have no internet — the demo still works end to end, and the
strip is telling the truth rather than pretending.

Not presenting live? The **▶ Guided demo** button in the header runs this whole
script on its own — each step presses one root cause, jumps to the page where
the consequence shows, and prints the result the model computed. It opens by
itself on a first visit, so a judge using the hosted link gets the same arc.

The board is **already moving** when you arrive. The simulated clock in the top
right is advancing, shelf life is burning down, congestion is following a
rush-hour curve. Nothing is waiting for you to press a button.

---

## The 10-second opening

> "This is a cold-chain control tower. It does not show me metrics — it tells me
> which shipment is about to cost me money, why, and what to do about it."

Point at the top card. Read it out. At baseline it is already flagging a real
exposure — an ice-cream load with 11 hours of shelf life on a rainy lane — with
a probability, an expected loss in rupees, the causes, and one recommended
action.

> "Everything above the fold answers five questions: what is wrong, what will
> happen, why, how much is at risk, and what to do."

---

## Step 1 — Traffic incident

Press **Traffic incident on the lane**.

The button says what it changes: `cause: incident delay +95 min`. It does **not**
say what the risk score becomes.

> "I've added 95 minutes of incident delay to one lane. That's the only thing I
> changed. Watch what the system does with it."

SC-1042 moves from SAFE to LOW. Note what did **not** happen:

> "The cargo is still cold — minus eighteen. No excursion minutes were added,
> because nothing warmed up. The score moved because the ETA margin shrank and
> the shelf life burned for another 45 minutes. That distinction is the whole point:
> a traffic jam does not spoil food directly, it spoils food by keeping it in a
> truck for longer."

---

## Step 2 — Refrigerant leak

Press **Refrigerant leak on RF-204**.

> "This does not set a health score. It sets a **wear rate** — eight points of
> cooling efficiency per operating hour — and then lets two and a half hours of simulated
> transit pass."

Open **Predictive Maintenance** in the nav.

> "Efficiency fell because the rate was integrated over time. The sensor trace
> is generated from that efficiency, so temperature, vibration and current
> drifted together — and the IsolationForest picked up a real trajectory. There
> is no injected outlier anywhere in this build."

Back to the Control Tower. SC-1042 is now **HIGH** and has taken over the top
slot from the ice cream.

> "And here is the cross-module link. I degraded a *machine*. The card now shows
> a *shipment* at about two and a half lakh of expected loss, and it names RF-204 as
> the cause. Predictive maintenance is not a separate tab — it is an input to
> operations."

Note the gate line:

> "About two lakh of impact exceeds the one-lakh auto-execution ceiling, so
> it will not act without me. That is a safety property, not a preference."

---

## Step 3 — Heat and storm front

Press **Heat + storm front**.

> "Ambient goes up eleven degrees and the lane re-bands to STORM."

Now open SC-1042 (click through from the card) and read the **Heat balance**
panel out loud:

> "Heat leaks in at twelve degrees an hour against nine degrees an hour of
> cooling, so the box is heading for plus three. That is above the minus fifteen
> limit for frozen food in transit, so the cold chain fails."

> "*Now* the excursion counter is running — over two hours of it, and every
> minute was earned by the cargo actually being too warm. Shelf life is
> burning faster than the clock, because warm food ages faster: that's the Q10
> rule, a doubling every ten degrees."

Back to the Control Tower: **CRITICAL**, ~77% spoilage, ~₹3.8L expected loss.

> "Five lakh of chicken times seventy-seven percent. The multiplication is on
> the card, not just the total."

---

## Step 4 — The decision

Open the shipment's route comparison.

| | Route A | Route B |
|---|---|---|
| Effective ETA from the start of the trip | ~7 h 10 min | ~5 h 20 min |
| Reefer | RF-204, failing | RF-205 standby, 88% |
| Spoilage risk | ~77% | ~36% |
| Expected loss | ~₹3.8L | ~₹1.8L |

The truck is about three-quarters of the way to Pune at this point — genuinely
still on the road, which is what makes the reroute a real decision.

> "The optimizer is not minimizing travel time. It is minimizing **expected
> business loss**. Route B wins because it hands the load to a healthy reefer
> at the Chakan cold hub — the equipment, again, driving the operational
> decision."

Press **Approve recommendation** on the priority card.

> "Approved, logged, executed. Risk drops from eighty-three to about fifty, and
> two lakh of loss avoided lands in the Act stage of the pipeline."

---

## Step 5 — Recovery is causal too

Press **Repair RF-204**.

> "The leak is fixed, so the wear rate goes back to normal and efficiency is
> restored. Nobody lowered a risk score — the cargo starts cooling again
> because the physics changed back."

Watch the cargo temperature fall on the next few ticks.

> "Note it does not go straight back to safe. More than two hours of
> excursion already happened and eight hours of shelf life are gone. The system
> does not pretend damage un-happens, which is exactly why the reroute needed
> approving when it did rather than ten minutes later."

---

## If a judge pushes back

**"Is this data real?"**
> "The weather is — Open-Meteo, keyless, fourteen lane waypoints in one request,
> and the strip at the top says which of them answered. Everything else is
> simulated and labelled SIMULATED. The sensor trace is generated from a reefer
> wear model. I'd rather say that plainly than dress it up."

**"Did you hardcode the demo numbers?"**
> "The opposite — and there's a test that enforces it. A scenario can only
> name a root cause: a delay, a wear rate, an ambient offset. There's no field
> it could put a Melt Index in.
> `test_no_scenario_can_assign_a_consequence` fails if anyone adds one."

**"Then how is it repeatable?"**
> "The clock is simulated, not read off the wall, so the same triggers integrate
> to the same state.
> `test_arc_is_identical_three_times_in_a_row` runs the whole arc three times
> and requires identical output."

**"What if Open-Meteo is down?"**
> "Simulated diurnal curve, labelled as such, and the risk engine never notices.
> Same for the models: a missing `.joblib` returns None and the caller uses its
> rule-based path. `/api/health` shows which is live."

**"Is the Melt Index scientific?"**
> "No. It is a transparent weighted formula and the UI says so. Six components,
> published weights, and the card shows each one's point contribution so you can
> see exactly why the number moved. I'd rather have auditable than impressive."

---

## Recovery if something goes wrong

| Problem | Fix |
|---|---|
| Numbers look wrong | Press **Reset**. |
| Board is frozen | The strip says "paused" — `PHYSICS_ENABLED=true` in `backend/.env`. |
| Weather says SIMULATED | No internet. Carry on; it is honest, not broken. |
| Want to step slowly | Press **▸ Step** to advance one tick at a time. |
| Backend died | Restart it; the last data stays on screen with a banner until it returns. |
