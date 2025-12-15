#!/usr/bin/env python3
"""MiG-17F Flight Model Development Tool.

This is the main entry point for all MiG-17F flight model development tasks.
It provides subcommands for mission generation, log parsing, variant building,
and orchestrating complete test runs.

Usage:
    python tools/mig17_fm_tool.py <command> [options]

Commands:
    generate-mission      Generate FM test mission (.miz file)
    parse-log             Parse DCS log for test results
    build-variants        Build FM variant mods from JSON configuration
    run-test              Run complete FM test workflow (build, install, test, analyze)
    generate-bfm-mission  Generate BFM (dogfight) test mission
    analyze-bfm           Analyze TacView ACMI file for BFM metrics
    run-bfm-test          Run complete BFM test workflow
    quick-bfm-setup       Build variants & BFM mission, install to DCS (ready to fly)
    promote-variant       Promote a variant to become the new baseline mod

Examples:
    # Generate a test mission
    python tools/mig17_fm_tool.py generate-mission --outfile mission.miz

    # Parse test results from DCS log
    python tools/mig17_fm_tool.py parse-log --csv results.csv

    # Build FM variant mods
    python tools/mig17_fm_tool.py build-variants --dcs-saved-games "C:/Users/.../DCS"

    # Run complete test workflow
    python tools/mig17_fm_tool.py run-test --timeout 900

    # Generate BFM test mission
    python tools/mig17_fm_tool.py generate-bfm-mission --max-priority 2

    # Analyze BFM test from ACMI file
    python tools/mig17_fm_tool.py analyze-bfm latest --csv results.csv

    # Run complete BFM test
    python tools/mig17_fm_tool.py run-bfm-test --max-priority 2

    # Quick BFM setup (builds variants, generates mission, installs to DCS)
    python tools/mig17_fm_tool.py quick-bfm-setup --variant-json fm_variants/mig17f_rc1.json

    # Promote a variant to become the new baseline mod
    python tools/mig17_fm_tool.py promote-variant RC1_1_G6_FLAPS05 --version RC2 \
        --config-dir ai_scratch_area/stage5_tuning
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Optional, Sequence

# Import the individual modules
from tools import (
    build_mig17f_variants_from_json as builder,
    generate_mig17_fm_test_mission as generator,
    parse_fm_test_log as parser,
    run_fm_test as runner,
    generate_bfm_test_mission as bfm_generator,
    bfm_acmi_analyzer as bfm_analyzer,
    run_bfm_test as bfm_runner,
)

LOGGER = logging.getLogger(__name__)


def cmd_generate_mission(args: argparse.Namespace) -> int:
    """Handle the generate-mission subcommand."""
    # Check for multi-FM variant JSON
    variant_json = args.variant_json
    variants: Optional[list[generator.VariantDescriptor]] = None

    if variant_json.exists():
        LOGGER.info("Found variant JSON: %s", variant_json)
        variants = generator.load_variant_descriptors(variant_json)
        LOGGER.info("Loaded %d FM variants for multi-FM mission", len(variants))
        type_name = "multi_fm_mode"
    else:
        LOGGER.info("No variant JSON found, using single-FM mode")
        type_name = args.type_name or generator.detect_type_name(args.mod_root)
        if not type_name:
            LOGGER.error(
                "Could not determine MiG-17 type name. Use --type-name to set it explicitly."
            )
            return 2

    generator.ensure_parent(args.outfile)

    try:
        miz, groups, run_id = generator.build_mission(type_name, variants)
    except Exception as exc:
        LOGGER.exception("Failed to build mission: %s", exc)
        return 4

    try:
        miz.save(args.outfile)
    except Exception as exc:
        LOGGER.exception("Failed to save mission: %s", exc)
        return 5

    LOGGER.info("MiG-17 FM test mission generated.")
    LOGGER.info("Output : %s", args.outfile)
    LOGGER.info("Run ID : %s", run_id)
    if variants:
        LOGGER.info("Mode   : Multi-FM (%d variants)", len(variants))
        for v in variants:
            LOGGER.info("  - %s (%s)", v.short_name, v.dcs_type_name)
    else:
        LOGGER.info("Type   : %s", type_name)
    LOGGER.info("Groups : %d total", len(groups))
    for name in groups:
        LOGGER.info("  - %s", name)

    print(f"RUN_ID={run_id}")
    return 0


def cmd_parse_log(args: argparse.Namespace) -> int:
    """Handle the parse-log subcommand."""
    log_path = args.log_file
    if not log_path:
        log_path = parser.find_dcs_log()
        if not log_path:
            LOGGER.error("Could not find DCS log file. Use --log-file to specify.")
            return 1

    if not log_path.exists():
        LOGGER.error("Log file not found: %s", log_path)
        return 1

    LOGGER.info("Parsing log file: %s", log_path)

    results = parser.parse_log_file(log_path)

    if not results:
        LOGGER.warning("No MIG17_FM_TEST data found in log file")
        LOGGER.info("Run the FM test mission in DCS first, then parse the log")
        return 2

    total_groups = sum(len(variant_results) for variant_results in results.values())
    num_variants = len(results)
    LOGGER.info(
        "Found data for %d test groups across %d variant(s)",
        total_groups,
        num_variants,
    )
    for variant_key in sorted(results.keys()):
        LOGGER.info("  %s: %d tests", variant_key, len(results[variant_key]))

    report = parser.generate_report(results)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
        LOGGER.info("Report written to: %s", args.output)
    else:
        print(report)

    if args.csv:
        parser.write_csv(results, args.csv)

    return 0


def cmd_build_variants(args: argparse.Namespace) -> int:
    """Handle the build-variants subcommand."""
    json_path = args.json_file.resolve()
    variants_root = args.variants_root.resolve()
    variants_root.mkdir(parents=True, exist_ok=True)

    if not json_path.exists():
        LOGGER.error("FM variants JSON not found: %s", json_path)
        return 1

    LOGGER.info("Loading variant configuration from: %s", json_path)
    config = builder.load_variant_config(json_path)
    LOGGER.info("Found %d variants to build", len(config.variants))

    base_mod_path = args.base_mod_root
    if not base_mod_path:
        repo_root = json_path.parent.parent
        base_mod_path = repo_root / config.base_mod_dir

    base_mod_path = base_mod_path.resolve()

    if not base_mod_path.exists():
        LOGGER.error("Base mod not found: %s", base_mod_path)
        return 1

    LOGGER.info("Base mod path: %s", base_mod_path)
    LOGGER.info("Variants output: %s", variants_root)

    built_variants: list[Path] = []
    for variant in config.variants:
        LOGGER.info("Building variant: %s (%s)", variant.short_name, variant.variant_id)
        variant_path = builder.build_variant(base_mod_path, variant, variants_root)
        built_variants.append(variant_path)
        LOGGER.info("  Created: %s", variant_path)

    if args.dcs_saved_games:
        dcs_saved_games = args.dcs_saved_games.resolve()
        if not dcs_saved_games.exists():
            LOGGER.warning("DCS Saved Games path does not exist: %s", dcs_saved_games)
        else:
            LOGGER.info("Installing variants to DCS Saved Games: %s", dcs_saved_games)
            for variant_path in built_variants:
                builder.install_to_saved_games(variant_path, dcs_saved_games)
            LOGGER.info("Installation complete")

    LOGGER.info("=" * 60)
    LOGGER.info("Build Summary")
    LOGGER.info("=" * 60)
    LOGGER.info("Variants built: %d", len(built_variants))
    for path in built_variants:
        LOGGER.info("  - %s", path.name)
    if args.dcs_saved_games:
        LOGGER.info("Installed to: %s", args.dcs_saved_games)

    return 0


def cmd_run_test(args: argparse.Namespace) -> int:
    """Handle the run-test subcommand."""
    repo_root = runner.find_repo_root()
    LOGGER.info("Repository root: %s", repo_root)

    # Handle analyze-only mode
    if args.analyze_only:
        LOGGER.info("Analyze-only mode: %s", args.analyze_only)
        if not args.analyze_only.exists():
            LOGGER.error("Log file not found: %s", args.analyze_only)
            return 1

        from datetime import datetime
        import shutil

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = repo_root / "test_runs" / f"{timestamp}_analysis"
        run_dir.mkdir(parents=True, exist_ok=True)

        dest_log = run_dir / "dcs.log"
        shutil.copy2(args.analyze_only, dest_log)

        if not runner.run_analysis(repo_root, dest_log, run_dir):
            return 1
        return 0

    # Detect DCS paths
    try:
        dcs_paths = runner.DCSPaths.detect(args.dcs_path, args.saved_games)
    except FileNotFoundError as e:
        LOGGER.error(str(e))
        return 1

    LOGGER.info("DCS installation: %s", dcs_paths.install_dir)
    LOGGER.info("DCS Saved Games: %s", dcs_paths.saved_games)

    # Resolve variant JSON path if provided
    variant_json = args.variant_json.resolve() if args.variant_json else None

    # Step 1: Build FM variants
    if not args.skip_build:
        if not runner.run_build_variants(repo_root, dcs_paths, variant_json):
            return 1

    # Step 2: Install base mod
    if not runner.install_base_mod(repo_root, dcs_paths):
        return 1

    # Step 3: Generate mission
    run_id = runner.generate_mission(repo_root, dcs_paths, variant_json)
    if not run_id:
        return 1

    # Step 4: Launch DCS
    if not args.skip_launch:
        if not runner.launch_dcs(dcs_paths):
            return 1

    # Step 5: Wait for test completion
    LOGGER.info("")
    LOGGER.info("*" * 60)
    LOGGER.info("ACTION REQUIRED:")
    LOGGER.info("  1. In DCS, go to Mission Editor")
    LOGGER.info("  2. Load: %s", dcs_paths.missions_dir / "MiG17F_FM_Test.miz")
    LOGGER.info("  3. Click 'Fly' to start the mission")
    LOGGER.info("  4. Wait for the test to complete (~10 minutes)")
    LOGGER.info("*" * 60)
    LOGGER.info("")

    if not runner.wait_for_test_completion(dcs_paths, run_id, args.timeout):
        LOGGER.error("Test did not complete successfully")
        return 1

    # Step 6: Archive test data
    archived_log = runner.copy_log_to_test_runs(dcs_paths, repo_root, run_id)
    if not archived_log:
        return 1

    run_dir = archived_log.parent

    # Step 7: Run analysis
    if not runner.run_analysis(repo_root, archived_log, run_dir):
        return 1

    LOGGER.info("")
    LOGGER.info("=" * 60)
    LOGGER.info("TEST RUN COMPLETE")
    LOGGER.info("=" * 60)
    LOGGER.info("Run ID: %s", run_id)
    LOGGER.info("Results: %s", run_dir)

    return 0


def cmd_generate_bfm_mission(args: argparse.Namespace) -> int:
    """Handle the generate-bfm-mission subcommand."""
    # Load BFM configuration
    if not args.bfm_config.exists():
        LOGGER.error("BFM config not found: %s", args.bfm_config)
        return 1

    LOGGER.info("Loading BFM configuration from: %s", args.bfm_config)
    bfm_config = bfm_generator.load_bfm_config(args.bfm_config)
    LOGGER.info("Loaded %d scenarios", len(bfm_config.scenarios))

    # Check for multi-FM mode
    variants = None
    if args.variant_json.exists():
        LOGGER.info("Found variant JSON: %s", args.variant_json)
        variants = bfm_generator.load_variant_descriptors(args.variant_json)
        LOGGER.info("Multi-FM mode: %d variants", len(variants))
        mig17_type = "multi_fm_mode"
    else:
        LOGGER.info("Single-FM mode: %s", args.type_name)
        mig17_type = args.type_name

    # Build mission
    try:
        miz, groups, run_id = bfm_generator.build_bfm_mission(
            bfm_config,
            mig17_type,
            variants,
            max_priority=args.max_priority,
        )
    except Exception as exc:
        LOGGER.exception("Failed to build mission: %s", exc)
        return 2

    # Ensure output directory exists
    args.outfile.parent.mkdir(parents=True, exist_ok=True)

    # Save mission
    try:
        miz.save(args.outfile)
    except Exception as exc:
        LOGGER.exception("Failed to save mission: %s", exc)
        return 3

    LOGGER.info("BFM test mission generated successfully")
    LOGGER.info("Output : %s", args.outfile)
    LOGGER.info("Run ID : %s", run_id)
    LOGGER.info("Groups : %d", len(groups))

    print(f"RUN_ID={run_id}")
    return 0


def cmd_analyze_bfm(args: argparse.Namespace) -> int:
    """Handle the analyze-bfm subcommand."""
    acmi_path = args.acmi_path

    # Handle 'latest' keyword
    if str(acmi_path).lower() == "latest":
        tacview_dir = bfm_runner.get_tacview_dir()
        acmi_path = bfm_runner.find_latest_acmi(tacview_dir)
        if not acmi_path:
            LOGGER.error("No ACMI files found in %s", tacview_dir)
            return 1
        LOGGER.info("Using latest ACMI: %s", acmi_path)
    elif not acmi_path.exists():
        LOGGER.error("ACMI file not found: %s", acmi_path)
        return 1

    results = bfm_analyzer.analyze_acmi_file(acmi_path, args.bfm_config)

    if not results:
        LOGGER.warning("No BFM engagement data found in ACMI file")
        return 2

    report = bfm_analyzer.generate_report(results)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
        LOGGER.info("Report written to: %s", args.output)
    else:
        print(report)

    if args.csv:
        bfm_analyzer.write_csv(results, args.csv)
        LOGGER.info("CSV written to: %s", args.csv)

    return 0


def cmd_run_bfm_test(args: argparse.Namespace) -> int:
    """Handle the run-bfm-test subcommand."""
    repo_root = bfm_runner.find_repo_root()
    LOGGER.info("Repository root: %s", repo_root)

    # Handle analyze-only mode
    if args.analyze_only:
        from datetime import datetime
        import shutil

        if args.analyze_only.lower() == "latest":
            tacview_dir = bfm_runner.get_tacview_dir()
            acmi_path = bfm_runner.find_latest_acmi(tacview_dir)
            if not acmi_path:
                LOGGER.error("No ACMI files found in %s", tacview_dir)
                return 1
            LOGGER.info("Using latest ACMI: %s", acmi_path)
        else:
            acmi_path = Path(args.analyze_only)
            if not acmi_path.exists():
                LOGGER.error("ACMI file not found: %s", acmi_path)
                return 1

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = repo_root / "test_runs" / f"{timestamp}_bfm_analysis"
        run_dir.mkdir(parents=True, exist_ok=True)

        dest_acmi = run_dir / acmi_path.name
        shutil.copy2(acmi_path, dest_acmi)

        if not bfm_runner.run_analysis(repo_root, dest_acmi, run_dir):
            return 1
        return 0

    # Detect DCS paths
    try:
        dcs_paths = bfm_runner.DCSPaths.detect(args.dcs_path, args.saved_games)
    except FileNotFoundError as e:
        LOGGER.error(str(e))
        return 1

    LOGGER.info("DCS installation: %s", dcs_paths.install_dir)
    LOGGER.info("DCS Saved Games: %s", dcs_paths.saved_games)

    # Step 1: Build FM variants
    if not args.skip_build:
        if not bfm_runner.run_build_variants(repo_root, dcs_paths):
            return 1

    # Step 2: Install base mod
    if not bfm_runner.install_base_mod(repo_root, dcs_paths):
        return 1

    # Step 3: Generate mission
    run_id = bfm_runner.generate_bfm_mission(repo_root, dcs_paths, args.max_priority)
    if not run_id:
        return 1

    # Step 4: Launch DCS
    if not args.skip_launch:
        if not bfm_runner.launch_dcs(dcs_paths):
            return 1

    # Instructions
    LOGGER.info("")
    LOGGER.info("*" * 60)
    LOGGER.info("ACTION REQUIRED:")
    LOGGER.info("  1. In DCS, go to Mission Editor")
    LOGGER.info("  2. Load: %s", dcs_paths.missions_dir / "MiG17F_BFM_Test.miz")
    LOGGER.info("  3. Click 'Fly' to start the mission")
    LOGGER.info("  4. Wait for BFM scenarios to complete (~10 minutes)")
    LOGGER.info("*" * 60)
    LOGGER.info("")

    from datetime import datetime
    mission_start_time = datetime.now()

    # Step 5: Wait for test completion
    if not bfm_runner.wait_for_test_completion(dcs_paths, run_id, args.timeout):
        LOGGER.warning("Test completion markers not found, proceeding anyway...")

    # Step 6: Wait for ACMI file
    acmi_path = bfm_runner.wait_for_acmi_file(mission_start_time)
    if not acmi_path:
        LOGGER.error("No ACMI file found")
        return 1

    # Copy and analyze
    run_dir = repo_root / "test_runs" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{run_id}_bfm"
    run_dir.mkdir(parents=True, exist_ok=True)
    dest_acmi = bfm_runner.copy_acmi_to_test_runs(acmi_path, repo_root, run_id)
    run_dir = dest_acmi.parent

    # Step 7: Analyze
    if not bfm_runner.run_analysis(repo_root, dest_acmi, run_dir):
        return 1

    LOGGER.info("")
    LOGGER.info("=" * 60)
    LOGGER.info("BFM TEST RUN COMPLETE")
    LOGGER.info("=" * 60)
    LOGGER.info("Run ID: %s", run_id)
    LOGGER.info("Results: %s", run_dir)

    return 0


def add_generate_mission_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the generate-mission subcommand parser."""
    parser_gen = subparsers.add_parser(
        "generate-mission",
        help="Generate FM test mission (.miz file)",
        description="Generate a MiG-17 FM test mission with test profiles for "
        "acceleration, climb, turn, max speed, and deceleration.",
    )
    parser_gen.add_argument(
        "--outfile",
        default=Path.home() / "Saved Games" / "DCS" / "Missions" / "MiG17F_FM_Test.miz",
        type=Path,
        help="Path to output .miz file (directories will be created)",
    )
    parser_gen.add_argument(
        "--type-name",
        dest="type_name",
        help="Override the aircraft type name (defaults to value from Database/mig17f.lua)",
    )
    parser_gen.add_argument(
        "--mod-root",
        default=Path.cwd() / "[VWV] MiG-17",
        type=Path,
        help="Path to the MiG-17 mod folder containing Database/mig17f.lua",
    )
    parser_gen.add_argument(
        "--variant-root",
        dest="variant_root",
        default=Path("./fm_variants/mods"),
        type=Path,
        help="Path to FM variants directory (default: ./fm_variants/mods)",
    )
    parser_gen.add_argument(
        "--variant-json",
        dest="variant_json",
        default=Path("./fm_variants/mig17f_fm_variants.json"),
        type=Path,
        help="Path to FM variants JSON file (default: ./fm_variants/mig17f_fm_variants.json)",
    )
    parser_gen.set_defaults(func=cmd_generate_mission)


