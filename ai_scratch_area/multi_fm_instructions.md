You are working on my MiG-17F DCS mod repository.

The repo contains:

- `[VWV] MiG-17/Database/mig17f.lua` – the base aircraft definition and SFM.  
- `tools/generate_mig17_fm_test_mission.py` – the current FM test mission generator.  
- `tools/parse_fm_test_log.py` – the current log parser for `[MIG17_FM_TEST]` lines.  
- `fm_variants/mig17f_fm_variants.json` – the FM variant definitions (you must not modify this).  
- `fm_variants/README.md` – documentation of the variant format (you must not modify this).

I want you to convert this project into a **multi-FM experimental framework** while keeping everything backward-compatible.

You must **NOT** modify the JSON or README that define the flight model variants.  
Your job is only to generate new scripts and update existing ones to use that JSON.

---

## Task 1 — Create a script to generate variant mod folders from the JSON

Create a new script in `tools/` (you choose the filename, e.g. `build_mig17f_variants_from_json.py`) that:

### 1. Reads the FM variant JSON

- Load `fm_variants/mig17f_fm_variants.json`.
- Use the `aircraft` block and the `variants` array exactly as described in the JSON and README.

### 2. Provides a CLI

The script must support:

- `--base-mod-root` (default: repo root + base_mod_dir from JSON)
- `--variants-root` (default: `./fm_variants`)
- `--dcs-saved-games` (optional path to Saved Games)

### 3. Builds variant mod folders

For each variant in the JSON:

- Copy the base mod directory into `variants-root/<mod_dir_name>`.
- Modify `Database/mig17f.lua` inside the copied folder:

  Set:
  - `Name = <dcs_type_name>`
  - `DisplayName = <display_name>`
  - `shape_table_data[0].username = <shape_username>`

- Apply scaling rules exactly as documented in `README.md`:

  - Multiply all **Cx0** entries by `scales.cx0`
  - Multiply all **B2** and **B4** entries by `scales.polar`
  - Multiply `dcx_eng` by `scales.engine_drag`
  - Multiply all **Pfor** values by `scales.pfor`
  - Do **not** modify Pmax

- Nothing else in the mod should change.

### 4. Optional installation to Saved Games

If `--dcs-saved-games` is provided:

- Copy all built variant mod folders into:  
  `<saved_games>/Mods/aircraft/<variant.mod_dir_name>/`

### 5. Logging

The script must log:

- Which variants were built
- Where the variant folders were created
- Whether they were installed to Saved Games

---

## Task 2 — Update mission generator (`generate_mig17_fm_test_mission.py`)

Add multi-FM support, while retaining single-FM compatibility.

### 1. CLI change

Add:

- `--variant-root` (default: `./fm_variants`)

### 2. Auto-detection of FM variants

If `<variant-root>/mig17f_fm_variants.json` exists:

- Load the JSON
- Build an internal list of variant descriptors containing:

  - `short_name`  
  - `mod_dir_name`  
  - `dcs_type_name`

Else:

- Fall back to original single-FM behavior.

### 3. Build one “lane” of flight tests per FM variant

For each FM variant:

- Use the exact same test patterns from the current script:

  - ACCEL_SL  
  - ACCEL_10K  
  - ACCEL_20K  
  - CLIMB_SL  
  - CLIMB_10K  
  - TURN_10K_300  
  - TURN_10K_350  
  - TURN_10K_400  
  - VMAX_SL  
  - VMAX_10K  
  - DECEL_10K  

- These test definitions must remain unchanged.

- Offset each variant’s lane along the X-axis by a fixed per-variant delta (e.g., 80 km increments) to avoid collisions.

- Prefix **all** group names with the FM variant short name:

  Example:  
  - `FM0_ACCEL_SL`  
  - `FM4_VMAX_10K`

### 4. Update logger injection

The current script uses a static `LOGGER_LUA` with a hard-coded group list.

Replace this with:

- A Lua template containing a placeholder for `MIG17_TEST.GROUPS`
- A Python function that:
  - Takes the exact list of generated group names (e.g., `FM6_ACCEL_SL`)
  - Renders a filled-in Lua string
- That rendered Lua string should then be injected into the mission trigger.

All output lines must keep their existing format:
- `[MIG17_FM_TEST] DATA,...`
- `[MIG17_FM_TEST] SPEED_GATE,...`
- `[MIG17_FM_TEST] ALT_GATE,...`
- `[MIG17_FM_TEST] VMAX,...`
- `[MIG17_FM_TEST] SUMMARY,...`

### 5. Backwards compatibility

If no variant JSON is found:

- The mission generator should behave exactly as today:
- One aircraft type
- Original group names (no prefixes)
- Original static logger list

---

## Task 3 — Update log parser (`parse_fm_test_log.py`)

Adapt the parser for the new multi-FM mission.

### 1. Continue matching only `[MIG17_FM_TEST]` lines.

### 2. New group name structure

In multi-FM missions, group names look like:

- `FM6_VMAX_10K`
- `FM3_CLIMB_SL`

You must:

- Split variant + test name on the first underscore.
- If no prefix exists (old missions), treat as:
  - `variant_key = "FM0"`
  - `test_name = full_group_name`

### 3. Aggregate results

Store results as:

- `results[variant_key][test_name] -> metrics`

Metrics include whatever the current script already extracts (max speed, max alt, climb rate, VMAX Mach, etc.).

### 4. Output format

When printing:

- Print a section for each variant, e.g.:

```
=== Variant FM6 ===
VMAX_10K: ...
CLIMB_SL: ...
```

If writing CSV:

- Add separate `variant` and `test` columns.

### 5. Backwards compatibility

Old logs without prefixes must still parse correctly and map to a default variant (e.g., `"FM0"`).

---

## Completion checklist

Before finishing, you must verify:

1. The new builder script reads the JSON and produces mod folders with the correct edited values.  
2. The mission generator:
   - Works unchanged in single-FM mode.
   - Builds a multi-FM mission when JSON is present.
   - Generates correct group names (prefixed).
   - Injects a dynamically-built Lua logger.  
3. The log parser:
   - Correctly extracts variant + test.
   - Processes old and new missions.
   - Outputs variant-separated summaries.


