# MiG‑17F Flight Envelope & Energy‑Maneuverability (EM) Baseline

**Purpose.** This document defines a *defensible* MiG‑17F (Fresco C) flight‑envelope target and a practical EM baseline for tuning/validating a DCS **SFM** (Simple Flight Model) MiG‑17F adversary.

It is written for mod developers and test pilots who want a Vietnam‑era opponent (e.g., Heatblur F‑4E vs MiG‑17F BFM) that supports **historical tactics** and avoids common SFM “UFO” failure modes:

* unrealistically high sustained turn rates at very low speed (missing induced‑drag/stall effects)
* excessive vertical energy retention (climbs like a rocket, little bleed)
* high‑Mach/high‑q maneuvering that contradicts declassified handling notes

**What’s new in this revision.** This rev replaces several earlier “working estimates” with **primary, CIA‑released Soviet flight‑manual performance table data** (MiG‑17 family). It also expands and corrects the **DCS SFM field mapping** using `dcs_sfm_modding_guide.md`.

**Scope limits.** We still do *not* have a full, digitized Ps/EM chart set for MiG‑17F (e.g., Ps=0 contours by altitude). Until that is found, this doc provides:

1) **Primary performance anchors** (speed/ceiling/climb times) you can treat as hard targets.
2) **Guardrail EM targets** (turn‑rate/radius) that intentionally err conservative to suppress UFO behavior.
3) A **machine‑readable JSON baseline** (spec + data) you can feed into your own tooling.

---

## 1) Declassified US evaluation anchors (what we can defend)

These come from the declassified *Have Drill / Have Ferry* tactical evaluation briefing ([HD], local file `area51_51.pdf`).

### 1.1 Structural / maneuvering limit (8 g)

The briefing notes that most engagements were at low altitude, where Fresco C’s **low wing loading** and **8 g structural limit** are best optimized. **Implication:** your AI FM should have a meaningful **hard cap / warning** around **8 g**.

### 1.2 High‑speed handling degradation

The briefing reports that **above ~0.85 Mach or 450 KIAS** the MiG‑17 experiences very high control forces and significantly reduced roll/pitch agility. **Implication:** your SFM MiG‑17 should not be a “high‑q monster.” If it routinely fights effectively at 500+ KCAS with large instantaneous pulls, that’s a red flag.

### 1.3 Turn‑rate sanity bound at altitude

The briefing includes an EM‑style turn‑rate vs Mach plot at **20,000 ft**, providing a sanity bound for turn performance at altitude (even though it is not a complete EM chart set).

---

## 2) Primary Soviet flight‑manual performance anchors (CIA release)

**Source.** `CIA-RDP81-01043R004000110001-0.pdf` contains scanned pages from a Soviet flight/technical manual for the MiG‑17 family (including VK‑1F afterburning engine performance). The most directly useful material for flight modeling is:

* **Table 1 – “Flight data of the aircraft”** (maximum speed, ceiling, climb times, range/endurance).
* **Table 2 – strength/limit assumptions** (design Mach and related limits used in strength calculations).

> **Variant caution.** The scanned table is presented for a MiG‑17P / MiG‑17PF context (interceptor variants) but the **engine mode** values (VK‑1F with/without afterburner) are still highly relevant as *hard anchors* for a MiG‑17F‑class airframe. MiG‑17F (Fresco C) will typically be similar or slightly better (lighter/no radar), so treat these as **conservative** unless you later obtain a MiG‑17F‑specific EM appendix.

### 2.1 Table 1: performance table (VK‑1F with/without afterburner)

From Table 1 (PDF page showing “Table 1. Flight data of the aircraft”):

| Metric | VK‑1F (afterburner) | VK‑1F (no afterburner) | Notes |
|---|---:|---:|---|
| **Max speed at altitude** | **1121 km/h @ 4000 m** | **1074 km/h @ 2000 m** | Primary Vmax anchors. |
| **Practical ceiling** | **15,850 m** | **14,350 m** | Service ceiling anchors. |
| **Time to 5,000 m** | **2.5 min** | **4.5 min** | Climb time anchors. |
| **Time to 10,000 m** | **4.5 min** | **7.6 min** | |
| **Time to 14,000 m** | **7.8 min** | **18.5 min** | |
| **Range @ 12,000 m (clean)** | **1120 km** | **1160 km** | See also w/ drop tanks. |
| **Range @ 12,000 m (2×400 L)** | **1870 km** | **1930 km** | |
| **Endurance @ 12,000 m (clean)** | **1h 40m** | **1h 45m** | |
| **Endurance @ 12,000 m (2×400 L)** | **2h 44m** | **2h 51m** | |

Table 1 also lists runway distances (useful for AI takeoff/landing behavior tuning): **takeoff run ~600–630 m** and **landing roll ~630–860 m** (values shown in the same table section).

