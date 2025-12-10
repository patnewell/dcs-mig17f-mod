"""Orchestrate a complete MiG-17F flight model test run.

This script automates the entire FM testing workflow:
1. Generate mods for all flight model variants
2. Install mods to DCS (removing any existing duplicates)
3. Generate the test mission with a unique run ID
4. Launch DCS if not already running
5. Poll the DCS log for test completion
6. Copy log file to test_runs/ directory
7. Run analysis and output results

Usage:
    python tools/run_fm_test.py
    python tools/run_fm_test.py --dcs-path "C:/Program Files/Eagle Dynamics/DCS World"
    python tools/run_fm_test.py --timeout 900

The script requires DCS World to be installed and will use standard paths by default.
"""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)

# Test duration: mission runs for 600s, add buffer for startup
DEFAULT_TEST_DURATION_S = 600
DEFAULT_TIMEOUT_S = 900  # 15 minutes total timeout
LOG_POLL_INTERVAL_S = 5


@dataclass
class DCSPaths:
    """Resolved paths for DCS installation and saved games."""

    install_dir: Path
    saved_games: Path
    mods_dir: Path
    missions_dir: Path
    log_file: Path
    executable: Path

    @classmethod
    def detect(
        cls,
        install_dir: Optional[Path] = None,
        saved_games: Optional[Path] = None,
    ) -> "DCSPaths":
        """Detect DCS paths from standard locations.

        Args:
            install_dir: Override for DCS installation directory
            saved_games: Override for DCS Saved Games directory

        Returns:
            DCSPaths with all resolved paths

        Raises:
            FileNotFoundError: If DCS installation cannot be found
        """
        # Find DCS installation - prioritize Steam, then standalone
        if install_dir and install_dir.exists():
            dcs_install = install_dir
        else:
            # Steam installation paths (prioritized)
            steam_candidates = [
                Path("C:/Program Files (x86)/Steam/steamapps/common/DCSWorld"),
                Path("C:/Program Files/Steam/steamapps/common/DCSWorld"),
                Path("D:/Steam/steamapps/common/DCSWorld"),
                Path("D:/SteamLibrary/steamapps/common/DCSWorld"),
                Path("E:/SteamLibrary/steamapps/common/DCSWorld"),
            ]
            # Standalone installation paths (fallback)
            standalone_candidates = [
                Path("C:/Program Files/Eagle Dynamics/DCS World"),
                Path("C:/Program Files/Eagle Dynamics/DCS World OpenBeta"),
                Path("D:/DCS World"),
                Path("D:/DCS World OpenBeta"),
            ]

            dcs_install = None
            # Check Steam paths first
            for candidate in steam_candidates:
                exe_path = candidate / "bin" / "DCS.exe"
                if exe_path.exists():
                    dcs_install = candidate
                    break

            # Fall back to standalone if Steam not found
            if not dcs_install:
                for candidate in standalone_candidates:
                    exe_path = candidate / "bin" / "DCS.exe"
                    if exe_path.exists():
                        dcs_install = candidate
                        break

            if not dcs_install:
                msg = (
                    "Could not find DCS installation. "
                    "Use --dcs-path to specify location. "
                    "Checked Steam and standalone paths."
                )
                raise FileNotFoundError(msg)

        # Find Saved Games
        if saved_games and saved_games.exists():
            dcs_saved = saved_games
        else:
            home = Path.home()
            candidates = [
                home / "Saved Games" / "DCS",
                home / "Saved Games" / "DCS.openbeta",
            ]
            dcs_saved = None
            for candidate in candidates:
                if candidate.exists():
                    dcs_saved = candidate
                    break
            if not dcs_saved:
                # Create default if none exists
                dcs_saved = home / "Saved Games" / "DCS"
                dcs_saved.mkdir(parents=True, exist_ok=True)

        return cls(
            install_dir=dcs_install,
            saved_games=dcs_saved,
            mods_dir=dcs_saved / "Mods" / "aircraft",
            missions_dir=dcs_saved / "Missions",
            log_file=dcs_saved / "Logs" / "dcs.log",
            executable=dcs_install / "bin" / "DCS.exe",
        )


