# [VWV] MiG-17F Baseline Mod – Structure & SFM Configuration Catalog

This document catalogs the baseline MiG-17F AI mod archive you provided (**`[VWV] MiG-17.zip`**), with a focus on the **SFM (Simple Flight Model)** configuration used by DCS AI.

It is intended to be used as a **source-of-truth reference** when doing FM sweeps (e.g. Stage 9), and when mapping test results back to specific Lua parameters.

## Plugin metadata (entry.lua)

**Source:** `entry.lua`

| Field | Value |
|---|---|
| `self_ID` | tetet_mig17f_fm5_g6_rc3ms |
| `displayName` | [VWV] MiG-17F RC3M Soft Clamp (toward RC3L) |
| `fileMenuName` | RC3MS MiG-17F |
| `developerName` | Hawkeye, TeTeT |
| `update_id` | mig17f_fm5_g6_rc3ms |
| `version` | 2.2.0 |

### What entry.lua does

At a high level, `entry.lua`:

- Registers the mod as a DCS plugin (`declare_plugin`).
- Mounts model, texture, and livery paths so DCS can find assets.
- Loads the aircraft definition from `Database/mig17f.lua` via `add_aircraft(dofile(...))`.

**Mounted paths:**

- Models: `Shapes/`
- Liveries: `Liveries/`
- Textures: `Textures/mig17f` (note: your archive contains `Textures/mig17f.zip`; DCS commonly loads textures directly from a .zip placed under `Textures/`).

## Mod folder structure

**Root directory:** `[VWV] MiG-17/`

### Top-level contents

| Name | Type | Files | Size |
|---|---|---|---|
| `Database` | dir | 2 | 27.4 KB |
| `ImagesGUI` | dir | 4 | 68.6 KB |
| `LICENSE.md` | file | 1 | 18.8 KB |
| `Liveries` | dir | 42 | 749.0 MB |
| `Options` | dir | 4 | 20.1 MB |
| `README.md` | file | 1 | 326 B |
| `Shapes` | dir | 12 | 46.8 MB |
| `Skins` | dir | 2 | 60.5 KB |
| `Textures` | dir | 1 | 43.8 MB |
| `comm.lua` | file | 1 | 252 B |
| `doc` | dir | 4 | 116.3 KB |
| `entry.lua` | file | 1 | 1.6 KB |
| `weapons` | dir | 1 | 5.7 KB |

### What each top-level directory is for

- `Database/`: Lua definitions for the aircraft (including the **SFM** data) and any static objects.
- `Shapes/`: 3D model assets (`.edm`, `.lods`, etc.).
- `Textures/`: texture archives. In this mod, the main package is `Textures/mig17f.zip`.
- `Liveries/`: paint schemes for the aircraft and cockpit, typically `.dds` textures and `description.lua` files.
- `ImagesGUI/`: icons / menu images used by the DCS UI for the mod.
- `Options/`: model/options UI assets. Includes an `.edm` used for the options dialog.
- `Skins/`: DCS “Skins/1” icon directory (used for mod selection in mission editor / payload pages).
- `weapons/`: custom gun/shell definitions (ballistics, ammo mixes).
- `doc/`: documentation and reference images bundled with the mod.

### Key files

| Path | Size | Purpose |
|---|---|---|
| `entry.lua` | 1.6 KB | DCS plugin registration & aircraft loading. |
| `comm.lua` | 252 B | Radio command dialog config (imports LockOnAirplane.lua config). |
| `README.md` | 326 B | Mod summary and attribution. |
| `LICENSE.md` | 18.8 KB | License terms. |
| `Database/mig17f.lua` | 24.2 KB | Main aircraft definition, AI parameters, **SFM_Data** (aerodynamics + engine). |
| `Database/statics/mig_boarding_ladder.lua` | 3.3 KB | Static ground support object (boarding ladder). |
| `weapons/guns.lua` | 5.7 KB | Gun + shell ballistics definitions. |
| `Textures/mig17f.zip` | 43.8 MB | Primary texture package (mounted via entry.lua). |
| `Options/mig17f.edm` | 20.1 MB | Options UI model asset. |