**How to use these in DCS testing.** These values are *more robust than a single “rate of climb” number* because they can be validated directly in telemetry:

* Replace (or supplement) “ROC at SL” with **time‑to‑altitude tests** (5 km / 10 km / 14 km) at a defined entry condition.
* Treat the ceiling as a **hard bound**: if the AI routinely reaches 40k+ ft quickly and stays there with little penalty, the model is too energetic vertically.

### 2.2 Table 2: strength/limit assumptions (use as guardrails)

Table 2 provides “initial data for strength calculations” and includes a **design Mach** (OCR suggests ~**M 1.03** and notes later strength calculations used a higher Mach, OCR suggests ~**M 1.15** above ~7000 m). Treat this as *structural/design context*, not a claim of operational maneuvering capability.

**Practical takeaway:** it is reasonable for the SFM to *allow* momentary high‑Mach excursions structurally, while still enforcing **handling degradation** above ~0.85 Mach and preventing aggressive high‑q maneuvering per [HD].

### 2.3 Optional secondary constraints (if you have additional declassified reports)

If your repository also includes other CIA/FOIA MiG‑17 operational reports (e.g., foreign service experience writeups), those can add two useful *operational* guardrails that Table 1 does not cover:

* **Afterburner time limit** (reported as only a few minutes in some field reports) → helps justify intentionally aggressive high‑alt thrust decay / vertical UFO suppression.
* **Do‑not‑exceed Mach** (reported throttle stops / control issues near the transonic region) → helps justify a “don’t fight at 0.9+ Mach” penalty even if the structure could survive it.

When you cite these, keep them clearly labeled as **secondary** unless they appear in a primary flight manual.

---

## 3) Consolidated “target envelope” for DCS tuning

This section turns the anchors above into concrete, testable targets for your mission + ACMI analysis suite.

### 3.1 Speed / altitude targets

**Primary anchors (Table 1):**

* Vmax ≈ **1121 km/h @ 4000 m** (AB)
* Vmax ≈ **1074 km/h @ 2000 m** (MIL/no AB)
* Practical ceiling ≈ **15.9 km** (AB) / **14.35 km** (MIL)

**Operational / tactics guardrails (Have Drill):**

* Treat **0.85 Mach / 450 KIAS** as a *handling degradation onset* region (roll/pitch authority should be noticeably worse).

### 3.2 Climb / vertical performance targets

**Primary anchors (Table 1 climb times):**

* **0 → 5,000 m:** ~**2.5 min** (AB)
* **0 → 10,000 m:** ~**4.5 min** (AB)
* **0 → 14,000 m:** ~**7.8 min** (AB)

**Recommended acceptance checks (vertical UFO suppression):**

* AI should **not** reach **40,000 ft** (~12,200 m) extremely quickly from a low‑altitude merge unless the scenario explicitly starts fast/high.
* In BFM, vertical climbs should show a **meaningful trade**: if the MiG can repeatedly go vertical without bleeding, it’s likely exploiting missing induced‑drag/stall modeling.

> Practical note: a “time to 40k” test is a *proxy* for energy bleed and thrust scaling (especially above ~20k ft).

### 3.3 G / turn performance targets (guardrails)

Until a full EM chart set is located (see next‑steps), use conservative “guardrails” that prioritize **non‑UFO behavior** over maximum historical fidelity.

| Metric (typical BFM weight) | Guardrail target | Basis |
|---|---:|---|
| **Max G (hard cap)** | **8 g** | Structural emphasis in [HD]. |
| **Best sustained TR (low altitude)** | **~12–17 deg/s** | Conservative band consistent with [HD] altitude plot and “low speed arena” remarks. |
| **Max instantaneous TR (short burst)** | **~18–25 deg/s** | Conservative bound to prevent 35–60 deg/s spikes seen in UFO behavior. |
| **Minimum turn radius** | **≥ ~2,200 ft** | Practical guardrail used in your envelope checks; revise when EM charts found. |

---

## 4) Mapping the envelope to DCS SFM configuration

Use `dcs_sfm_modding_guide.md` as the primary reference for how SFM inputs map to AI behavior. In particular:

* AI behavior depends on **both** the **basic aircraft stats** block and `SFM_Data` (the physics model). (See [SFM-GUIDE], “Where the AI flight model is defined”.)
* The `SFM_Data.aerodynamics.table_data` Mach table has the canonical columns: **M, Cx0, Cya, B, B4, Omxmax, Aldop, Cymax**. (See [SFM-GUIDE], “Mach table (`table_data`)”.)
* The guide’s “aerodynamics tuning cheat sheet” provides practical knob‑to‑symptom mapping (top speed, energy bleed, G limits).

### 4.1 Where to tune each real‑world behavior