def add_parse_log_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the parse-log subcommand parser."""
    parser_log = subparsers.add_parser(
        "parse-log",
        help="Parse DCS log for test results",
        description="Parse the DCS log file for MIG17_FM_TEST data and generate "
        "a verification report comparing performance against historical targets.",
    )
    parser_log.add_argument(
        "--log-file",
        type=Path,
        help="Path to DCS log file (auto-detected if not specified)",
    )
    parser_log.add_argument(
        "--output",
        type=Path,
        help="Path to write report (prints to stdout if not specified)",
    )
    parser_log.add_argument(
        "--csv",
        type=Path,
        help="Path to write CSV output with variant and test columns",
    )
    parser_log.set_defaults(func=cmd_parse_log)


def add_build_variants_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the build-variants subcommand parser."""
    parser_build = subparsers.add_parser(
        "build-variants",
        help="Build FM variant mods from JSON configuration",
        description="Build MiG-17F flight model variant mod folders from JSON "
        "configuration. Each variant has scaled SFM coefficients.",
    )
    parser_build.add_argument(
        "--base-mod-root",
        type=Path,
        help="Path to base mod folder (default: repo root + base_mod_dir from JSON)",
    )
    parser_build.add_argument(
        "--variants-root",
        type=Path,
        default=Path("./fm_variants/mods"),
        help="Output directory for variant folders (default: ./fm_variants/mods)",
    )
    parser_build.add_argument(
        "--dcs-saved-games",
        type=Path,
        help="Path to DCS Saved Games folder for optional installation",
    )
    parser_build.add_argument(
        "--json-file",
        type=Path,
        default=Path("./fm_variants/mig17f_fm_variants.json"),
        help="Path to FM variants JSON (default: ./fm_variants/mig17f_fm_variants.json)",
    )
    parser_build.set_defaults(func=cmd_build_variants)


