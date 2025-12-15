# DCS AI Flight Model (SFM) – Implementation & Tuning Guide

> **Scope:** This document is **only** about the flight model used by **AI‑controlled aircraft** in DCS when you define an SFM in a 3rd‑party mod. Player‑flown AFM/PFM/EFM implementations are intentionally **out of scope**.

This is structured as a Markdown file you can drop directly into a repo/wiki.

---

## Contents

- [1. Scope and background](#1-scope-and-background)
  - [1.1 What “AI SFM” means](#11-what-ai-sfm-means)
  - [1.2 SFM vs GFM from an AI perspective](#12-sfm-vs-gfm-from-an-ai-perspective)
- [2. Where the AI flight model is defined in a mod](#2-where-the-ai-flight-model-is-defined-in-a-mod)
- [3. ](#3-sfm_data-ai-physics-inputs)[`SFM_Data`](#3-sfm_data-ai-physics-inputs)[: AI physics inputs](#3-sfm_data-ai-physics-inputs)
  - [3.1 Aerodynamics block](#31-aerodynamics-block)
  - [3.2 Engine block](#32-engine-block)
- [4. “Basic aircraft stats” and how AI uses them](#4-basic-aircraft-stats-and-how-ai-uses-them)
- [5. Implementation workflow for a new AI SFM aircraft](#5-implementation-workflow-for-a-new-ai-sfm-aircraft)
- [6. Tuning for realistic AI performance](#6-tuning-for-realistic-ai-performance)
- [7. Limitations of the AI SFM](#7-limitations-of-the-ai-sfm)
- [8. Workarounds and advanced tricks](#8-workarounds-and-advanced-tricks)
- [9. Relationship to other AI flight models](#9-relationship-to-other-ai-flight-models)
- [10. Quick reference tables](#10-quick-reference-tables)

---

## 1. Scope and background

### 1.1 What “AI SFM” means

When you define an aircraft in a 3rd‑party DCS mod, you can give it a **Standard Flight Model (SFM)**. For AI‑only aircraft, this SFM is what the AI autopilot flies.

Key points for this doc:

- We only care about **how the AI interprets your SFM**.
- We assume the aircraft is *not* user‑flyable, or if it is, you still want the AI‑side SFM to be correct.
- We treat SFM as a **data‑driven AI flight model** defined entirely in Lua.

Conceptually, the SFM is a **point‑mass trajectory model**:

- Forces: lift, drag, thrust, weight.
- State: position, velocity, attitude.
- No detailed control‑surface physics, no per‑surface failure model.
- Aerodynamics expressed via coefficients (e.g., `Cy`, `Cx`) as functions of Mach and AoA, but compressed into a small set of parameters and a Mach table (`table_data`).

From the AI’s point of view, the SFM is a **black box**: given a commanded attitude / G / throttle, the FM returns forces and moments; the AI’s guidance logic sits on top of that.

### 1.2 SFM vs GFM from an AI perspective

There are two broad AI flight model families in DCS today:

- **SFM‑based AI** (what this guide covers):
  - Used by many legacy and community AI aircraft.
  - Driven by `SFM_Data` + basic stats in the aircraft Lua.
- **GFM‑based AI** (General Flight Model):
  - Newer unified AI FM used by some ED‑supplied AI aircraft.
  - Not currently something you configure directly in a 3rd‑party SFM mod.

If you are authoring a **Lua‑only 3rd‑party aircraft**, you should assume your AI aircraft will use **SFM**. Everything below is about how to shape that SFM so the AI flies realistically.

---

## 2. Where the AI flight model is defined in a mod

In a typical aircraft mod, the main aircraft definition Lua (e.g. `MyJet.lua`) includes three areas that matter for AI flight behavior:

1. **Basic aircraft definition**\
   Overall physical properties:

   - dimensions, wing area, reference area
   - empty/nominal/max mass
   - fuel capacity
   - gear, flaps, pylons, etc.

2. **“Basic aircraft stats” block**\
   A set of high‑level performance numbers and limits that AI logic uses to:

   - decide cruise speeds, climb profiles, and intercept speeds
   - respect structural G limits
   - know takeoff / landing speeds and rotation AoA

3. ``** block**\
   The **actual AI flight model**:

   - `aerodynamics` sub‑table → lift & drag vs Mach, AoA, configuration.
   - `engine` sub‑table → thrust vs Mach and altitude.

Skeleton (heavily simplified):

```lua
-- inside your aircraft table, e.g. local MyJet = {

-- 2) Basic aircraft stats (AI uses these directly)
M_empty         = 9000,
M_nominal       = 14000,
M_max           = 19000,
M_fuel_max      = 4500,

H_max           = 18000,   -- [m]
CAS_min         = 150,     -- [m/s] min controllable IAS (AI)
V_opt           = 220,     -- [m/s] AI "preferred" cruise speed
V_take_off      = 75,      -- [m/s]
V_land          = 70,      -- [m/s]

AOA_take_off    = 0.16,    -- [rad] AI rotation AoA

bank_angle_max  = 60,      -- [deg] nominal AI bank limit
Ny_min          = -3,
Ny_max          = 8,
Ny_max_e        = 7.5,     -- effective G limit used by AI

Mach_max        = 2.0,
V_max_sea_level = 400,     -- [m/s]
V_max_h         = 720,     -- [m/s] max speed at altitude
Vy_max          = 250,     -- [m/s] best climb rate

wing_area       = 50.0,
thrust_sum_max  = 9000,    -- [kgf]
thrust_sum_ab   = 15000,   -- [kgf]

-- 3) SFM flight model used by AI
SFM_Data = {
    aerodynamics = { ... },
    engine       = { ... },
},

-- etc.
```

For AI behavior, **all three** sections matter. `SFM_Data` defines what is physically possible; the **basic stats** constrain what the AI will actually attempt to do.

---

## 3. `SFM_Data`: AI physics inputs

`SFM_Data` is the core AI flight model. DCS samples it every update and applies forces and moments to the AI aircraft.

At the top level:

```lua
SFM_Data = {
    aerodynamics = { ... },
    engine       = { ... },
}
```

### 3.1 Aerodynamics block

This controls lift, drag, and roll response.

#### 3.1.1 Global aero parameters

These apply across all Mach numbers (and get modulated by the Mach table):

| Field      | Effect on AI flight behavior                                                                                           |
| ---------- | ---------------------------------------------------------------------------------------------------------------------- |
| `Cy0`      | Lift coefficient at 0° AoA. Use for small trim corrections (e.g. nose‑heavy vs nose‑light feel).                       |
| `Mzalfa`   | Pitching moment vs AoA. Higher → stronger pitch authority and more “eager” nose; too high can make AI pitch oscillate. |
| `Mzalfadt` | Pitch damping vs AoA rate. Higher → more damping, less oscillation.                                                    |
| `kjx`      | Roll inertia/damping around x‑axis. Affects how quickly the aircraft responds and settles in roll.                     |
| `kjz`      | Yaw inertia/damping. Influences yaw stability and how “snaky” AI looks in turns.                                       |
| `Czbe`     | Side‑force vs sideslip. Helps stabilise sideslip; can reduce weird yaw oscillations.                                   |
| `cx_gear`  | Additional drag with gear down. Impacts AI approach and go‑around behavior.                                            |
| `cx_flap`  | Additional drag with flaps. Tuning this helps keep AI from floating excessively on landing.                            |
| `cy_flap`  | Extra lift from flaps. Impacts AI approach AoA and speed.                                                              |
| `cx_brk`   | Drag from airbrake. Affects deceleration when AI deploys boards.                                                       |

You generally keep these within plausible ranges (borrow from a similar ED aircraft) and do most tuning in the Mach table.

#### 3.1.2 Mach table (`table_data`)

`table_data` is the main knob set for how the AI aircraft flies at different Mach numbers:

```lua
SFM_Data = {
  aerodynamics = {
    table_data = {
      -- M     Cx0     Cya     B       B4      Omxmax  Aldop  Cymax
      { 0.0,  0.020,  0.060,  0.08,   1.00,   2.50,   20.0,  1.20 },
      { 0.5,  0.021,  0.058,  0.07,   0.60,   3.50,   19.0,  1.15 },
      { 0.9,  0.024,  0.050,  0.06,   0.30,   4.00,   17.0,  1.05 },
      { 1.2,  0.032,  0.045,  0.08,   0.50,   3.50,   14.0,  0.95 },
      { 1.6,  0.040,  0.040,  0.30,   2.00,   2.00,   12.0,  0.70 },
    },
  },
}
```

Each row is evaluated at a particular **Mach number** `M` and interpolated between.

- `M` – Mach number for this row.
- `Cx0` – baseline drag coefficient at small AoA. Lower → higher top speed.
- `Cya` – lift slope (lift per degree of AoA). Higher → more G available at a given AoA.
- `B`, `B4` – coefficients for drag that grows with lift (induced/extra drag). These largely control **energy bleed in turns**.
- `Omxmax` – maximum roll rate at this Mach (rad/s). Higher → snappier AI roll response.
- `Aldop` – AoA (deg) where the FM treats the aircraft as approaching departure/stall. Above this, lift stops increasing and drag spikes.
- `Cymax` – maximum lift coefficient. Caps total G the aircraft can generate even if AI commands more AoA.

From an AI standpoint:

- `Cya` + `Cymax` + mass/wing area determine **max G** and **corner speed**.
- `Cx0` + `B` + `B4` + engine thrust determine **top speed** and **sustained turn performance**.
- `Omxmax` limits **how “robotic”** AI roll looks at different speeds.
- `Aldop`/`Cymax` prevent AI from sitting at absurd AoA forever.

### 3.2 Engine block

The `engine` sub‑table defines available thrust vs Mach and indirectly vs altitude.

#### 3.2.1 Scalar engine parameters

Common fields in the `engine` block:

| Field     | Description                                                                                             |
| --------- | ------------------------------------------------------------------------------------------------------- |
| `Nmg`     | Idle RPM / normalized engine speed. Affects spool and some AI taxi behavior.                            |
| `MinRUD`  | Minimum throttle command (usually `0.0`).                                                               |
| `MaxRUD`  | Maximum throttle command (usually `1.0`).                                                               |
| `MaksRUD` | Throttle setting corresponding to **military power** (no afterburner).                                  |
| `ForsRUD` | Throttle setting where **afterburner** engages.                                                         |
| `type`    | Engine type string (e.g. `"TurboJet"`, `"TurboFan"`).                                                   |
| `hMaxEng` | Altitude (km) where thrust effectively reaches minimum (engine “ceiling”).                              |
| `dcx_eng` | Extra drag from engine nacelles/intakes.                                                                |
| `cemax`   | Fuel consumption coefficient for MIL power (AI uses it for fuel estimation, not precise fuel flow sim). |
| `cefor`   | Same but for afterburner.                                                                               |
| `dpdh_m`  | Thrust decay per meter of altitude in MIL. Higher → faster thrust loss with altitude.                   |
| `dpdh_f`  | Thrust decay per meter in AB.                                                                           |

You mostly tune these to get realistic **top speed and climb vs altitude** for the AI.

#### 3.2.2 Mach thrust table

`engine.table_data` gives thrust vs Mach:

```lua
engine = {
  -- ...scalars...
  table_data = {
    -- M     Pmax      Pfor
    { 0.0,  90000,    150000 },
    { 0.5,  95000,    170000 },
    { 1.0,  90000,    180000 },
    { 1.5,  75000,    170000 },
    { 2.0,  60000,    150000 },
  },
}
```

- `M`    – Mach number for this row.
- `Pmax` – thrust (Newtons) in MIL at this Mach.
- `Pfor` – thrust in afterburner at this Mach.

AI doesn’t see these directly, but the FM uses them to decide if the aircraft can reach the speeds and climb rates that the AI logic requests.

---

## 4. “Basic aircraft stats” and how AI uses them

The **basic stats block** is not part of the aerodynamics math, but the AI uses it heavily to plan and constrain its maneuvers.

Important fields and their AI implications:

### 4.1 Masses and geometry

| Field            | Role                                                                                           |
| ---------------- | ---------------------------------------------------------------------------------------------- |
| `M_empty`        | Empty mass. Used with loadout and fuel to compute gross weight.                                |
| `M_nominal`      | Typical mission mass. Affects some AI performance assumptions.                                 |
| `M_max`          | Structural max mass; informs AI about feasible loads.                                          |
| `M_fuel_max`     | Internal fuel mass. Used by AI for fuel planning and endurance.                                |
| `wing_area`      | Reference wing area. Together with mass and `Cya`/`Cymax` this defines wing loading and max G. |
| `thrust_sum_max` | Sum of engine thrust in MIL (kgf). Should be consistent with `engine.table_data`.              |
| `thrust_sum_ab`  | Sum of engine thrust in AB (kgf).                                                              |

These set the **scale** for your SFM. If they’re wrong, the same `SFM_Data` will behave very differently.

### 4.2 Speed and altitude references

| Field             | AI meaning                                                                         |
| ----------------- | ---------------------------------------------------------------------------------- |
| `H_max`           | Service ceiling. AI generally won’t plan to cruise above this.                     |
| `CAS_min`         | Minimum controllable IAS. AI tries not to fly sustained below this.                |
| `V_opt`           | “Optimal” cruise speed that AI prefers for level flight.                           |
| `V_max_sea_level` | Maximum speed at sea level. AI uses it as a cap for low‑altitude cruise/intercept. |
| `V_max_h`         | Maximum speed at altitude. Used in high‑altitude planning.                         |
| `Mach_max`        | Overall Mach cap. AI respects this even if FM would allow higher.                  |
| `Vy_max`          | Best climb rate. Influences AI climb profile choices.                              |

If these are set unrealistically high, AI will try to use **non‑existent performance** and look like a UFO even if the SFM is reasonable.

### 4.3 G limits and bank limits

| Field            | AI meaning                                                                          |
| ---------------- | ----------------------------------------------------------------------------------- |
| `Ny_min`         | Minimum G (negative). AI usually won’t exceed this in normal flying.                |
| `Ny_max`         | Structural positive G limit. Should match or slightly exceed real structural limit. |
| `Ny_max_e`       | “Effective” positive G limit used in **maneuvering logic** (BFM, hard turns, etc.). |
| `bank_angle_max` | Nominal bank limit in non‑combat maneuvering (turns in cruise, etc.).               |

As a rule of thumb:

- `Ny_max` = structural limit (e.g. 9.0).
- `Ny_max_e` = what you want AI to normally use (e.g. 7.5–8.5).
- If AI is out‑turning human players in full‑fidelity modules, **lower **`` rather than crippling the SFM.

### 4.4 Takeoff and landing references

| Field          | AI meaning                                                |
| -------------- | --------------------------------------------------------- |
| `V_take_off`   | Target IAS at rotation. AI will rotate around this speed. |
| `AOA_take_off` | Target AoA for rotation (rad).                            |
| `V_land`       | Reference approach/landing IAS.                           |

These are especially important for AI behavior at high weights. If you see AI rotating too late/early or consistently floating down the runway, adjust these along with flap lift/drag (`cy_flap`, `cx_flap`).

---

## 5. Implementation workflow for a new AI SFM aircraft

This is a practical step‑by‑step plan to create and tune an AI SFM from scratch.

### Step 0 – Choose a baseline AI aircraft

Pick an ED aircraft with **similar role and performance** whose SFM you can inspect (via Lua):

- For a light fighter (MiG‑21/F‑5 class), start from another light fighter SFM.
- For a heavy fighter/interceptor (F‑4/F‑14 class), pick something with similar thrust‑to‑weight and wing loading.
- For trainers / light attack, pick something like L‑39 or similar.

Copy its `SFM_Data` and basic stats into your mod as a **starting point**, then morph them towards your target aircraft.

### Step 1 – Fill in basic stats from real data

From manuals / reference data:

- Empty, typical, and max takeoff weights (`M_empty`, `M_nominal`, `M_max`).
- Internal fuel (`M_fuel_max`).
- Wing area and approximate span.
- Max level speed at sea level and at a reference altitude.
- Tactical / structural G limits.

Populate the basic stats block first so the SFM has a **sane physical context**.

### Step 2 – Build a first‑pass engine table

1. Estimate thrust in MIL and AB at several Mach numbers (or clone from a similar ED aircraft and scale).
2. Fill `engine.table_data` with 4–6 rows from Mach 0 to your max Mach.
3. Adjust `thrust_sum_max` / `thrust_sum_ab` to be consistent with your table.
4. Set conservative `dpdh_m` / `dpdh_f` so thrust decays reasonably with altitude.

Goal of this pass: **roughly correct top speed and climb** at SL and mid‑altitude for AI.

### Step 3 – Create a first‑pass aero Mach table

Start with copied values from your baseline and then tweak:

- Use the same Mach breakpoints as the baseline initially.
- Adjust per row:
  - `Cx0` for top‑speed tuning at that Mach.
  - `Cya` & `Cymax` to get plausible max G and corner speeds.
  - `B` & `B4` to control energy bleed in sustained turns.
  - `Omxmax` so roll rates match known data (convert deg/s to rad/s).
  - `Aldop` to approximate realistic maximum AoA.

At this stage, you want the AI aircraft to be **in the right ballpark** for speed, climb, and G capability.

### Step 4 – Build simple AI test missions

Create a few missions dedicated to AI performance testing:

1. **Level acceleration / top‑speed tests**

   - Clean aircraft (no stores).
   - AI at several altitudes and power settings; observe max speed reached.

2. **Climb tests**

   - AI climbs from SL to a target altitude at full AB; record time and peak climb rate.

3. **Sustained turn tests**

   - Co‑altitude 1v1 vs a copy of itself.
   - Observe sustained turn rate and energy bleed while AI is in prolonged turning fights.

Adjust `engine.table_data`, `Cx0`, `Cya`, `Cymax`, `B`, `B4` until performance roughly matches available real‑world or reference data.

### Step 5 – Refine AI behavior via basic stats

Once physical performance is acceptable, tune the **AI preferences and limits**:

- Set `Ny_max` to structural, `Ny_max_e` to tactical.
- Clamp `Mach_max`, `V_max_sea_level`, and `V_max_h` to realistic values.
- Set `V_opt` to a reasonable cruise speed (not the absolute max).
- Tune `V_take_off`, `AOA_take_off`, and `V_land` based on AI takeoff/landing behavior in your tests.

At this point your AI should “feel right” in both transit and combat.

---

## 6. Tuning for realistic AI performance

This section focuses on how to shape AI behavior, not just raw performance numbers.

### 6.1 Order of operations

A reliable tuning order:

1. **Mass & thrust** → get rough top speed and climb right.
2. **Lift & G** → tune `Cya`, `Cymax`, and `Ny_*` for realistic instantaneous and sustained G.
3. **Energy bleed** → refine `B` / `B4` so sustained turn performance matches expectations.
4. **Roll & AoA limits** → tune `Omxmax` and `Aldop` for believable roll and stall behavior.
5. **AI caps** → adjust `Mach_max`, `V_max_*`, `V_opt`, and `Ny_max_e` so AI doesn’t exploit unrealistic corners of the FM.

### 6.2 Controlling AI dogfight behavior

The AI guidance logic tries to achieve certain goals (rate fight, nose position, etc.) while obeying the limits you give it:

- **If AI always wins rate fights vs human players**:

  - Lower `Ny_max_e` slightly.
  - Increase `B`/`B4` at the Mach where fights typically happen so the aircraft bleeds more energy when pulling high G.
  - Reduce `Omxmax` at medium Mach to avoid super‑robotic rolls.

- **If AI feels too sluggish**:

  - Increase `Cya` or `Cymax` modestly (watch structural G).
  - Reduce `B`/`B4` slightly to improve sustained turn.
  - Raise `Ny_max_e` toward the structural limit.

- **If AI yo‑yos or oscillates a lot in pitch**:

  - Increase `Mzalfadt` for more pitch damping.
  - Slightly reduce `Mzalfa` if pitch authority is excessive.

### 6.3 Making AI energy management believable

You can’t control the AI’s strategy directly, but you can **force it into realistic trade‑offs**:

- Use **high **``** / **`` in the transonic region where induced drag is nasty → if AI insists on pulling 7–8 G there, it will pay for it in energy.
- Ensure engine thrust drops appropriately with altitude (`dpdh_m`, `dpdh_f`) so AI can’t sustain silly climbs.
- Don’t give AI a `V_opt` that is too close to max speed; they should cruise at a **comfortable margin below**.

---

## 7. Limitations of the AI SFM

Some limitations are inherent to how SFM and AI logic work together.

### 7.1 Physics/model limitations

- SFM is a **point‑mass model** with simplified damping; it does not simulate detailed rigid‑body short‑period dynamics.
- Stall and departure behavior is essentially handled by **hard thresholds** (`Aldop`, `Cymax`) plus drag spikes, not by detailed wing stall mechanics.
- Asymmetric loadouts are only partially represented (mostly via mass and drag), so cross‑controlled or one‑wing‑heavy behavior is limited.

### 7.2 AI control system limitations

- AI uses a **generic autopilot / control law**, not your custom FCS. You can’t directly edit PID gains or stick curves.
- AI does not “feel” buffet or stick forces; it only sees the FM outputs and its own constraints (`Ny_*`, speed caps, AoA limits).
- AI decisions (e.g. when to extend, re‑engage, or climb) come from high‑level behavior code you cannot modify in Lua.

### 7.3 Representational limits in SFM

- The aero tables are **one‑dimensional in Mach**; they don’t offer separate polars for each flap/gear/store configuration beyond simple drag/lift scalars.
- High‑fidelity effects like transonic pitch trim changes, control surface reversal, deep stall, and spins cannot be reproduced faithfully.

Understanding these limits is critical when interpreting AI behavior: sometimes the best you can do is **approximate the trend**, not the exact real‑world response.

---

## 8. Workarounds and advanced tricks

Given the limitations, here are practical techniques to extract more believable AI behavior from SFM.

### 8.1 Use AI stats as “guardrails”

Treat basic stats as **behavior clamps** rather than mere documentation:

- Clamp **G**:

  - `Ny_max` = real structural max.
  - `Ny_max_e` = slightly lower, so AI doesn’t pull absolute max G continuously.

- Clamp **speed**:

  - `Mach_max`, `V_max_sea_level`, `V_max_h` = realistic maxima; don’t let AI demand non‑existent thrust.

- Clamp **bank**:

  - `bank_angle_max` = \~45–60° for routine navigation so AI doesn’t bank 80–90° for every gentle course change.

These guardrails won’t fix physics, but they stop AI from **exposing** the FM’s simplifications.

### 8.2 Shape stalls and high‑AoA behavior

You can fake a more believable stall envelope even with SFM’s simple tools:

- Set `Aldop` to the **realistic max AoA** where the wing would depart.
- Choose `Cymax` such that **max lift** at `Aldop` corresponds to realistic max G at typical combat weight.
- Use higher `B4` values near the high‑AoA Mach range to make drag rise sharply as AI approaches stall.

Result:

- AI can still briefly “spike” high AoA, but if it hangs there, it loses speed quickly and becomes vulnerable, which is realistic enough for most combats.

### 8.3 Faking configuration effects

To approximate different configurations without a full multidimensional polar:

- Use `cx_flap` / `cy_flap` for flap‑down behavior.
- Use `cx_gear` for gear‑down drag.
- Assign **pylon and store drag** via the weapon/pylon definitions so heavy loadouts are slower and climb worse, even though the SFM tables stay the same.

The idea is to keep your SFM tuned for a **typical mission configuration**, and express other effects via simple drag/lift scalars.

### 8.4 Multiple AI variants

If a single SFM cannot cover the full desired envelope, consider making **multiple AI aircraft entries** with different FMs, e.g.:

- A “clean training” variant with slightly reduced thrust and G limits.
- A “combat loaded” variant with heavier mass and more drag.

These can share the same 3D model and liveries but have different internal names and performance envelopes.

### 8.5 Mission‑level tricks

In the Mission Editor you can further shape AI behavior:

- Use **“Reaction to threat”**, **ROE**, and **advanced waypoint Actions** to prevent AI from constantly going to max performance.
- Use **altitude and speed restrictions** at waypoints to keep AI in realistic cruise regimes.
- Pair your custom AI aircraft with **doctrine‑appropriate tasks** (intercept vs CAP vs CAS) to let the AI’s built‑in playbook make more sense.

---

## 9. Relationship to other AI flight models

Even though this guide is SFM‑focused, it helps to know how it fits into the broader AI FM ecosystem.

- **SFM‑based AI (this guide):**

  - Defined entirely in Lua via `SFM_Data` and basic stats.
  - Easiest path for community AI aircraft.

- **GFM‑based AI (General Flight Model):**

  - Newer unified FM used for some ED AI aircraft, with more natural short‑period behavior and unified ground/flight dynamics.
  - Currently not directly authorable for 3rd‑party Lua‑only mods; when/if that changes, many of the same tuning goals (top speed, climb, G‑limits) will still apply, but via a different interface.

For now, if you are building AI aircraft as a modder, you should assume **SFM is the tool you have**, and design your performance targets so they would still make sense if migrated to a more advanced AI FM later.

---

## 10. Quick reference tables

### 10.1 Aerodynamics tuning cheat sheet

| Goal                       | Primary knobs                     | Secondary knobs                    |
| -------------------------- | --------------------------------- | ---------------------------------- |
| Raise top speed            | ↓ `Cx0`, ↑ engine `Pmax` / `Pfor` | ↓ `dcx_eng`, adjust `dpdh_*`       |
| Lower top speed            | ↑ `Cx0`                           | ↓ engine thrust at high Mach       |
| Increase max G             | ↑ `Cya`, ↑ `Cymax`, ↑ `Ny_max`    | ↑ wing area, ↓ mass                |
| Reduce max G               | ↓ `Cya`, ↓ `Cymax`, ↓ `Ny_max_e`  | ↑ mass, ↓ wing area                |
| More energy bleed in turns | ↑ `B`, ↑ `B4`                     | Slight ↑ `Cx0` at relevant Mach    |
| Less energy bleed in turns | ↓ `B`, ↓ `B4`                     | ↑ engine thrust at relevant Mach   |
| Faster roll response       | ↑ `Omxmax`, ↓ `kjx` (carefully)   | Adjust `Czbe` if yaw/roll coupling |
| Slower / smoother roll     | ↓ `Omxmax`, ↑ `kjx`               |                                    |
| Softer stall onset         | Lower `Aldop`, tune `Cymax`       | Use higher `B4` near stall         |

### 10.2 AI behavior guardrails cheat sheet

| Symptom                                       | Likely fix                                     |
| --------------------------------------------- | ---------------------------------------------- |
| AI constantly out‑turns full‑fidelity players | Lower `Ny_max_e`, increase `B`/`B4`            |
| AI cruises at absurd speeds                   | Lower `Mach_max`, `V_max_*`, fix drag/thrust   |
| AI rotates too late / long takeoff roll       | Lower `V_take_off`, tune `AOA_take_off`, flaps |
| AI floats or overshoots landings              | Lower `V_land`, adjust `cy_flap`/`cx_flap`     |
| AI banks 80–90° for casual heading changes    | Lower `bank_angle_max`                         |
| AI is “twitchy” in roll                       | Lower `Omxmax`, raise `kjx`                    |

---

You can now drop this file into your mod’s docs and iterate. If you share details of a specific aircraft (weight, thrust, wing area, desired top speed and G limits), we can walk through a concrete set of `SFM_Data` values and AI stats tailored to that airframe.