| Behavior you’re trying to match | DCS SFM knobs (typical) | Notes |
|---|---|---|
| **Vmax / cruise energy** | `Cx0` in `table_data`; engine thrust tables (`Pmax`/`Pfor`) | Vmax is a drag/thrust balance; also ensure `V_max_*` in basic stats is sane so AI doesn’t “plan” to go faster than physics. (See [SFM-GUIDE] cheat sheet + basic stats discussion.) |
| **Climb / vertical energy** | engine thrust decay with altitude (your `dpdh_*` scaling); `Cx0`/`B`/`B4` | Excess vertical power usually means thrust stays too strong at altitude *and/or* induced drag too low at high lift. |
| **Low‑speed UFO turns** | increase `B`/`B4` (energy bleed) and/or reduce `Cymax`/`Aldop` | `B/B4` are the “more energy bleed in turns” knobs in the guide. |
| **G limit enforcement** | `Ny_max` / `Ny_max_e` (basic stats) | AI respects these as limits; use them as the first line of defense for 8 g cap. |
| **High‑Mach handling degradation** | Mach‑dependent `Cymax` reduction; `Cx0` increase near transonic | Enforce “don’t pull hard at 0.9+ Mach” behavior consistent with [HD]. |

### 4.2 Remember: basic “AI stats” matter

Even with a physically plausible `SFM_Data`, if the basic stats block advertises unrealistic numbers (e.g., too‑high `Mach_max`, `V_max_h`, or `Vy_max`), the AI may *attempt* or *seek* unrealistic regimes. The modding guide calls out these fields explicitly (see [SFM-GUIDE], “Basic aircraft stats” example).

---

## 5) Gaps & recommended next steps (still the highest leverage)

### 5.1 Locate and digitize the MiG‑17 EM chart set

Have Drill explicitly points to an EM chart set as “accurately defining” MiG‑17 performance qualities. When you find a primary EM set (Ps contours, corner speeds by altitude), replace the guardrail TR/radius numbers with **curve‑based constraints**.

### 5.2 Make vertical performance a first‑class acceptance gate

Your new ACMI “vertical UFO” metrics (time‑to‑30k/40k, max climb FPM above 20k, early‑window max alt) should be treated as **acceptance gates**, not just diagnostics.

---

## 6) References

This document uses a short citation key in brackets, like `[CIA-MAN Table 1]`.

### [CIA-MAN] CIA release: MiG‑17 family flight/technical manual scans

* Local file: `CIA-RDP81-01043R004000110001-0.pdf`
* Used for:
  * Table 1 performance anchors (Vmax, ceiling, climb times, range/endurance)
  * Table 2 strength/limit assumptions (design Mach context)

### [HD] Have Drill / Have Ferry tactical evaluation briefing

* Local file: `area51_51.pdf`
* Used for:
  * 8 g structural limit emphasis
  * High‑speed handling degradation above ~0.85 Mach / 450 KIAS
  * Turn‑rate sanity bound at 20,000 ft

### [SFM-GUIDE] DCS SFM modding guide

* Local file: `dcs_sfm_modding_guide.md`
* Used for:
  * Field‑level mapping: basic aircraft stats + `SFM_Data`
  * Mach table column definitions
  * Practical tuning knob cheat sheets

---

## 7) Machine‑readable baseline JSON (spec + data)

The JSON below is designed to be copy/paste‑able into other tooling.

### 7.1 JSON field spec (what each field means)

* `sources[]`: list of source documents and how to cite them.
* `aircraft`: the target aircraft identity for tooling.
* `anchors`: hard numeric anchors (speed, ceiling, climb times) with units and source pointers.
* `guardrails`: conservative envelope limits used to suppress UFO behavior when EM charts are missing.
* `acceptance_checks`: recommended telemetry‑derived checks your scripts can compute.
* `sfm_mapping`: a machine‑readable mapping between envelope targets and DCS SFM fields/areas.

### 7.2 JSON payload

