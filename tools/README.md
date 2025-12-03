# MiG-17 Flight-Model Test Mission Generator

This repository includes a helper script that builds a MiG-17F flight-model test mission using Python and the [pydcs](https://pydcs.readthedocs.io/) `dcs` library.

## Requirements

Use the included helper to create a virtual environment and install
dependencies on Windows, macOS, or Linux:

```bash
python tools/setup_env.py
```

This defaults to a `.venv` directory in the repo root; override it with
`--venv-path` if desired. If you prefer manual installation, run
`pip install -r requirements.txt` using your chosen interpreter.

## Usage

```bash
# Optionally activate the virtual environment first (example for POSIX shells)
source .venv/bin/activate

python tools/generate_mig17_fm_test_mission.py
python tools/generate_mig17_fm_test_mission.py --outfile "C:/Users/<you>/Saved Games/DCS.openbeta/Missions/MiG17F_FM_Test.miz"
python tools/generate_mig17_fm_test_mission.py --type-name vwv_mig17f
```

The generator defaults to saving `build/MiG17F_FM_Test.miz` and reads the MiG-17 type name from `[VWV] MiG-17/Database/mig17f.lua`. Override the detected type with `--type-name` if needed.

## Test groups

The mission includes single-ship AI groups for common performance checks:

- **ACCEL_*:** level acceleration at sea level, 10,000 ft, and 20,000 ft.
- **CLIMB_*:** constant-IAS climbs beginning at 1,000 ft and 10,000 ft up to 33,000 ft.
- **TURN_*:** sustained level turns at 10,000 ft at 300/350/400 KIAS.
- **DECEL_*:** idle/low-power deceleration from 325 KIAS at 10,000 ft.

A mission-start trigger injects a Lua logger that reports progress to `dcs.log` for each group.