def find_repo_root() -> Path:
    """Find the repository root directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    # Fallback: assume we're in tools/
    return Path(__file__).resolve().parent.parent


def run_build_variants(
    repo_root: Path,
    dcs_paths: DCSPaths,
    variant_json: Optional[Path] = None,
) -> bool:
    """Build FM variant mods and install to DCS.

    Args:
        repo_root: Repository root directory
        dcs_paths: DCS paths configuration
        variant_json: Optional path to FM variants JSON file

    Returns:
        True if successful, False otherwise
    """
    LOGGER.info("=" * 60)
    LOGGER.info("Step 1: Building FM variant mods")
    LOGGER.info("=" * 60)

    build_script = repo_root / "tools" / "build_mig17f_variants_from_json.py"
    if not build_script.exists():
        LOGGER.error("Build script not found: %s", build_script)
        return False

    # Run the build script
    cmd = [
        sys.executable,
        str(build_script),
        "--dcs-saved-games",
        str(dcs_paths.saved_games),
    ]

    # Add custom variant JSON if specified
    if variant_json:
        cmd.extend(["--json-file", str(variant_json)])
        LOGGER.info("Using custom variant JSON: %s", variant_json)

    LOGGER.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)

    if result.returncode != 0:
        LOGGER.error("Build failed with code %d", result.returncode)
        LOGGER.error("stderr: %s", result.stderr)
        return False

    LOGGER.info("Build output:\n%s", result.stdout)
    return True


def install_base_mod(repo_root: Path, dcs_paths: DCSPaths) -> bool:
    """Install the base MiG-17 mod to DCS.

    Args:
        repo_root: Repository root directory
        dcs_paths: DCS paths configuration

    Returns:
        True if successful, False otherwise
    """
    LOGGER.info("=" * 60)
    LOGGER.info("Step 2: Installing base MiG-17 mod")
    LOGGER.info("=" * 60)

    base_mod = repo_root / "[VWV] MiG-17"
    if not base_mod.exists():
        LOGGER.error("Base mod not found: %s", base_mod)
        return False

    # Ensure mods directory exists
    dcs_paths.mods_dir.mkdir(parents=True, exist_ok=True)

    # Remove existing and copy
    dest = dcs_paths.mods_dir / "[VWV] MiG-17"
    if dest.exists():
        LOGGER.info("Removing existing mod: %s", dest)
        shutil.rmtree(dest)

    LOGGER.info("Installing to: %s", dest)
    shutil.copytree(base_mod, dest)

    return True


def generate_mission(
    repo_root: Path,
    dcs_paths: DCSPaths,
    variant_json: Optional[Path] = None,
) -> Optional[str]:
    """Generate the test mission and return the run ID.

    Args:
        repo_root: Repository root directory
        dcs_paths: DCS paths configuration
        variant_json: Optional path to FM variants JSON file

    Returns:
        Run ID string if successful, None otherwise
    """
    LOGGER.info("=" * 60)
    LOGGER.info("Step 3: Generating test mission")
    LOGGER.info("=" * 60)

    gen_script = repo_root / "tools" / "generate_mig17_fm_test_mission.py"
    if not gen_script.exists():
        LOGGER.error("Generator script not found: %s", gen_script)
        return None

    # Ensure missions directory exists
    dcs_paths.missions_dir.mkdir(parents=True, exist_ok=True)

    outfile = dcs_paths.missions_dir / "MiG17F_FM_Test.miz"

    cmd = [
        sys.executable,
        str(gen_script),
        "--outfile",
        str(outfile),
    ]

    # Add custom variant JSON if specified
    if variant_json:
        cmd.extend(["--variant-json", str(variant_json)])
        LOGGER.info("Using custom variant JSON: %s", variant_json)

    LOGGER.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)

    if result.returncode != 0:
        LOGGER.error("Mission generation failed with code %d", result.returncode)
        LOGGER.error("stderr: %s", result.stderr)
        return None

    LOGGER.info("Generator output:\n%s", result.stdout)

    # Extract run ID from output
    run_id = None
    for line in result.stdout.splitlines():
        if line.startswith("RUN_ID="):
            run_id = line.split("=", 1)[1].strip()
            break

    if not run_id:
        LOGGER.error("Could not extract run ID from generator output")
        return None

    LOGGER.info("Mission generated with Run ID: %s", run_id)
    return run_id


def is_dcs_running() -> bool:
    """Check if DCS is currently running."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq DCS.exe"],
            capture_output=True,
            text=True,
        )
        return "DCS.exe" in result.stdout
    except Exception:
        return False