```json
{
  "schema_version": 1,
  "document": {
    "name": "MiG-17F Flight Envelope & EM Baseline",
    "revision": "2025-12-14",
    "notes": "Primary performance anchors from CIA-released MiG-17 family flight-manual scans; EM curves still pending."
  },
  "field_spec": {
    "sources": "List of reference documents. Use 'id' in other fields (e.g., anchors.*.source) to attribute values.",
    "aircraft": "Target aircraft identity and scope notes.",
    "anchors": "Hard numeric performance anchors. Prefer these for calibration-style acceptance tests.",
    "guardrails": "Conservative bounds used to suppress UFO behavior where true EM curves are missing.",
    "acceptance_checks": "Telemetry-derived gates your ACMI/log analysis should compute (e.g., vertical UFO rules).",
    "sfm_mapping": "Mapping from envelope behaviors to DCS SFM configuration areas/fields."
  },
  "sources": [
    {
      "id": "CIA-MAN",
      "file": "CIA-RDP81-01043R004000110001-0.pdf",
      "type": "CIA release / scanned Soviet manual",
      "citations": {
        "table1": "Table 1 (Flight data of the aircraft)",
        "table2": "Table 2 (Strength/limit assumptions)"
      }
    },
    {
      "id": "HD",
      "file": "area51_51.pdf",
      "type": "USAF tactical evaluation briefing",
      "citations": {
        "g_limit": "8 g structural limit emphasis",
        "high_speed": "handling degradation above ~0.85 Mach / 450 KIAS",
        "turnrate_plot": "20k-ft turn-rate vs Mach plot"
      }
    },
    {
      "id": "SFM-GUIDE",
      "file": "dcs_sfm_modding_guide.md",
      "type": "modding guide",
      "citations": {
        "sfm_data": "SFM_Data structure + table_data column definitions",
        "cheatsheet": "aero/AI tuning cheat sheets"
      }
    }
  ],
  "aircraft": {
    "name": "MiG-17F (Fresco C)",
    "dcs_role": "AI adversary",
    "variant_notes": "Primary anchors are from MiG-17 family manual (interceptor context) and should be treated as conservative for MiG-17F."
  },
  "anchors": {
    "vmax": [
      {
        "engine_mode": "VK-1F_AB",
        "alt_m": 4000,
        "v_kmh": 1121,
        "source": "CIA-MAN.table1"
      },
      {
        "engine_mode": "VK-1F_MIL",
        "alt_m": 2000,
        "v_kmh": 1074,
        "source": "CIA-MAN.table1"
      }
    ],
    "ceiling_practical": [
      {
        "engine_mode": "VK-1F_AB",
        "ceiling_m": 15850,
        "source": "CIA-MAN.table1"
      },
      {
        "engine_mode": "VK-1F_MIL",
        "ceiling_m": 14350,
        "source": "CIA-MAN.table1"
      }
    ],
    "climb_time": [
      {
        "engine_mode": "VK-1F_AB",
        "to_alt_m": 5000,
        "time_s": 150,
        "source": "CIA-MAN.table1"
      },
      {
        "engine_mode": "VK-1F_AB",
        "to_alt_m": 10000,
        "time_s": 270,
        "source": "CIA-MAN.table1"
      },
      {
        "engine_mode": "VK-1F_AB",
        "to_alt_m": 14000,
        "time_s": 468,
        "source": "CIA-MAN.table1"
      }
    ]
  },
  "guardrails": {
    "g_limit": {
      "ny_max": 8.0,
      "source": "HD.g_limit",
      "note": "Use Ny_max/Ny_max_e to enforce AI g-limit in SFM."
    },
    "high_speed_handling": {
      "degrade_mach": 0.85,
      "degrade_kias": 450,
      "source": "HD.high_speed"
    },
    "turn": {
      "sustained_tr_deg_s": { "min": 12.0, "max": 17.0 },
      "instant_tr_deg_s": { "min": 18.0, "max": 25.0 },
      "min_radius_ft": 2200,
      "note": "Conservative UFO-suppression bounds until EM charts are digitized."
    }
  },
  "acceptance_checks": {
    "vertical_ufo": {
      "max_climb_fpm_5s_above_20k_ft": 18000,
      "reaches_40k_within_s": 300,
      "note": "Tune thresholds using a sane control aircraft run (e.g., F-86)."
    }
  },
  "sfm_mapping": {
    "basic_ai_stats": [
      { "field": "H_max", "affects": ["ceiling"], "units": "m" },
      { "field": "Mach_max", "affects": ["AI planning / speed regimes"], "units": "Mach" },
      { "field": "V_max_sea_level", "affects": ["AI planning"], "units": "m/s" },
      { "field": "V_max_h", "affects": ["AI planning"], "units": "m/s" },
      { "field": "Vy_max", "affects": ["AI climb planning"], "units": "m/s" },
      { "field": "Ny_max", "affects": ["structural g cap"], "units": "g" },
      { "field": "Ny_max_e", "affects": ["effective AI g cap"], "units": "g" }
    ],
    "sfm_data": {
      "aerodynamics.table_data": {
        "columns": ["M", "Cx0", "Cya", "B", "B4", "Omxmax", "Aldop", "Cymax"],
        "note": "Drag/lift/polar vs Mach; primary place to shape energy bleed and max lift."
      },
      "engine": {
        "note": "Thrust vs Mach and altitude. Tune high-alt thrust decay to fix vertical UFO behavior.",
        "related_scalars": ["dpdh_m_scale", "dpdh_f_scale"],
        "related_tables": ["engine.table_data (Pmax/Pfor vs Mach)"]
      }
    }
  }
}
```