def add_run_test_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the run-test subcommand parser."""
    parser_run = subparsers.add_parser(
        "run-test",
        help="Run complete FM test workflow",
        description="Orchestrate a complete MiG-17F flight model test run: "
        "build variants, install mods, generate mission, run DCS, analyze results.",
    )
    parser_run.add_argument(
        "--dcs-path",
        type=Path,
        help="Path to DCS installation directory",
    )
    parser_run.add_argument(
        "--saved-games",
        type=Path,
        help="Path to DCS Saved Games directory",
    )
    parser_run.add_argument(
        "--timeout",
        type=int,
        default=runner.DEFAULT_TIMEOUT_S,
        help=f"Maximum time to wait for test completion (default: {runner.DEFAULT_TIMEOUT_S}s)",
    )
    parser_run.add_argument(
        "--variant-json",
        dest="variant_json",
        type=Path,
        help="Path to FM variants JSON file (default: ./fm_variants/mig17f_fm_variants.json)",
    )
    parser_run.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building FM variants (use existing)",
    )
    parser_run.add_argument(
        "--skip-launch",
        action="store_true",
        help="Skip launching DCS (assume already running)",
    )
    parser_run.add_argument(
        "--analyze-only",
        type=Path,
        metavar="LOG_FILE",
        help="Skip test execution, only analyze existing log file",
    )
    parser_run.set_defaults(func=cmd_run_test)


def add_generate_bfm_mission_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the generate-bfm-mission subcommand parser."""
    parser_bfm = subparsers.add_parser(
        "generate-bfm-mission",
        help="Generate BFM (dogfight) test mission",
        description="Generate a mission with BFM engagement scenarios to test "
        "the MiG-17F at the edge of its performance envelope.",
    )
    parser_bfm.add_argument(
        "--outfile",
        default=Path.home() / "Saved Games" / "DCS" / "Missions" / "MiG17F_BFM_Test.miz",
        type=Path,
        help="Path to output .miz file",
    )
    parser_bfm.add_argument(
        "--bfm-config",
        dest="bfm_config",
        default=Path.cwd() / "bfm_mission_tests.json",
        type=Path,
        help="Path to BFM test configuration JSON",
    )
    parser_bfm.add_argument(
        "--variant-json",
        dest="variant_json",
        default=Path.cwd() / "fm_variants" / "mig17f_fm_variants.json",
        type=Path,
        help="Path to FM variants JSON (enables multi-FM mode)",
    )
    parser_bfm.add_argument(
        "--type-name",
        dest="type_name",
        default="vwv_mig17f",
        help="MiG-17 DCS type name for single-FM mode",
    )
    parser_bfm.add_argument(
        "--max-priority",
        dest="max_priority",
        type=int,
        default=2,
        choices=[1, 2, 3],
        help="Maximum scenario priority (1=core, 2=standard, 3=all)",
    )
    parser_bfm.set_defaults(func=cmd_generate_bfm_mission)