### Asset inventories (summaries)

- `Shapes/`: 12 files (EDM models + LODs + collision + vapor).
- `Textures/`: 1 files (mainly `mig17f.zip`).
- `Options/`: 4 files (includes `mig17f.edm`).
- `Liveries/`: top-level livery categories: `Cockpit_mig17f`, `vwv_mig17f`

## Aircraft definition (Database/mig17f.lua)

**Source:** `Database/mig17f.lua`

This file defines:

- Gun definitions (`n37`, `nr23`) and mounts
- The aircraft table: `local vwv_mig17f = { ... }`
- **SFM flight model data** under `SFM_Data = { aerodynamics = {...}, engine = {...} }`
- AI behavior hints (max speed, climb rate, g limits, etc.)
- Damage model, pylons, tasks, etc.

### Airframe & AI performance parameters

These values live at the aircraft table level (not inside `SFM_Data`). DCS uses them primarily as:

- **AI planning / constraints** (what the AI *tries* to do)
- General aircraft characteristics (mass, wing area, range, etc.)

They may not directly change the physics integration step-by-step the way `SFM_Data` does, but they *can* influence behavior and the ability of AI to exploit the FM.

| Parameter | Raw value in Lua | Interpreted value |
|---|---|---|
| `Name` | 'vwv_mig17f_rc3ms' |  |
| `DisplayName` | _('[VWV] MiG-17F RC3M Soft Clamp (toward RC3L)') |  |
| `Shape` | "mig17f" |  |
| `M_empty` | 3920 | 3920 |
| `M_nominal` | 5345 | 5345 |
| `M_max` | 6075 | 6075 |
| `M_fuel_max` | 1140 | 1140 |
| `H_max` | 18000 | 18000 m = 59055 ft |
| `CAS_min` | 50 | 50.00 m/s = 180 km/h = 97 kt |
| `V_opt` | 850 / 3.6 | 236.11 m/s = 850 km/h = 459 kt |
| `V_take_off` | 63 | 63.00 m/s = 227 km/h = 122 kt |
| `V_land` | 78 | 78.00 m/s = 281 km/h = 152 kt |
| `AOA_take_off` | 0.17 | 0.17 |
| `bank_angle_max` | 75 | 75 |
| `Ny_min` | -3 | -3 |
| `Ny_max` | 7.0 | 7 |
| `Ny_max_e` | 7.0 | 7 |
| `V_max_sea_level` | 1115 / 3.6 | 309.72 m/s = 1115 km/h = 602 kt |
| `V_max_h` | 1145 / 3.6 | 318.06 m/s = 1145 km/h = 618 kt |
| `Mach_max` | 0.95 | 0.95 |
| `wing_area` | 22.6 | 22.6 |
| `thrust_sum_max` | 2650 | 2650 kgf = 26.0 kN |
| `thrust_sum_ab` | 3380 | 3380 kgf = 33.1 kN |
| `Vy_max` | 60 | 60.0 m/s = 11811 ft/min |
| `flaps_maneuver` | 0.08 | 0.08 |
| `range` | 1300 | 1300 |
| `RCS` | 2 | 2 |
| `IR_emission_coeff` | 0.30 | 0.3 |
| `IR_emission_coeff_ab` | 0.45 | 0.45 |

**Notes on the most FM-relevant of these parameters:**

- `Ny_max` / `Ny_max_e`: AI g-limits. In practice, these are one of the most reliable ways to suppress UFO turns *if* the AI respects them in SFM.
- `flaps_maneuver`: AI maneuver-flap usage. High values can create “cheat flaps”; your baseline uses **0.08**, which is already conservative.
- `Vy_max`: AI climb capability hint; can influence whether AI chooses vertical tactics.
- `H_max`: AI ceiling hint; your baseline is **18,000 m (~59k ft)** which is higher than the commonly quoted MiG-17F service ceiling (~54.5k ft). Tightening this can reduce high-altitude excursions even if physics still allows them.