def launch_dcs(dcs_paths: DCSPaths) -> bool:
    """Launch DCS if not already running.

    Args:
        dcs_paths: DCS paths configuration

    Returns:
        True if DCS is running (launched or already running)
    """
    LOGGER.info("=" * 60)
    LOGGER.info("Step 4: Launching DCS")
    LOGGER.info("=" * 60)

    if is_dcs_running():
        LOGGER.info("DCS is already running")
        return True

    if not dcs_paths.executable.exists():
        LOGGER.error("DCS executable not found: %s", dcs_paths.executable)
        return False

    LOGGER.info("Starting DCS: %s", dcs_paths.executable)

    # Launch DCS (non-blocking)
    subprocess.Popen(
        [str(dcs_paths.executable)],
        cwd=dcs_paths.install_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for DCS to start
    LOGGER.info("Waiting for DCS to start...")
    for _ in range(60):  # Wait up to 60 seconds
        time.sleep(1)
        if is_dcs_running():
            LOGGER.info("DCS started successfully")
            return True

    LOGGER.error("Timeout waiting for DCS to start")
    return False


def wait_for_test_completion(
    dcs_paths: DCSPaths,
    run_id: str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> bool:
    """Poll the DCS log file waiting for test completion.

    Args:
        dcs_paths: DCS paths configuration
        run_id: The run ID to look for
        timeout_s: Maximum time to wait in seconds

    Returns:
        True if test completed, False if timeout or error
    """
    LOGGER.info("=" * 60)
    LOGGER.info("Step 5: Waiting for test completion")
    LOGGER.info("=" * 60)

    LOGGER.info("Run ID: %s", run_id)
    LOGGER.info("Timeout: %d seconds", timeout_s)
    LOGGER.info("Polling log file: %s", dcs_paths.log_file)

    start_marker = f"[MIG17_FM_TEST] RUN_START,{run_id}"
    end_marker = f"[MIG17_FM_TEST] RUN_END,{run_id}"

    start_time = time.time()
    found_start = False

    LOGGER.info("Waiting for mission to start (marker: RUN_START,%s)...", run_id)
    LOGGER.info(
        "NOTE: Load the mission 'MiG17F_FM_Test.miz' in DCS Mission Editor and fly it"
    )

    while time.time() - start_time < timeout_s:
        if not dcs_paths.log_file.exists():
            time.sleep(LOG_POLL_INTERVAL_S)
            continue

        try:
            content = dcs_paths.log_file.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            LOGGER.warning("Error reading log file: %s", e)
            time.sleep(LOG_POLL_INTERVAL_S)
            continue

        if not found_start:
            if start_marker in content:
                found_start = True
                elapsed = time.time() - start_time
                LOGGER.info("Mission started! (%.1fs elapsed)", elapsed)
                LOGGER.info(
                    "Test will run for ~%d seconds...", DEFAULT_TEST_DURATION_S
                )

        if found_start and end_marker in content:
            elapsed = time.time() - start_time
            LOGGER.info("Test completed! (%.1fs total)", elapsed)
            return True

        # Show progress
        if found_start:
            elapsed = time.time() - start_time
            remaining = timeout_s - elapsed
            LOGGER.info(
                "Waiting for completion... (%.0fs elapsed, %.0fs remaining)",
                elapsed,
                remaining,
            )

        time.sleep(LOG_POLL_INTERVAL_S)

    LOGGER.error("Timeout waiting for test completion")
    if not found_start:
        LOGGER.error("Mission never started - did you load and fly the mission?")
    return False


def copy_log_to_test_runs(
    dcs_paths: DCSPaths,
    repo_root: Path,
    run_id: str,
) -> Optional[Path]:
    """Copy the DCS log to the test_runs directory.

    Args:
        dcs_paths: DCS paths configuration
        repo_root: Repository root directory
        run_id: The run ID for naming

    Returns:
        Path to the copied log file, or None on error
    """
    LOGGER.info("=" * 60)
    LOGGER.info("Step 6: Archiving test data")
    LOGGER.info("=" * 60)

    if not dcs_paths.log_file.exists():
        LOGGER.error("Log file not found: %s", dcs_paths.log_file)
        return None

    # Create test_runs directory with timestamp and run_id
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = repo_root / "test_runs" / f"{timestamp}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Copy log file
    dest_log = run_dir / "dcs.log"
    LOGGER.info("Copying log to: %s", dest_log)
    shutil.copy2(dcs_paths.log_file, dest_log)

    # Write run metadata
    metadata = run_dir / "run_info.txt"
    metadata.write_text(
        f"Run ID: {run_id}\n"
        f"Timestamp: {timestamp}\n"
        f"Source log: {dcs_paths.log_file}\n",
        encoding="utf-8",
    )

    LOGGER.info("Test data archived to: %s", run_dir)
    return dest_log


def run_analysis(
    repo_root: Path,
    log_file: Path,
    run_dir: Path,
) -> bool:
    """Run the log analysis script and output results.

    Args:
        repo_root: Repository root directory
        log_file: Path to the log file to analyze
        run_dir: Directory to save the report

    Returns:
        True if successful, False otherwise
    """
    LOGGER.info("=" * 60)
    LOGGER.info("Step 7: Analyzing results")
    LOGGER.info("=" * 60)

    parse_script = repo_root / "tools" / "parse_fm_test_log.py"
    if not parse_script.exists():
        LOGGER.error("Parser script not found: %s", parse_script)
        return False

    report_file = run_dir / "fm_test_report.txt"
    csv_file = run_dir / "fm_test_results.csv"

    cmd = [
        sys.executable,
        str(parse_script),
        "--log-file",
        str(log_file),
        "--output",
        str(report_file),
        "--csv",
        str(csv_file),
    ]

    LOGGER.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)

    if result.returncode != 0:
        LOGGER.error("Analysis failed with code %d", result.returncode)
        LOGGER.error("stderr: %s", result.stderr)
        return False

    LOGGER.info("Parser output:\n%s", result.stdout)
    LOGGER.info("Report saved to: %s", report_file)
    LOGGER.info("CSV saved to: %s", csv_file)

    # Print report to stdout
    print("\n" + "=" * 70)
    print("FLIGHT MODEL TEST REPORT")
    print("=" * 70)
    if report_file.exists():
        print(report_file.read_text(encoding="utf-8"))
    else:
        LOGGER.warning("Report file not found")

    return True


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Orchestrate a complete MiG-17F flight model test run"
    )
    parser.add_argument(
        "--dcs-path",
        type=Path,
        help="Path to DCS installation directory",
    )
    parser.add_argument(
        "--saved-games",
        type=Path,
        help="Path to DCS Saved Games directory",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=f"Maximum time to wait for test completion (default: {DEFAULT_TIMEOUT_S}s)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building FM variants (use existing)",
    )
    parser.add_argument(
        "--skip-launch",
        action="store_true",
        help="Skip launching DCS (assume already running)",
    )
    parser.add_argument(
        "--analyze-only",
        type=Path,
        metavar="LOG_FILE",
        help="Skip test execution, only analyze existing log file",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    args = parse_args()
    repo_root = find_repo_root()

    LOGGER.info("Repository root: %s", repo_root)

    # Handle analyze-only mode
    if args.analyze_only:
        LOGGER.info("Analyze-only mode: %s", args.analyze_only)
        if not args.analyze_only.exists():
            LOGGER.error("Log file not found: %s", args.analyze_only)
            return 1

        # Create a temporary run directory for analysis output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = repo_root / "test_runs" / f"{timestamp}_analysis"
        run_dir.mkdir(parents=True, exist_ok=True)

        # Copy the log file
        dest_log = run_dir / "dcs.log"
        shutil.copy2(args.analyze_only, dest_log)

        if not run_analysis(repo_root, dest_log, run_dir):
            return 1
        return 0

    # Detect DCS paths
    try:
        dcs_paths = DCSPaths.detect(args.dcs_path, args.saved_games)
    except FileNotFoundError as e:
        LOGGER.error(str(e))
        return 1

    LOGGER.info("DCS installation: %s", dcs_paths.install_dir)
    LOGGER.info("DCS Saved Games: %s", dcs_paths.saved_games)

    # Step 1: Build FM variants
    if not args.skip_build:
        if not run_build_variants(repo_root, dcs_paths):
            return 1

    # Step 2: Install base mod
    if not install_base_mod(repo_root, dcs_paths):
        return 1

    # Step 3: Generate mission
    run_id = generate_mission(repo_root, dcs_paths)
    if not run_id:
        return 1

    # Step 4: Launch DCS
    if not args.skip_launch:
        if not launch_dcs(dcs_paths):
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

    if not wait_for_test_completion(dcs_paths, run_id, args.timeout):
        LOGGER.error("Test did not complete successfully")
        return 1

    # Step 6: Archive test data
    archived_log = copy_log_to_test_runs(dcs_paths, repo_root, run_id)
    if not archived_log:
        return 1

    run_dir = archived_log.parent

    # Step 7: Run analysis
    if not run_analysis(repo_root, archived_log, run_dir):
        return 1

    LOGGER.info("")
    LOGGER.info("=" * 60)
    LOGGER.info("TEST RUN COMPLETE")
    LOGGER.info("=" * 60)
    LOGGER.info("Run ID: %s", run_id)
    LOGGER.info("Results: %s", run_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
