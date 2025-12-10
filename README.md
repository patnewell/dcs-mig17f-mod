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
- `tools/`: Python helpers for flight model testing and development:
  - `mig17_fm_tool.py`: **unified CLI tool** with subcommands for all FM development tasks
  - `setup_env.py`: environment bootstrap for dependencies
  - `generate_mig17_fm_test_mission.py`: FM test mission generator module
  - `generate_bfm_test_mission.py`: BFM (dogfight) test mission generator
  - `bfm_acmi_analyzer.py`: TacView ACMI analyzer for BFM metrics
  - `run_bfm_test.py`: BFM test orchestration module
  - `parse_fm_test_log.py`: log parsing module
  - `build_mig17f_variants_from_json.py`: variant building module
  - `run_fm_test.py`: test orchestration module
  - `tests/`: comprehensive unit tests for all modules
- `fm_variants/`: flight model variant configuration for A/B testing different SFM coefficients:
  - `mig17f_fm_variants.json`: variant definitions with scaling factors (checked in)
  - `mods/`: generated variant mod folders (gitignored; regenerate with build-variants command)
- `bfm_mission_tests.json`: BFM scenario definitions (opponents, geometries, altitudes, pass/fail criteria)
- `Tests/`: mission scripts and notes for manual flight-model checks.
- `test_runs/`: archived test run data (gitignored; created by run-test command)
- `codex_ref/`: reference aircraft data (MiG-15bis, MiG-19P, MiG-21bis Lua files) and a sample `.miz` used by the tooling tests.

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

## Unified CLI Tool

All flight model development tasks are available through a single CLI tool with subcommands:

```bash
python -m tools.mig17_fm_tool <command> [options]
```

### Available Commands

| Command | Description |
|---------|-------------|
| `generate-mission` | Generate FM test mission (.miz file) |
| `parse-log` | Parse DCS log for test results |
| `build-variants` | Build FM variant mods from JSON configuration |
| `run-test` | Run complete FM test workflow (build, install, test, analyze) |
| `generate-bfm-mission` | Generate BFM (dogfight) test mission |
| `analyze-bfm` | Analyze TacView ACMI file for BFM metrics |
| `run-bfm-test` | Run complete BFM test workflow |

Use `python -m tools.mig17_fm_tool <command> --help` for detailed options.

### Generating the flight-model test mission

```bash
# Generate to default location (Saved Games/DCS/Missions/)
python -m tools.mig17_fm_tool generate-mission

# Custom output path
python -m tools.mig17_fm_tool generate-mission --outfile "C:/Users/<you>/Saved Games/DCS/Missions/MiG17F_FM_Test.miz"

# Override aircraft type name
python -m tools.mig17_fm_tool generate-mission --type-name vwv_mig17f
```

The mission spawns single-ship AI groups named `ACCEL_*`, `CLIMB_*`, `TURN_*`, `VMAX_*`, and `DECEL_*` and injects a Lua logger that reports progress to `dcs.log`.

**Multi-FM variant mode:** When `fm_variants/mig17f_fm_variants.json` exists, the generator automatically builds a multi-FM mission with test groups for each variant. Group names are prefixed with the variant ID (e.g., `FM6_VMAX_10K`).

> **Windows note:** PyDCS may trigger a `KeyError` when scanning livery folders on Windows. The repository includes a stub to prevent this.

### Parsing test results

```bash
# Auto-detect DCS log location
python -m tools.mig17_fm_tool parse-log

# Specify log file and output
python -m tools.mig17_fm_tool parse-log --log-file path/to/dcs.log --output report.txt

# Export to CSV
python -m tools.mig17_fm_tool parse-log --csv results.csv
```

The parser compares measured performance against historical MiG-17F targets and reports pass/fail status for each test group. In multi-FM mode, results are grouped by variant.

### Building FM variants

```bash
# Build variants to default location (fm_variants/mods/)
python -m tools.mig17_fm_tool build-variants

# Build and install to DCS
python -m tools.mig17_fm_tool build-variants --dcs-saved-games "C:/Users/<you>/Saved Games/DCS"
```

The builder reads `fm_variants/mig17f_fm_variants.json` and generates mod folders with scaled SFM coefficients (Cx0, induced drag polar, engine drag, afterburner thrust). Each variant appears as a distinct aircraft type in DCS.