## SFM flight model configuration

The **Simple Flight Model** is defined under:

- `vwv_mig17f.SFM_Data.aerodynamics`
- `vwv_mig17f.SFM_Data.engine`

### Aerodynamics model

The file documents the drag polar as:

`Cx = Cx0 + Cy^2 * B2 + Cy^4 * B4`

Where the coefficients are Mach-dependent via `table_data`.

#### Aerodynamics scalar parameters

| Parameter | Value | Notes (practical effect) |
|---|---|---|
| `Cy0` | 0.0712 | Lift offset at 0 AoA (trim bias). |
| `Mzalfa` | 4.32 | Pitch moment response to AoA (agility / stability proxy). |
| `Mzalfadt` | 0.87 | Pitch damping derivative (stability / oscillation damping). |
| `kjx` | 2.08 | Inertia-like parameter in X (roll) axis used by SFM. |
| `kjz` | 0.0115 | Inertia-like parameter in Z (yaw) axis used by SFM. |
| `Czbe` | -0.014 | Z-axis coefficient (stability / coupling term). |
| `cx_gear` | 0.02 | Additional drag with gear extended. |
| `cx_flap` | 0.06 | Additional drag with flaps extended. |
| `cy_flap` | 0.35 | Additional lift with flaps. |
| `cx_brk` | 0.026 | Speedbrake drag coefficient. |

#### Aerodynamics Mach table (`SFM_Data.aerodynamics.table_data`)

Columns (as commented in the Lua):

- `M`: Mach
- `Cx0`: profile/parasite drag coefficient
- `Cya`: normal force coefficient per AoA (lift slope proxy)
- `B2`, `B4`: induced/high-AoA drag polar terms
- `Omxmax`: roll rate limit (rad/s)
- `Aldop`: departure AoA threshold
- `Cymax`: maximum lift coefficient clamp

| M | Cx0 | Cya | B2 | B4 | Omxmax | Aldop | Cymax |
|---|---|---|---|---|---|---|---|
| 0.00 | 0.0097 | 0.0715 | 0.043 | 0.006 | 0.460 | 8.8 | 0.52 |
| 0.10 | 0.0097 | 0.0715 | 0.043 | 0.006 | 0.460 | 8.8 | 0.52 |
| 0.20 | 0.0095 | 0.0710 | 0.043 | 0.092 | 0.860 | 8.7 | 0.51 |
| 0.30 | 0.0091 | 0.0718 | 0.044 | 0.106 | 1.200 | 8.6 | 0.51 |
| 0.40 | 0.0089 | 0.0735 | 0.045 | 0.145 | 1.580 | 8.3 | 0.50 |
| 0.50 | 0.0089 | 0.0765 | 0.047 | 0.172 | 1.780 | 8.2 | 0.50 |
| 0.60 | 0.0091 | 0.0810 | 0.049 | 0.224 | 1.620 | 7.8 | 0.47 |
| 0.70 | 0.0094 | 0.0855 | 0.052 | 0.370 | 1.050 | 7.4 | 0.46 |
| 0.80 | 0.0104 | 0.0895 | 0.056 | 0.620 | 0.520 | 6.8 | 0.43 |
| 0.86 | 0.0115 | 0.0860 | 0.064 | 0.078 | 0.380 | 6.4 | 0.41 |
| 0.90 | 0.0153 | 0.0805 | 0.074 | 0.141 | 0.320 | 5.8 | 0.38 |
| 0.94 | 0.0237 | 0.0775 | 0.091 | 0.216 | 0.280 | 5.3 | 0.36 |
| 1.00 | 0.0348 | 0.0765 | 0.114 | 0.300 | 0.230 | 4.5 | 0.34 |
| 1.04 | 0.0366 | 0.0770 | 0.135 | 0.402 | 0.210 | 4.2 | 0.32 |
| 1.20 | 0.0375 | 0.0785 | 0.153 | 0.534 | 0.190 | 3.8 | 0.30 |