def add_analyze_bfm_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the analyze-bfm subcommand parser."""
    parser_analyze = subparsers.add_parser(
        "analyze-bfm",
        help="Analyze TacView ACMI file for BFM metrics",
        description="Analyze a TacView ACMI file to extract BFM performance metrics "
        "and assess whether the MiG-17F is operating within expected envelope.",
    )
    parser_analyze.add_argument(
        "acmi_path",
        type=Path,
        help="Path to ACMI file (or 'latest' for most recent)",
    )
    parser_analyze.add_argument(
        "--bfm-config",
        dest="bfm_config",
        type=Path,
        default=Path.cwd() / "bfm_mission_tests.json",
        help="Path to BFM config for envelope targets",
    )
    parser_analyze.add_argument(
        "--output",
        type=Path,
        help="Path to write report (prints to stdout if not specified)",
    )
    parser_analyze.add_argument(
        "--csv",
        type=Path,
        help="Path to write CSV output",
    )
    parser_analyze.set_defaults(func=cmd_analyze_bfm)


def add_run_bfm_test_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the run-bfm-test subcommand parser."""
    parser_bfm_run = subparsers.add_parser(
        "run-bfm-test",
        help="Run complete BFM test workflow",
        description="Orchestrate a complete BFM test: build variants, generate mission, "
        "run DCS, capture TacView ACMI, and analyze results.",
    )
    parser_bfm_run.add_argument(
        "--dcs-path",
        type=Path,
        help="Path to DCS installation directory",
    )
    parser_bfm_run.add_argument(
        "--saved-games",
        type=Path,
        help="Path to DCS Saved Games directory",
    )
    parser_bfm_run.add_argument(
        "--timeout",
        type=int,
        default=bfm_runner.DEFAULT_TIMEOUT_S,
        help=f"Maximum wait time (default: {bfm_runner.DEFAULT_TIMEOUT_S}s)",
    )
    parser_bfm_run.add_argument(
        "--max-priority",
        dest="max_priority",
        type=int,
        default=2,
        choices=[1, 2, 3],
        help="Maximum scenario priority (1=core, 2=standard, 3=all)",
    )
    parser_bfm_run.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building FM variants",
    )
    parser_bfm_run.add_argument(
        "--skip-launch",
        action="store_true",
        help="Skip launching DCS",
    )
    parser_bfm_run.add_argument(
        "--analyze-only",
        type=str,
        metavar="ACMI_PATH",
        help="Skip test, only analyze ACMI ('latest' for most recent)",
    )
    parser_bfm_run.set_defaults(func=cmd_run_bfm_test)


