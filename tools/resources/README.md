# Tools Resources

This directory contains configuration files for the MiG-17F flight model development tools.

## File Types

### Flight Models (flight_models.json / mig17f_*.json)
Configuration files defining MiG-17F flight model variants with scaling factors for
SFM coefficients. Used by `build-variants` and `quick-bfm-setup` commands.

### Flight Scenarios (flight_scenarios.json / bfm_*.json)
Configuration files defining BFM engagement scenarios for testing. Used by
`generate-bfm-mission` and `quick-bfm-setup` commands.

## Usage

```bash
# Quick BFM setup with custom configs
python -m tools.mig17_fm_tool quick-bfm-setup \
    --variant-json tools/resources/flight_models_rc1.json \
    --bfm-config tools/resources/flight_scenarios_f4e.json
```
