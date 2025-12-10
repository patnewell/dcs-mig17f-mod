# DCS SFM Tools – Refactor Plan (Multi‑Aircraft, CLI‑First)

This document describes how to refactor the current `tools/` repo into a more structured, reusable application that:

- Has a clear, testable **core library** (Python package).
- Exposes a **CLI entrypoint** as the first “app front-end”.
- Can later serve as the **backend** for a web UI or native Windows app.
- Keeps DCS-specific glue isolated from analysis & domain logic.

The initial target is a CLI-only app; web/GUI can be layered on later.

---

## 1. Goals & Constraints

### 1.1 Functional goals

- Manage DCS SFM aircraft flight model variants and mod builds.
- Generate FM and BFM test missions.
- Orchestrate automated test runs (DCS dedicated server flow).
- Parse and analyze:
  - DCS logs (FM calibration tests).
  - TacView ACMI (BFM & envelope tests).
- Persist test runs (input config + outputs) in a structured way for later analysis.

### 1.2 Non-functional goals

- **Refactorable**: future aircraft / missions should reuse most of the code.
- **Testable**: core logic decoupled from DCS paths / OS specifics; easy to unit test.
- **Composable**: same code should work in:
  - CLI (current focus).
  - Long-running backend process (future web UI).
- **Minimal dependencies** (for now):
  - Prefer standard library & `argparse` for CLI.
  - Avoid heavy frameworks until necessary.

### 1.3 Current state (high-level)

From `tools/` package (current repo):

- `mig17_fm_tool.py`: “mega” CLI script that imports:
  - `build_mig17f_variants_from_json`
  - `generate_mig17_fm_test_mission`
  - `parse_fm_test_log`
  - `run_fm_test`
  - `generate_bfm_test_mission`
  - `bfm_acmi_analyzer`
  - `run_bfm_test`
- `run_fm_test.py`: orchestrates full FM test (build, install, mission, DCS, parse, report).
- `run_bfm_test.py`: similar orchestration for BFM.
- `generate_*_mission.py`: mission generators.
- `build_mig17f_variants_from_json.py`: builds mod variants from FM JSON.
- `parse_fm_test_log.py`: DCS log parser.
- `bfm_acmi_analyzer.py`, `acmi_bfm_envelope_analysis.py`: TacView ACMI analysis.
- `tests/`: some unit tests for run\_fm\_test / run\_bfm\_test / analyzers.

The codebase is already modular-ish, but everything lives flat under `tools/` and there’s no clean separation between:

- CLI / orchestration
- DCS integration
- FM / mission domain logic
- Analysis & persistence

---

## 2. Proposed Package Structure

Refactor `tools/` into a more structured package while keeping the name (for now) to minimize churn.

### 2.1 Target layout

```text
tools/
  __init__.py

  # Core domain / config
  core/
    __init__.py
    config.py         # Load/save JSON configs (FM variants, BFM mission tests, run_info)
    paths.py          # DCSPaths resolution, test_runs dir, etc.
    models.py         # Dataclasses for FM variants, missions, test runs, envelopes

  # DCS integration layer
  dcs/
    __init__.py
    install.py        # Install/remove mod variants into DCS Mods/aircraft
    missions.py       # Generate .miz files (FM tests, BFM tests)
    server.py         # Launch/stop DCS or DCS server, handle timeouts
    logs.py           # Tail dcs.log, detect completion markers

  # FM & mission-specific logic
  fm/
    __init__.py
    variants.py       # Build SFM variants (any supported aircraft) from FM JSON, apply scaling to baseline
    fm_runner.py      # High-level FM test orchestration (logic-only, no CLI parsing)

  bfm/
    __init__.py
    mission_generator.py  # BFM mission generation logic
    acmi_analysis.py      # TacView ACMI parsing + BFM metrics (currently in bfm_acmi_analyzer & acmi_bfm_envelope_analysis)
    bfm_runner.py         # High-level BFM test orchestration (logic-only)

  # CLI / app front-end
  cli/
    __init__.py
    main.py           # Entry point (argparse) – replaces mig17_fm_tool.py
    fm_commands.py    # Subcommands for FM tests (generate-mission, run-test, parse-log, etc.)
    bfm_commands.py   # Subcommands for BFM tests (generate-mission, run-test, analyze-acmi)
    util.py           # Shared CLI helpers: logging setup, common arguments

  # Backward-compat (thin wrappers)
  mig17_fm_tool.py    # Will delegate to tools.cli.main.main()
  run_fm_test.py      # Will delegate to fm.fm_runner & cli
  run_bfm_test.py     # Will delegate to bfm.bfm_runner & cli

  # Tests
  tests/
    test_core_paths.py
    test_fm_runner.py
    test_bfm_runner.py
    test_acmi_analysis.py
    resources/...
```

---

## 3. Layering & Responsibilities

### 3.1 `tools.core`

Holds:

- Shared dataclasses and configuration/state handling.
- Centralized path and config management.

### 3.2 `tools.dcs`

Responsible for:

- Installing/removing mods.
- Generating missions.
- Launching/stopping DCS or DCS Dedicated Server.
- Tail dcs.log and detect completion.

### 3.3 `tools.fm`

Contains generic SFM FM logic (aircraft‑agnostic):

- Variant construction.
- FM test orchestration.

### 3.4 `tools.bfm`

Contains:

- BFM mission generation.
- TacView ACMI parsing & analysis.
- BFM test orchestration.

### 3.5 `tools.cli`

Layer that:

- Exposes commands to users.
- Delegates to orchestrators.
- Handles CLI-only behavior.

---

## 4. Implementation Phases (for Claude Code)

### Phase 1 – Introduce core structures, keep behavior the same

- Create subpackages: `core`, `dcs`, `fm`, `bfm`, `cli`.
- Consolidate shared models into `core.models`.
- Consolidate paths logic into `core.paths`.
- Consolidate JSON loading into `core.config`.

### Phase 2 – Split orchestration from top-level scripts

- Move FM variant build logic into `fm.variants`.
- Move mission generation into `dcs.missions`.
- Move DCS launch & log-tail logic into `dcs.server` & `dcs.logs`.
- Create `fm.fm_runner` & `bfm.bfm_runner`.

### Phase 3 – Clean up analysis & CLI

- Create `bfm.acmi_analysis`.
- Create `cli.main`, `cli.fm_commands`, `cli.bfm_commands`.

### Phase 4 – Tests and future backend

- Add tests around new modules.
- Ensure orchestrators return dataclasses suitable for HTTP API usage.

---

## 5. Notes for Claude Code

- Avoid behavior changes in Phase 1 & 2.
- Use dataclasses for all shared models.
- Use absolute imports inside package.
- Document each new module with a clear responsibility.

