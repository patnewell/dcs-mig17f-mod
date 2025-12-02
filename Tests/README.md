# MiG-17F FM Test Mission

This mission concept exercises level-acceleration performance for the MiG-17F mod using three AI groups and logs results to `dcs.log` via `mig17_accel_test.lua`.

**Note:** The `.miz` file is not bundled here (binary files are excluded). To recreate it, copy `codex_ref/mig17_template.miz` to your Saved Games mission folder, add the ACCEL_SL / ACCEL_10K / ACCEL_20K groups for the `vwv_mig17f` unit with the described waypoints, and attach `Tests/mig17_accel_test.lua` via a Mission Start DO SCRIPT FILE trigger.

## Expected Behavior
- **Sea level (~1,000 ft):** Clean MiG-17F should accelerate from ~230 KIAS to roughly 595–605 KIAS (≈ Mach 0.90) before leveling off.
- **10,000 ft:** Plateau around 610–620 KIAS (≈ Mach 0.95–0.97).
- **20,000 ft:** Plateau slightly lower in knots but near Mach 1.0 (subsonic in sustained level flight).
- `[ACCEL_TEST]` lines in `Saved Games\\DCS...\\Logs\\dcs.log` report time-to-speed gates and plateau speeds.
