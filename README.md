# VWV MiG-17F Mod

This repository packages a fork of the VWV MiG-17F community aircraft for DCS World. The fork focuses on iterating on the flight model for Vietnam-era air-to-air combat while keeping the supporting tooling and reference missions in one place.

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