### Running a complete flight test

```bash
# Full automated test workflow
python -m tools.mig17_fm_tool run-test

# Custom timeout (default: 15 minutes)
python -m tools.mig17_fm_tool run-test --timeout 900

# Reuse existing mods
python -m tools.mig17_fm_tool run-test --skip-build

# Analyze existing log only
python -m tools.mig17_fm_tool run-test --analyze-only path/to/dcs.log
```

The run-test command performs these steps automatically:
1. Builds all FM variant mods from JSON configuration
2. Installs mods to DCS (removes duplicates first)
3. Generates the test mission with a unique run ID
4. Launches DCS if not already running
5. Polls the DCS log file for test completion (~10 minutes)
6. Archives the log to `test_runs/<timestamp>_<run_id>/`
7. Runs analysis and outputs pass/fail report

Test results are saved to `test_runs/` (gitignored) with:
- `dcs.log`: copy of the DCS log from the test run
- `fm_test_report.txt`: human-readable pass/fail report
- `fm_test_results.csv`: data for further analysis
- `run_info.txt`: metadata about the run

### Generating BFM (dogfight) test missions

```bash
# Generate BFM mission using high-AoA tuning profiles and flight model variants
python -m tools.mig17_fm_tool generate-bfm-mission \
  --bfm-config ai_scratch_area/high_aoa_tuning/flight_profiles.json \
  --variant-json ai_scratch_area/high_aoa_tuning/flight_models.json

# Generate to a custom output path
python -m tools.mig17_fm_tool generate-bfm-mission \
  --bfm-config ai_scratch_area/high_aoa_tuning/flight_profiles.json \
  --variant-json ai_scratch_area/high_aoa_tuning/flight_models.json \
  --outfile "C:/Users/<you>/Saved Games/DCS/Missions/MiG17F_HighAoA_BFM.miz"

# Include only priority-1 (core) scenarios
python -m tools.mig17_fm_tool generate-bfm-mission \
  --bfm-config ai_scratch_area/high_aoa_tuning/flight_profiles.json \
  --variant-json ai_scratch_area/high_aoa_tuning/flight_models.json \
  --max-priority 1

# Single-FM mode (no variants, just the base MiG-17F)
python -m tools.mig17_fm_tool generate-bfm-mission \
  --bfm-config ai_scratch_area/high_aoa_tuning/flight_profiles.json \
  --type-name vwv_mig17f
```

The BFM mission generator creates dogfight scenarios between MiG-17F variants and opponent aircraft (F-4E by default). When `--variant-json` is provided, the mission includes test groups for each FM variant, allowing A/B comparison of flight model tuning in TacView.

**Configuration files:**
- `flight_profiles.json`: Defines engagement geometries, altitudes, speeds, and test scenarios
- `flight_models.json`: Defines FM variants with high-AoA tuning parameters (polar drag, lift caps)

### Legacy Script Usage

The individual scripts are still available for backward compatibility:

```bash
python tools/generate_mig17_fm_test_mission.py [options]
python tools/parse_fm_test_log.py [options]
python tools/build_mig17f_variants_from_json.py [options]
python tools/run_fm_test.py [options]
```

## Mission scripts and references
- `Tests/README.md`: detailed documentation of test groups, targets, fuel loads, and log formats.
- `Tests/mig17_accel_test.lua`: legacy mission-start logger (the generator now embeds a more comprehensive script).
- `codex_ref/`: reference data including `mig-17f-fm-tests.miz` and SFM Lua files from comparable aircraft (MiG-15bis, MiG-19P, MiG-21bis).

## Running tests
After installing dependencies, run the Python test suite from the repo root:

```bash
# Install pytest if not already installed
pip install pytest

# Run all tests
python -m pytest tools/tests

# Run with verbose output
python -m pytest tools/tests -v
```

The test suite includes comprehensive unit tests for all modules:
- `test_generate_mig17_fm_test_mission.py`: mission generator tests
- `test_parse_fm_test_log.py`: log parser tests
- `test_build_mig17f_variants_from_json.py`: variant builder tests
- `test_run_fm_test.py`: test orchestration tests
- `test_mig17_fm_tool.py`: unified CLI tool tests
