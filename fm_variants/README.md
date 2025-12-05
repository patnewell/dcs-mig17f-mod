# MiG-17F SFM Variant Configuration

This directory describes a set of MiG-17F simple flight model (SFM) variants
used for black-box testing in DCS to calibrate the VWV MiG-17F AI flight model.

The canonical configuration file is:

- `fm_variants/mig17f_fm_variants.json`

## JSON structure

The JSON file has the following top-level shape:

- `version` (number): schema version (currently `1`).
- `aircraft` (object):
  - `id`: base DCS type name (for the stock mod), e.g. `vwv_mig17f`.
  - `base_mod_dir`: the folder name of the base mod in the repo, e.g. `[VWV] MiG-17`.
  - `base_display_name`: original `DisplayName` from `mig17f.lua`.
  - `description`: human-readable description.
- `scaling_model` (object): documentation for how each numeric scale is applied.
- `variants` (array): list of variant definitions. Each element has:
  - `variant_id`: stable identifier for this variant, e.g. `FM6_DRAG0.5_ALL`.
  - `short_name`: short ID such as `FM6` used in group names and logs.
  - `mod_dir_name`: name of the generated mod directory under `fm_variants/`.
  - `dcs_type_name`: the `Name` value to write into `Database/mig17f.lua` for this variant.
  - `shape_username`: the `username` field inside `shape_table_data` for this variant
    (ensures DCS treats each variant as a distinct aircraft type).
  - `display_name`: the `DisplayName` value to write into `Database/mig17f.lua`.
  - `scales` (object):
    - `cx0`: factor to multiply all Cx0 entries in `SFM_Data.aerodynamics.table_data`.
    - `polar`: factor to multiply all B2 and B4 entries in `SFM_Data.aerodynamics.table_data`.
    - `engine_drag`: factor to multiply `SFM_Data.engine.dcx_eng`.
    - `pfor`: factor to multiply all `Pfor` entries in `SFM_Data.engine.table_data`.
  - `notes`: free-form description of the intent of this variant.

All scaling factors are **multiplicative** relative to the current baseline SFM
in the base mod's `Database/mig17f.lua`.

## How to apply a variant to produce a new flight model

Given:

- The base MiG-17F mod in `[VWV] MiG-17/`
- A single variant entry from `mig17f_fm_variants.json`

You can produce a new mod folder as follows (this is what the automation script
is expected to do):

1. **Copy the base mod folder**

   - Source: `[VWV] MiG-17/`
   - Destination: `fm_variants/mods/<mod_dir_name>/`, where `<mod_dir_name>` comes from the
     variant's `mod_dir_name` field.

   Note: The `mods/` subdirectory is gitignored since the mods can be regenerated
   from this JSON configuration.

2. **Patch identity fields in `Database/mig17f.lua`**

   In the copied mod:

   - Set the `Name` field to the variant's `dcs_type_name`.
   - Set the `DisplayName` field to the variant's `display_name`.
   - In `shape_table_data`, set `username` to the variant's `shape_username`.

   This ensures each variant appears in DCS as a distinct aircraft type that can
   coexist with the others in the same mission.

3. **Apply SFM scaling**

   Inside `SFM_Data` in `Database/mig17f.lua`:

   - **Parasite drag (Cx0)**  
     In `aerodynamics.table_data`, each row is of the form:

     `{ M, Cx0, Cya, B2, B4, Omxmax, Aldop, Cymax }`

     Multiply **only** the `Cx0` value in each row by `scales.cx0`.

   - **Induced / polar drag (B2/B4)**  
     In the same `table_data` rows, multiply:

     - `B2` by `scales.polar`
     - `B4` by `scales.polar`

   - **Engine drag fudge (`dcx_eng`)**  
     In `SFM_Data.engine`, multiply the single `dcx_eng` value by `scales.engine_drag`.

   - **Afterburner thrust (`Pfor`)**  
     In `SFM_Data.engine.table_data`, each row has:

     `{ M, Pmax, Pfor }`

     Multiply the `Pfor` value in each row by `scales.pfor`.  
     **Do not** change `Pmax`; the idea is to preserve MIL thrust and only perturb AB.

4. **Leave everything else unchanged**

   - Mass properties (`M_empty`, `M_nominal`, etc.) remain unchanged.
   - Lift coefficients (`Cy0`, `Cya`) and max lift (`Cymax`) remain unchanged.
   - Control authorities and inertia (`Mzalfa`, `kjx`, `kjz`, etc.) remain unchanged.

   The goal is to treat these variants purely as *drag/thrust* sweeps around the
   current SFM, so we can empirically back-solve what the correct drag/thrust
   envelope needs to be.

## How the variants are intended to be used

The current variant set is designed to give both:

- **Axis-specific sensitivity tests** (change only one parameter family at a time):
  - FM1: Cx0 only
  - FM2: B2/B4 only
  - FM3: engine drag only
  - FM4: afterburner thrust only

- **Composite candidates near the suspected “good” region**:
  - FM5: moderate drag reduction across all drag knobs (0.6x)
  - FM6: stronger drag reduction across all drag knobs (0.5x)
  - FM7: FM6 + small AB boost (+5%)
  - FM8: FM6 + larger AB boost (+10%)

Running all of these in a single mission (with each FM variant flying the same
test profiles side by side) should give enough data to:

- Estimate how Vmax, climb, and sustained turn scale with each drag/thrust knob.
- Identify which composite variant lies closest to the historical performance targets.
- Interpolate/extrapolate to a “production” SFM by choosing non-extreme scale
  factors (e.g. somewhere between the FM5–FM8 cluster).

## Logging and test naming conventions

Downstream tooling (mission generator and log parser) is expected to:

- Use `short_name` (e.g. `FM6`) as a **prefix** in DCS group names:
  - `FM6_ACCEL_SL`, `FM6_VMAX_10K`, etc.
- Use that same `short_name` as the *variant key* in test logs and summaries.

This README and JSON are intentionally decoupled from any particular automation
implementation; the Python tooling and mission generator should treat this file
as the single source of truth for which variants exist and how their SFM
coefficients should be derived from the base mod.