**Two specific “gotchas” to be aware of for tuning:**

- **High-AoA drag window discontinuity:** `B4` is very large up to **M 0.8** but drops sharply at **M 0.86** (0.620 → 0.078). If the AI is fighting at higher Mach/CAS, it may “escape” the intended high-AoA drag clamp.
- **Departure AoA is expressed as `Aldop` and trends downward with Mach:** if you sweep `Aldop` as a single global multiplier, you may overly restrict low-Mach behavior while still leaving high-Mach behavior too permissive (or vice-versa). A piecewise / Mach-window approach can be useful.

### Engine model

#### Engine scalar parameters

| Parameter | Value | Notes (practical effect) |
|---|---|---|
| `type` | TurboJet | Engine type (TurboJet). |
| `Nominal_RPM` | 11600.0 | Nominal RPM used by engine model. |
| `Nmg` | 21.5 | Idle RPM (approx). |
| `Startup_Prework` | 28.0 | Seconds of pre-start. |
| `Startup_Duration` | 21.0 | Seconds to reach idle. |
| `Shutdown_Duration` | 62.0 | Seconds to spool down. |
| `MinRUD` | 0 |  |
| `MaxRUD` | 1 |  |
| `MaksRUD` | 1 |  |
| `ForsRUD` | 1 |  |
| `hMaxEng` | 19 | Max altitude for safe engine operation (km). |
| `dcx_eng` | 0.0080 | Engine drag coefficient. |
| `cemax` | 1.24 | AI-only fuel/time routine coefficient (not physics fuel burn). |
| `cefor` | 2.56 | AI-only fuel/time routine coefficient (not physics fuel burn). |
| `dpdh_m` | 1340 | Altitude coefficient controlling thrust lapse with altitude for mil power. |
| `dpdh_f` | 1340 | Altitude coefficient controlling thrust lapse with altitude for afterburner. |

#### Engine Mach table (`SFM_Data.engine.table_data`)

Columns:

- `M`: Mach
- `Pmax`: thrust at military power
- `Pfor`: thrust with afterburner

*Units:* In most ED SFM configs, thrust is in **Newtons**. These values align with ~26.5 kN mil and ~33.8 kN AB at M 0.0.

| M | Pmax (N) | Pmax (kN) | Pfor (N) | Pfor (kN) |
|---|---|---|---|---|
| 0.00 | 26500 | 26.5 | 33800 | 33.8 |
| 0.10 | 26500 | 26.5 | 33800 | 33.8 |
| 0.20 | 25000 | 25.0 | 32700 | 32.7 |
| 0.30 | 23800 | 23.8 | 31800 | 31.8 |
| 0.40 | 23000 | 23.0 | 31000 | 31.0 |
| 0.50 | 22500 | 22.5 | 30500 | 30.5 |
| 0.60 | 22300 | 22.3 | 30300 | 30.3 |
| 0.70 | 22400 | 22.4 | 30400 | 30.4 |
| 0.80 | 23000 | 23.0 | 31000 | 31.0 |
| 0.86 | 23500 | 23.5 | 31500 | 31.5 |
| 0.90 | 24000 | 24.0 | 32000 | 32.0 |
| 0.94 | 24300 | 24.3 | 32200 | 32.2 |
| 1.00 | 24800 | 24.8 | 32500 | 32.5 |
| 1.04 | 25100 | 25.1 | 32700 | 32.7 |
| 1.10 | 26200 | 26.2 | 33500 | 33.5 |

**Notable characteristics of this thrust table (relevant to vertical energy):**