def cmd_quick_bfm_setup(args: argparse.Namespace) -> int:
    """Handle the quick-bfm-setup subcommand.

    This command builds FM variants, generates a BFM mission, and installs
    everything into DCS so the user only needs to launch DCS and fly the mission.
    """
    repo_root = runner.find_repo_root()
    LOGGER.info("Repository root: %s", repo_root)

    # Resolve variant JSON path from config-dir or explicit argument
    variant_json: Optional[Path] = None

    if args.config_dir:
        config_dir = args.config_dir.resolve()
        if not config_dir.exists():
            LOGGER.error("Config directory not found: %s", config_dir)
            return 1
        if not config_dir.is_dir():
            LOGGER.error("Config path is not a directory: %s", config_dir)
            return 1

        # Look for flight_models.json in the config directory
        variant_json = config_dir / "flight_models.json"
        LOGGER.info("Using config directory: %s", config_dir)

    # Explicit --variant-json overrides --config-dir
    if args.variant_json:
        variant_json = args.variant_json.resolve()

    # Fall back to default if nothing specified
    if variant_json is None:
        variant_json = Path("./fm_variants/mig17f_fm_variants.json").resolve()

    # BFM config: use explicit argument, --4x flag, or default to standard F-4E merge scenario
    if args.bfm_config:
        bfm_config_path = args.bfm_config.resolve()
    elif getattr(args, "use_4x", False):
        bfm_config_path = repo_root / "tools" / "resources" / "flight_scenarios_f4e_merge_4x.json"
        LOGGER.info("Using 4x instances config")
    else:
        bfm_config_path = repo_root / "tools" / "resources" / "flight_scenarios_f4e_merge.json"

    if not variant_json.exists():
        LOGGER.error("Variant JSON not found: %s", variant_json)
        return 1

    if not bfm_config_path.exists():
        LOGGER.error("BFM config not found: %s", bfm_config_path)
        return 1

    # Detect DCS paths
    try:
        dcs_paths = runner.DCSPaths.detect(args.dcs_path, args.saved_games)
    except FileNotFoundError as e:
        LOGGER.error(str(e))
        return 1

    LOGGER.info("DCS Saved Games: %s", dcs_paths.saved_games)
    LOGGER.info("Variant JSON: %s", variant_json)
    LOGGER.info("BFM config: %s", bfm_config_path)

    # Step 1: Build and install FM variants
    LOGGER.info("=" * 60)
    LOGGER.info("Step 1: Building FM variant mods")
    LOGGER.info("=" * 60)

    json_config = builder.load_variant_config(variant_json)
    LOGGER.info("Found %d variants to build", len(json_config.variants))

    # Resolve base mod path
    base_mod_path = repo_root / json_config.base_mod_dir
    if not base_mod_path.exists():
        LOGGER.error("Base mod not found: %s", base_mod_path)
        return 1

    # Build variants
    variants_root = repo_root / "fm_variants" / "mods"
    variants_root.mkdir(parents=True, exist_ok=True)

    built_variants: list[Path] = []
    for variant in json_config.variants:
        LOGGER.info("Building variant: %s (%s)", variant.short_name, variant.variant_id)
        variant_path = builder.build_variant(base_mod_path, variant, variants_root)
        built_variants.append(variant_path)

    # Install variants to DCS
    LOGGER.info("Installing variants to DCS...")
    for variant_path in built_variants:
        builder.install_to_saved_games(variant_path, dcs_paths.saved_games)
        LOGGER.info("  Installed: %s", variant_path.name)

    # Step 2: Install base mod
    LOGGER.info("=" * 60)
    LOGGER.info("Step 2: Installing base MiG-17 mod")
    LOGGER.info("=" * 60)

    if not runner.install_base_mod(repo_root, dcs_paths):
        return 1

    # Step 3: Generate BFM mission
    LOGGER.info("=" * 60)
    LOGGER.info("Step 3: Generating BFM test mission")
    LOGGER.info("=" * 60)

    # Load BFM configuration
    bfm_config = bfm_generator.load_bfm_config(bfm_config_path)
    LOGGER.info("Loaded %d scenarios", len(bfm_config.scenarios))

    # Load variant descriptors for multi-FM mode
    variants = bfm_generator.load_variant_descriptors(variant_json)
    LOGGER.info("Multi-FM mode: %d variants", len(variants))

    # Build mission
    try:
        miz, groups, run_id = bfm_generator.build_bfm_mission(
            bfm_config,
            "multi_fm_mode",
            variants,
            max_priority=args.max_priority,
        )
    except Exception as exc:
        LOGGER.exception("Failed to build mission: %s", exc)
        return 2

    # Save mission to DCS Missions folder
    dcs_paths.missions_dir.mkdir(parents=True, exist_ok=True)
    mission_path = dcs_paths.missions_dir / "MiG17F_BFM_Test.miz"

    try:
        miz.save(mission_path)
    except Exception as exc:
        LOGGER.exception("Failed to save mission: %s", exc)
        return 3

    LOGGER.info("Mission saved to: %s", mission_path)

    # Summary
    LOGGER.info("")
    LOGGER.info("=" * 60)
    LOGGER.info("QUICK BFM SETUP COMPLETE")
    LOGGER.info("=" * 60)
    LOGGER.info("Variants installed: %d", len(built_variants))
    for path in built_variants:
        LOGGER.info("  - %s", path.name)
    LOGGER.info("Mission: %s", mission_path)
    LOGGER.info("Run ID: %s", run_id)
    LOGGER.info("Groups: %d", len(groups))
    LOGGER.info("")
    LOGGER.info("To run the test:")
    LOGGER.info("  1. Launch DCS")
    LOGGER.info("  2. Go to Mission Editor")
    LOGGER.info("  3. Load: MiG17F_BFM_Test.miz")
    LOGGER.info("  4. Click 'Fly' to start the mission")

    print(f"RUN_ID={run_id}")
    return 0


