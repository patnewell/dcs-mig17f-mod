#!/usr/bin/env python3
"""MiG-17F Flight Model Development Tool.

This is the main entry point for all MiG-17F flight model development tasks.
It provides subcommands for mission generation, log parsing, variant building,
and orchestrating complete test runs.

Usage:
    python tools/mig17_fm_tool.py <command> [options]

Commands:
    generate-mission  Generate FM test mission (.miz file)
    parse-log         Parse DCS log for test results
    build-variants    Build FM variant mods from JSON configuration
    run-test          Run complete FM test workflow (build, install, test, analyze)

Examples:
    # Generate a test mission
    python tools/mig17_fm_tool.py generate-mission --outfile mission.miz

    # Parse test results from DCS log
    python tools/mig17_fm_tool.py parse-log --csv results.csv

    # Build FM variant mods
    python tools/mig17_fm_tool.py build-variants --dcs-saved-games "C:/Users/.../DCS"

    # Run complete test workflow
    python tools/mig17_fm_tool.py run-test --timeout 900
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

# Import the individual modules
from tools import (
    build_mig17f_variants_from_json as builder,
    generate_mig17_fm_test_mission as generator,
    parse_fm_test_log as parser,
    run_fm_test as runner,
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

    # Step 1: Build FM variants
    if not args.skip_build:
        if not runner.run_build_variants(repo_root, dcs_paths):
            return 1

    # Step 2: Install base mod
    if not runner.install_base_mod(repo_root, dcs_paths):
        return 1

    # Step 3: Generate mission
    run_id = runner.generate_mission(repo_root, dcs_paths)
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

    return main_parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = "%(levelname)s: %(message)s"
    if args.command == "run-test":
        log_format = "%(asctime)s %(levelname)s: %(message)s"

    logging.basicConfig(level=log_level, format=log_format, datefmt="%H:%M:%S")

    # Dispatch to the appropriate command handler
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