- Thrust decreases from M 0.0 to about M 0.6, then rises again toward transonic. This shape affects how hard the AI accelerates in the 300–500 kt regime and during zoom climbs.
- `dpdh_m` and `dpdh_f` are equal (1340). If the aircraft is showing unrealistic high-altitude vertical performance, you can often fix it by **reducing AB thrust (`Pfor`) and/or decreasing the dpdh values** so thrust decays faster with altitude.

## Stage 9 tuning recommendations: what else to sweep

Stage 9 is focused on **vertical energy / zoom climb UFO behavior** (MiG retaining too much energy and climbing unrealistically high / fast).

Your current `flight_models.json` schema (as of Stage 9) already covers many of the highest-leverage knobs:

- Aerodynamics: `Cx0`, `B2`, `B4`, `Cymax`, `Aldop`
- Engine: `dcx_eng`, `Pmax`, `Pfor`, `dpdh_m`, `dpdh_f`
- AI constraints: `Ny_max`, `Ny_max_e`, `flaps_maneuver`

If the vertical UFO behavior persists even after sweeping those, the next most likely contributors are below.

### Recommended new JSON/schema fields (requires code updates)

1) **Lift slope scaling (`Cya`)**

- **Lua path:** `SFM_Data.aerodynamics.table_data[*][Cya]` (the 3rd numeric column: `M, Cx0, Cya, ...`).
- **Why it matters:** If the lift curve slope is too high in the regime the AI is exploiting, it can generate large normal force (g) at lower AoA, which can support unrealistic vertical pulls and zoom climbs.
- **Suggested JSON additions:**
  - `cya_scale` (global multiplier)
  - optionally `cya_mach_windows`: list of `{mach_min, mach_max, scale}` so you can tune subsonic vs transonic separately.

2) **Mach-window control for high-AoA drag scaling (`B4` window)**

- **Lua path:** `SFM_Data.aerodynamics.table_data[*][B4]` (5th numeric column).
- **Why it matters:** Your current “high-AoA clamp” behavior is concentrated up to M 0.8, but `B4` collapses at M 0.86. If the AI is maneuvering at 400–500 KCAS at altitude, you may need the high-AoA drag clamp to extend into ~M 0.9+.
- **Suggested JSON additions:**
  - `polar_high_aoa_mach_min` / `polar_high_aoa_mach_max` (so the clamp window is tunable)
  - or `polar_high_aoa_windows`: list of windows like above.

3) **Pitch agility/damping scaling (`Mzalfa`, `Mzalfadt`)**

- **Lua path:** `SFM_Data.aerodynamics.Mzalfa`, `SFM_Data.aerodynamics.Mzalfadt`.
- **Why it matters:** Even if sustained performance is constrained, overly aggressive pitch response can create “instant UFO” behavior (snap vertical, unreal instantaneous turn spikes).
- **Suggested JSON additions:** `mzalfa_scale`, `mzalfadt_scale` (or absolute overrides).

4) **Engine ceiling / guardrail (`hMaxEng`)**

- **Lua path:** `SFM_Data.engine.hMaxEng` (km).
- **Why it matters:** This is a blunt instrument, but it can prevent the AI from using unreal engine performance above the intended altitude band.
- **Suggested JSON additions:** `hmaxeng_km_override` (absolute) or `hmaxeng_scale`.

5) **AI “intent” hints (`Vy_max`, `H_max`, `V_opt`)**

- **Lua path:** top-level aircraft params.
- **Why it matters:** These can change whether the AI *chooses* to go vertical even if the physics is unchanged, which matters for synthetic AI-vs-AI reproduction of vertical UFO tactics.
- **Suggested JSON additions:** `vy_max_scale`, `h_max_m_override`, `v_opt_scale`.

### If you want to keep Stage 9 “physics-only”

If you prefer to avoid AI-hint tweaks and focus purely on the physics side, the best next addition is **`Cya` scaling** plus a tunable **Mach window for the high-AoA `B4` clamp**. Those two typically give you the most leverage without resorting to artificial ceilings.