def add_quick_bfm_setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the quick-bfm-setup subcommand parser."""
    parser_quick = subparsers.add_parser(
        "quick-bfm-setup",
        help="Build variants and BFM mission, install to DCS (ready to fly)",
        description="Quick setup for BFM testing: builds FM variants from a JSON file, "
        "generates a BFM test mission, and installs everything to DCS. "
        "After running this command, just launch DCS and fly the mission.",
    )
    parser_quick.add_argument(
        "--config-dir",
        dest="config_dir",
        type=Path,
        help="Directory containing flight_models.json",
    )
    parser_quick.add_argument(
        "--variant-json",
        dest="variant_json",
        type=Path,
        help="Path to FM variants JSON file (overrides --config-dir)",
    )
    parser_quick.add_argument(
        "--bfm-config",
        dest="bfm_config",
        type=Path,
        help="Path to BFM scenarios JSON file (default: tools/resources/flight_scenarios_f4e_merge.json)",
    )
    parser_quick.add_argument(
        "--dcs-path",
        type=Path,
        help="Path to DCS installation directory",
    )
    parser_quick.add_argument(
        "--saved-games",
        type=Path,
        help="Path to DCS Saved Games directory",
    )
    parser_quick.add_argument(
        "--max-priority",
        dest="max_priority",
        type=int,
        default=3,
        choices=[1, 2, 3],
        help="Maximum scenario priority to include (1=core, 2=standard, 3=all)",
    )
    parser_quick.add_argument(
        "--4x",
        dest="use_4x",
        action="store_true",
        help="Use 4x instances config (4 copies of each scenario per variant)",
    )
    parser_quick.set_defaults(func=cmd_quick_bfm_setup)


def cmd_promote_variant(args: argparse.Namespace) -> int:
    """Handle the promote-variant subcommand.

    This command promotes a variant to become the new baseline mod by:
    1. Loading the variant definition from flight_models.json
    2. Copying the clean orig_mod as the base (preserves all identity fields)
    3. Applying ONLY the SFM coefficient scaling to mig17f.lua
    4. Updating ONLY display names (NOT identity fields like self_ID, update_id, etc.)
    5. Replacing the [VWV] MiG-17 directory with the promoted mod

    CRITICAL: The baseline mod must maintain these identity fields unchanged:
    - entry.lua: self_ID="tetet_mig17f", update_id="mig17f", LogBook.type="mig17f"
    - mig17f.lua: Name='vwv_mig17f', Shape="mig17f", username='mig17f'

    Only display fields can be modified:
    - entry.lua: displayName, fileMenuName
    - mig17f.lua: DisplayName
    """
    repo_root = runner.find_repo_root()
    LOGGER.info("Repository root: %s", repo_root)

    # Resolve variant JSON path
    variant_json: Optional[Path] = None

    if args.config_dir:
        config_dir = args.config_dir.resolve()
        if not config_dir.exists():
            LOGGER.error("Config directory not found: %s", config_dir)
            return 1
        variant_json = config_dir / "flight_models.json"
    elif args.variant_json:
        variant_json = args.variant_json.resolve()
    else:
        LOGGER.error("Must specify either --config-dir or --variant-json")
        return 1

    if not variant_json.exists():
        LOGGER.error("Variant JSON not found: %s", variant_json)
        return 1

    # Load variant configuration
    LOGGER.info("Loading variant configuration from: %s", variant_json)
    config = builder.load_variant_config(variant_json)

    # Find the specified variant
    source_variant: Optional[builder.Variant] = None
    for v in config.variants:
        if v.variant_id == args.variant_id:
            source_variant = v
            break

    if source_variant is None:
        LOGGER.error("Variant '%s' not found in %s", args.variant_id, variant_json)
        LOGGER.error("Available variants: %s", [v.variant_id for v in config.variants])
        return 1

    LOGGER.info("Found variant: %s (%s)", source_variant.variant_id, source_variant.short_name)
    LOGGER.info("  Scales: cx0=%.2f, polar=%.2f, pfor=%.2f",
                source_variant.scales.cx0,
                source_variant.scales.polar,
                source_variant.scales.pfor)

    # Use orig_mod as the clean reference source (not the potentially corrupted baseline)
    orig_mod_path = repo_root / "orig_mod" / "[VWV] MiG-17"
    if not orig_mod_path.exists():
        LOGGER.error("Original mod not found: %s", orig_mod_path)
        LOGGER.error("The orig_mod directory is required as the clean reference source")
        return 1

    # Determine the target mod path (the [VWV] MiG-17 directory to replace)
    base_mod_path = repo_root / config.base_mod_dir
    version_name = args.version
    display_name = f"[VWV] MiG-17F ({version_name})"

    # Build the new mod in a temporary location
    temp_build_dir = repo_root / "fm_variants" / "promoted"
    temp_build_dir.mkdir(parents=True, exist_ok=True)
    promoted_path = temp_build_dir / "[VWV] MiG-17"

    LOGGER.info("=" * 60)
    LOGGER.info("Building promoted variant: %s", display_name)
    LOGGER.info("=" * 60)

    # Remove any existing promoted folder
    if promoted_path.exists():
        LOGGER.info("Removing existing promoted folder: %s", promoted_path)
        shutil.rmtree(promoted_path)

    # Step 1: Copy the clean orig_mod (preserves all original identity fields)
    LOGGER.info("Copying clean original mod from: %s", orig_mod_path)
    shutil.copytree(orig_mod_path, promoted_path)

    # Step 2: Apply ONLY SFM coefficient scaling to mig17f.lua
    lua_path = promoted_path / "Database" / "mig17f.lua"
    if lua_path.exists():
        lua_content = lua_path.read_text(encoding="utf-8")

        # Apply SFM scaling functions (but NOT identity patching)
        lua_content = builder.scale_aero_table_data(lua_content, source_variant.scales)
        lua_content = builder.scale_engine_dcx_eng(lua_content, source_variant.scales)
        lua_content = builder.scale_engine_pfor(lua_content, source_variant.scales)
        lua_content = builder.patch_ny_max(lua_content, source_variant.scales)
        lua_content = builder.scale_flaps_maneuver(lua_content, source_variant.scales)

        # Update ONLY the DisplayName field (not Name, Shape, or username)
        display_pattern = re.compile(
            r"(DisplayName\s*=\s*_\(['\"])(.+?)(['\"])\)"
        )
        lua_content = display_pattern.sub(
            rf'\g<1>{display_name} "Fresco C"\g<3>)', lua_content, count=1
        )

        lua_path.write_text(lua_content, encoding="utf-8")
        LOGGER.info("Applied SFM scales and updated DisplayName in mig17f.lua")
    else:
        LOGGER.error("Database/mig17f.lua not found in: %s", promoted_path)
        return 1

    # Step 3: Update ONLY display fields in entry.lua (NOT identity fields)
    entry_path = promoted_path / "entry.lua"
    if entry_path.exists():
        entry_content = entry_path.read_text(encoding="utf-8")

        # Update displayName ONLY (shown in module manager)
        entry_content = re.sub(
            r'(displayName\s*=\s*_\(["\'])([^"\']+)(["\'])',
            rf'\g<1>{display_name}\g<3>',
            entry_content,
        )

        # Update fileMenuName ONLY (shown in file menus)
        entry_content = re.sub(
            r'(fileMenuName\s*=\s*_\(["\'])([^"\']+)(["\'])',
            rf'\g<1>{version_name} MiG-17F\g<3>',
            entry_content,
        )

        # NOTE: We intentionally do NOT modify:
        # - self_ID: must remain "tetet_mig17f" for livery/payload references
        # - update_id: must remain "mig17f" for update system
        # - LogBook.type: must remain "mig17f" for pilot logbook

        entry_path.write_text(entry_content, encoding="utf-8")
        LOGGER.info("Updated display fields in entry.lua (identity fields preserved)")
    else:
        LOGGER.warning("entry.lua not found in: %s", promoted_path)

    # Step 4: Replace the baseline mod directory
    LOGGER.info("=" * 60)
    LOGGER.info("Replacing baseline mod: %s", base_mod_path)
    LOGGER.info("=" * 60)

    # Remove the existing baseline mod completely
    if base_mod_path.exists():
        LOGGER.info("Removing existing baseline mod...")
        shutil.rmtree(base_mod_path)

    # Move the promoted variant to the baseline location
    LOGGER.info("Installing promoted variant as new baseline...")
    shutil.move(str(promoted_path), str(base_mod_path))

    # Clean up temp directory if empty
    if temp_build_dir.exists() and not any(temp_build_dir.iterdir()):
        temp_build_dir.rmdir()

    # Summary
    LOGGER.info("")
    LOGGER.info("=" * 60)
    LOGGER.info("PROMOTE VARIANT COMPLETE")
    LOGGER.info("=" * 60)
    LOGGER.info("Source variant: %s", source_variant.variant_id)
    LOGGER.info("New version: %s", version_name)
    LOGGER.info("Display name: %s", display_name)
    LOGGER.info("Installed to: %s", base_mod_path)
    LOGGER.info("")
    LOGGER.info("The baseline mod [VWV] MiG-17 has been updated with:")
    LOGGER.info("  - SFM scales from %s", source_variant.variant_id)
    LOGGER.info("  - Display name: %s", display_name)
    LOGGER.info("")
    LOGGER.info("Identity fields preserved (for liveries/payloads/logbook):")
    LOGGER.info("  - self_ID = 'tetet_mig17f'")
    LOGGER.info("  - update_id = 'mig17f'")
    LOGGER.info("  - LogBook.type = 'mig17f'")
    LOGGER.info("  - Name = 'vwv_mig17f'")
    LOGGER.info("  - Shape = 'mig17f'")

    return 0


def add_promote_variant_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the promote-variant subcommand parser."""
    parser_promote = subparsers.add_parser(
        "promote-variant",
        help="Promote a variant to become the new baseline mod",
        description="Promotes a tested variant to become the new baseline [VWV] MiG-17 mod. "
        "This applies the variant's SFM scales to the baseline mod and updates all "
        "identifiers to use the new version name.",
    )
    parser_promote.add_argument(
        "variant_id",
        type=str,
        help="Variant ID to promote (e.g., RC1_1_G6_FLAPS05)",
    )
    parser_promote.add_argument(
        "--version",
        type=str,
        required=True,
        help="Version name for the new baseline (e.g., RC2)",
    )
    parser_promote.add_argument(
        "--config-dir",
        dest="config_dir",
        type=Path,
        help="Directory containing flight_models.json",
    )
    parser_promote.add_argument(
        "--variant-json",
        dest="variant_json",
        type=Path,
        help="Path to FM variants JSON file (alternative to --config-dir)",
    )
    parser_promote.set_defaults(func=cmd_promote_variant)


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser with subcommands."""
    main_parser = argparse.ArgumentParser(
        prog="mig17_fm_tool",
        description="MiG-17F Flight Model Development Tool",
        epilog="Use '%(prog)s <command> --help' for more information on each command.",
    )
    main_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging",
    )

    subparsers = main_parser.add_subparsers(
        title="commands",
        dest="command",
        required=True,
        metavar="<command>",
    )

    add_generate_mission_parser(subparsers)
    add_parse_log_parser(subparsers)
    add_build_variants_parser(subparsers)
    add_run_test_parser(subparsers)
    add_generate_bfm_mission_parser(subparsers)
    add_analyze_bfm_parser(subparsers)
    add_run_bfm_test_parser(subparsers)
    add_quick_bfm_setup_parser(subparsers)
    add_promote_variant_parser(subparsers)

    return main_parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = "%(levelname)s: %(message)s"
    if args.command in ("run-test", "quick-bfm-setup"):
        log_format = "%(asctime)s %(levelname)s: %(message)s"

    logging.basicConfig(level=log_level, format=log_format, datefmt="%H:%M:%S")

    # Dispatch to the appropriate command handler
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
