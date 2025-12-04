# VWV MiG-17F Mod

This repository packages a fork of the VWV MiG-17F community aircraft for DCS World. The fork focuses on iterating on the flight model for Vietnam-era air-to-air combat while keeping the supporting tooling and reference missions in one place.

## Flight Model Target Specifications

The MiG-17F "Fresco C" was the definitive day-fighter variant, powered by the Klimov VK-1F afterburning turbojet. This mod aims to replicate the performance characteristics of the Vietnam War-era aircraft that proved surprisingly effective against faster American fighters like the F-4 Phantom and F-105 Thunderchief.

### Historical Performance Targets

| Parameter | Target Value | Notes |
|-----------|--------------|-------|
| **Max speed (sea level)** | 1,100 km/h (593 kt) | Mach 0.89 [1][2] |
| **Max speed (3,000 m / 10,000 ft)** | 1,145 km/h (618 kt) | Mach 0.93 with afterburner [1][2] |
| **Service ceiling** | 16,600 m (54,500 ft) | [1][2] |
| **Rate of climb** | 65 m/s (12,800 ft/min) | At sea level with afterburner [1][2] |
| **Thrust/weight ratio** | 0.63 | At normal loaded weight [1] |
| **G limits** | +8 / -3 | [1] |
| **Range** | 2,020 km (1,090 nm) | With 2× 400L drop tanks [1][2] |

### Current Flight Model Values

Defined in `[VWV] MiG-17/Database/mig17f.lua`:

**Weights**
- Empty: 3,920 kg (8,642 lb) — includes pilot [1][2]
- Normal loaded: 5,345 kg (11,784 lb) — empty + full internal fuel
- Max takeoff: 6,075 kg (13,393 lb) [1][2]
- Internal fuel: 1,140 kg (2,513 lb)

**Engine (Klimov VK-1F)**
- Military thrust: 26.5 kN (5,960 lbf) [1][2]
- Afterburner thrust: 33.8 kN (7,600 lbf) [1][2]
- Max operating altitude: 19,000 m

**Dimensions**
- Wing span: 9.628 m (31 ft 7 in) [1][2]
- Wing area: 22.6 m² [1][2]
- Length: 11.09 m (36 ft 5 in)
- Height: 3.80 m (12 ft 6 in) [1][2]

**Aerodynamics**
- Wing sweep: 45° inboard / 42° outboard [1]
- Max AoA (low speed): 18.4°
- Max AoA (transonic): 8–12°
- Peak roll rate: ~1.8 rad/s at Mach 0.5

### Armament

| Weapon | Caliber | Rounds | Rate of Fire |
|--------|---------|--------|--------------|
| Nudelman N-37 | 37 mm | 40 | 400 rpm |
| Nudelman-Rikhter NR-23 (×2) | 23 mm | 80 each | 700 rpm |

The MiG-17's guns could deliver approximately 23 kg (50 lb) of projectiles in a 2-second burst at 1,500 m range—comparable to American 20 mm cannon armament [3].

### Design Philosophy

The flight model is tuned to capture the MiG-17F's key combat characteristics:

1. **Transonic agility** — Excellent roll rate and pitch authority at Mach 0.5–0.8
2. **Energy retention** — Good sustained turn performance in the subsonic regime
3. **Climb performance** — Afterburner roughly doubles rate of climb [1]
4. **Speed limitations** — Aircraft tends to pitch up approaching Mach 1; controllable to ~Mach 0.95 [1]

The MiG-17 excelled in close-range dogfights where its superior maneuverability offset its lower top speed compared to American fighters optimized for missile combat [3].

### References

1. Belyakov, R.A. and Marmain, Jacques. *MiG: Fifty Years of Secret Aircraft Design*. Naval Institute Press, 1994. ISBN 978-1557505668.
2. Wilson, Stewart. *Combat Aircraft Since 1945*. Aerospace Publications, 2000. ISBN 978-1875671502.
3. Toperczer, István. *MiG-17 and MiG-19 Units of the Vietnam War*. Osprey Publishing (Combat Aircraft 25), 2001. ISBN 978-1841761626.

## Repository layout
- `[VWV] MiG-17/`: aircraft definition, models, textures, and configuration Lua for the mod itself.
- `tools/`: Python helpers, including environment bootstrap (`setup_env.py`) and the flight-model test mission generator (`generate_mig17_fm_test_mission.py`).
- `Tests/`: mission scripts and notes for manual flight-model checks.
- `codex_ref/`: reference aircraft data and a sample `.miz` used by the tooling tests.

## Installing the aircraft
1. Copy the `[VWV] MiG-17` directory into your DCS Saved Games Mods folder (e.g., `Saved Games/DCS.openbeta/Mods/aircraft/`).
2. Launch DCS and verify the MiG-17F appears in the unit list; the type name is read from `[VWV] MiG-17/Database/mig17f.lua`.

## Python tooling
The mission tooling requires Python 3 and the [pydcs](https://pydcs.readthedocs.io/) `dcs` package.

```bash
python tools/setup_env.py
```

The helper creates a `.venv` in the repo root by default (override with `--venv-path`). You can also install dependencies manually with:

```bash
pip install -r requirements.txt
```

## Generating the flight-model test mission
Use the generator to build a reusable mission that exercises acceleration, climb, turn, and deceleration profiles for the mod aircraft.

```bash
# Optionally activate the virtual environment first
source .venv/bin/activate

python tools/generate_mig17_fm_test_mission.py
python tools/generate_mig17_fm_test_mission.py --outfile "C:/Users/<you>/Saved Games/DCS.openbeta/Missions/MiG17F_FM_Test.miz"
python tools/generate_mig17_fm_test_mission.py --type-name vwv_mig17f
```

> **Windows note:** In the CI/Codex Linux environment the generator runs without a
> local DCS installation, so PyDCS never finds any livery folders to scan and
> imports cleanly. On Windows, PyDCS will attempt to scan the default DCS
> install and Saved Games paths during import, which can trigger a `KeyError`
> if the expected `country_list` variable is missing in certain livery scripts.
> The repository includes a stub to short-circuit that scan when running the
> generator so it behaves consistently across platforms.

Defaults:
- Output: `build/MiG17F_FM_Test.miz` (directories are created automatically).
- Mod root: `[VWV] MiG-17/` relative to the repo; override with `--mod-root` if the mod lives elsewhere.
- Aircraft type: read from `Database/mig17f.lua`; override with `--type-name` when needed.

The mission spawns single-ship AI groups named `ACCEL_*`, `CLIMB_*`, `TURN_*`, and `DECEL_*` and injects a Lua logger that reports progress to `dcs.log`.

## Mission scripts and references
- `Tests/mig17_accel_test.lua` provides a mission-start logger for level-acceleration checks and is described in `Tests/README.md` for recreating the `.miz` used during development.
- `codex_ref/mig-17f-fm-tests.miz` is a reference mission archive used by the generator tests.

## Running tests
After installing dependencies, run the Python test suite from the repo root:

```bash
python -m pytest tools/tests
```
