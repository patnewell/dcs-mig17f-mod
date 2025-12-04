# MiG-17F Flight Model Test Suite

This test suite validates the MiG-17F flight model against historical performance data.

## Quick Start

1. **Generate the test mission:**
   ```bash
   python tools/generate_mig17_fm_test_mission.py
   ```
   This creates `MiG17F_FM_Test.miz` in your DCS Missions folder.

2. **Run the mission in DCS:**
   - Load the mission in DCS Mission Editor or fly it directly
   - Let it run for ~10 minutes to collect full data
   - The Lua script logs data to `dcs.log`

3. **Analyze the results:**
   ```bash
   python tools/parse_fm_test_log.py
   ```
   This parses the log and generates a pass/fail report.

## Test Groups

| Group | Description | Target |
|-------|-------------|--------|
| ACCEL_SL | Level acceleration at 1,000 ft | Time to speed gates |
| ACCEL_10K | Level acceleration at 10,000 ft | Time to speed gates |
| ACCEL_20K | Level acceleration at 20,000 ft | Time to speed gates |
| CLIMB_SL | Climb from 1,000 ft to 40,000 ft | 12,800 fpm (65 m/s) |
| CLIMB_10K | Climb from 10,000 ft to 40,000 ft | Altitude gate times |
| TURN_10K_300 | Sustained turn at 300 kt | Turn performance |
| TURN_10K_350 | Sustained turn at 350 kt | Turn performance |
| TURN_10K_400 | Sustained turn at 400 kt | Turn performance |
| VMAX_SL | Maximum speed at sea level | 593 kt (1100 km/h) |
| VMAX_10K | Maximum speed at 10,000 ft | 618 kt (1145 km/h) |
| DECEL_10K | Deceleration at 10,000 ft | Drag characteristics |

## Historical Targets

Based on MiG-17F "Fresco C" with Klimov VK-1F afterburning engine:

| Parameter | Target | Source |
|-----------|--------|--------|
| Max speed (SL) | 593 kt / Mach 0.89 | [1][2] |
| Max speed (10K ft) | 618 kt / Mach 0.93 | [1][2] |
| Rate of climb | 12,800 fpm (65 m/s) | [1][2] |
| Service ceiling | 54,500 ft | [1][2] |

## Aircraft Weight & Fuel Specifications

| Parameter | Value | Notes |
|-----------|-------|-------|
| Empty weight | 3,920 kg | With pilot (M_empty) |
| Nominal weight | 5,345 kg | Empty + full internal fuel (M_nominal) |
| Max takeoff weight | 6,075 kg | M_max |
| Internal fuel capacity | 1,140 kg | M_fuel_max |
| Military thrust | 2,650 kgf | 26.5 kN |
| Afterburner thrust | 3,380 kgf | 33.8 kN (1.28x military) |

### Fuel Consumption

The VK-1F engine fuel consumption varies with throttle setting:
- **Military power (cemax)**: ~1.24 (reference multiplier for AI calculations)
- **Afterburner (cefor)**: ~2.56 (~2.06x military power consumption)

### Afterburner Behavior

The afterburner engages automatically at full throttle:
- `has_afteburner = true` in flight model
- `ForsRUD = 1` - afterburner activates at max throttle position
- No separate afterburner zone; it's binary on/off at full throttle

### Test Group Fuel Loads

| Test Group | Fuel Load | Rationale |
|------------|-----------|-----------|
| CLIMB_SL, CLIMB_10K | 100% (1,140 kg) | Historical ROC at nominal weight |
| ACCEL_*, VMAX_* | 50% (570 kg) | Mid-mission weight scenario |
| TURN_10K_* | 50% (570 kg) | Combat maneuvering weight |
| DECEL_10K | 50% (570 kg) | Standard test configuration |

## Log Format

The test script logs structured data to `dcs.log` with the prefix `[MIG17_FM_TEST]`:

```
START,<group>,alt=<alt_ft>,spd=<spd_kt>,fuel_kg=<fuel>,fuel_pct=<pct>,weight_kg=<weight>
DATA,<group>,<elapsed_s>,<alt_ft>,<spd_kt>,<vspd_fpm>,<mach>
SPEED_GATE,<group>,<gate_kt>,<elapsed_s>,<alt_ft>
ALT_GATE,<group>,<gate_ft>,<elapsed_s>,<climb_rate_fpm>
VMAX,<group>,<speed_kt>,<alt_ft>,<mach>
SUMMARY,<group>,<max_spd_kt>,<max_alt_ft>,<max_vspd_fpm>,fuel_start=<kg>,fuel_end=<kg>,fuel_used=<kg>
```

The fuel fields allow tracking of:
- Initial fuel load and aircraft weight at test start
- Fuel consumption during each test profile
- Comparison of fuel burn rates between military power and afterburner operation

## Legacy Test Script

The older `mig17_accel_test.lua` is retained for reference but the mission generator
now embeds a more comprehensive logging script directly via a Mission Start trigger.
