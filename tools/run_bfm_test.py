"""Orchestrate a complete BFM test run for MiG-17F flight model validation.

This script automates the entire BFM testing workflow:
1. Build FM variant mods (if configured)
2. Install mods to DCS
3. Generate the BFM test mission
4. Launch DCS if not running
5. Wait for the mission to complete
6. Find and process the TacView ACMI file
7. Analyze results and generate report

Usage:
    python tools/run_bfm_test.py
    python tools/run_bfm_test.py --analyze-only latest
    python tools/run_bfm_test.py --analyze-only path/to/file.acmi
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)

# Test timing
DEFAULT_TEST_DURATION_S = 600  # 10 minutes for BFM scenarios
DEFAULT_TIMEOUT_S = 900  # 15 minutes total
LOG_POLL_INTERVAL_S = 5
ACMI_POLL_INTERVAL_S = 10
ACMI_SETTLE_TIME_S = 30  # Wait for file to finish writing


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
        """Detect DCS paths from standard locations."""
        # Find DCS installation
        if install_dir and install_dir.exists():
            dcs_install = install_dir
        else:
            steam_candidates = [
                Path("C:/Program Files (x86)/Steam/steamapps/common/DCSWorld"),
                Path("C:/Program Files/Steam/steamapps/common/DCSWorld"),
                Path("D:/Steam/steamapps/common/DCSWorld"),
                Path("D:/SteamLibrary/steamapps/common/DCSWorld"),
                Path("E:/SteamLibrary/steamapps/common/DCSWorld"),
            ]
            standalone_candidates = [
                Path("C:/Program Files/Eagle Dynamics/DCS World"),
                Path("C:/Program Files/Eagle Dynamics/DCS World OpenBeta"),
                Path("D:/DCS World"),
            ]

            dcs_install = None
            for candidate in steam_candidates + standalone_candidates:
                exe_path = candidate / "bin" / "DCS.exe"
                if exe_path.exists():
                    dcs_install = candidate
                    break

            if not dcs_install:
                msg = "Could not find DCS installation. Use --dcs-path."
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
    return Path(__file__).resolve().parent.parent


def get_tacview_dir() -> Path:
    """Get the TacView output directory."""
    return Path.home() / "Documents" / "Tacview"


def find_latest_acmi(tacview_dir: Path, after_time: Optional[datetime] = None) -> Optional[Path]:
    """Find the most recent ACMI file in the TacView directory.

    Args:
        tacview_dir: Path to TacView directory
        after_time: Only consider files modified after this time

    Returns:
        Path to the latest ACMI file, or None if not found
    """
    if not tacview_dir.exists():
        return None

    acmi_files = list(tacview_dir.glob("*.acmi"))
    if not acmi_files:
        return None

    # Filter by modification time if specified
    if after_time:
        acmi_files = [
            f for f in acmi_files
            if datetime.fromtimestamp(f.stat().st_mtime) > after_time
        ]
        if not acmi_files:
            return None

    # Sort by modification time, newest first
    acmi_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return acmi_files[0]


def run_build_variants(repo_root: Path, dcs_paths: DCSPaths) -> bool:
    """Build FM variant mods and install to DCS."""
    LOGGER.info("=" * 60)
    LOGGER.info("Step 1: Building FM variant mods")
    LOGGER.info("=" * 60)

    build_script = repo_root / "tools" / "build_mig17f_variants_from_json.py"
    if not build_script.exists():
        LOGGER.warning("Build script not found: %s", build_script)
        LOGGER.warning("Skipping variant build - using existing mods")
        return True

    cmd = [
        sys.executable,
        str(build_script),
        "--dcs-saved-games",
        str(dcs_paths.saved_games),
    ]

    LOGGER.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)

    if result.returncode != 0:
        LOGGER.error("Build failed with code %d", result.returncode)
        LOGGER.error("stderr: %s", result.stderr)
        return False

    LOGGER.info("Build output:\n%s", result.stdout)
    return True


def install_base_mod(repo_root: Path, dcs_paths: DCSPaths) -> bool:
    """Install the base MiG-17 mod to DCS."""
    LOGGER.info("=" * 60)
    LOGGER.info("Step 2: Installing base MiG-17 mod")
    LOGGER.info("=" * 60)

    base_mod = repo_root / "[VWV] MiG-17"
    if not base_mod.exists():
        LOGGER.error("Base mod not found: %s", base_mod)
        return False

    dcs_paths.mods_dir.mkdir(parents=True, exist_ok=True)

    dest = dcs_paths.mods_dir / "[VWV] MiG-17"
    if dest.exists():
        LOGGER.info("Removing existing mod: %s", dest)
        shutil.rmtree(dest)

    LOGGER.info("Installing to: %s", dest)
    shutil.copytree(base_mod, dest)

    return True


def generate_bfm_mission(repo_root: Path, dcs_paths: DCSPaths, max_priority: int = 2) -> Optional[str]:
    """Generate the BFM test mission and return the run ID."""
    LOGGER.info("=" * 60)
    LOGGER.info("Step 3: Generating BFM test mission")
    LOGGER.info("=" * 60)

    gen_script = repo_root / "tools" / "generate_bfm_test_mission.py"
    if not gen_script.exists():
        LOGGER.error("Generator script not found: %s", gen_script)
        return None

    dcs_paths.missions_dir.mkdir(parents=True, exist_ok=True)
    outfile = dcs_paths.missions_dir / "MiG17F_BFM_Test.miz"

    cmd = [
        sys.executable,
        str(gen_script),
        "--outfile",
        str(outfile),
        "--max-priority",
        str(max_priority),
    ]

    LOGGER.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)

    if result.returncode != 0:
        LOGGER.error("Mission generation failed with code %d", result.returncode)
        LOGGER.error("stderr: %s", result.stderr)
        return None

    LOGGER.info("Generator output:\n%s", result.stdout)

    # Extract run ID
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
    """Launch DCS if not already running."""
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

    subprocess.Popen(
        [str(dcs_paths.executable)],
        cwd=dcs_paths.install_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    LOGGER.info("Waiting for DCS to start...")
    for _ in range(60):
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
    """Poll the DCS log for test completion markers."""
    LOGGER.info("=" * 60)
    LOGGER.info("Step 5: Waiting for test completion")
    LOGGER.info("=" * 60)

    LOGGER.info("Run ID: %s", run_id)
    LOGGER.info("Timeout: %d seconds", timeout_s)

    start_marker = f"[BFM_TEST] RUN_START,{run_id}"
    end_marker = f"[BFM_TEST] RUN_END,{run_id}"

    start_time = time.time()
    found_start = False

    LOGGER.info("Waiting for mission to start...")
    LOGGER.info("NOTE: Load 'MiG17F_BFM_Test.miz' in DCS and fly the mission")

    while time.time() - start_time < timeout_s:
        if not dcs_paths.log_file.exists():
            time.sleep(LOG_POLL_INTERVAL_S)
            continue

        try:
            content = dcs_paths.log_file.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            LOGGER.warning("Error reading log: %s", e)
            time.sleep(LOG_POLL_INTERVAL_S)
            continue

        if not found_start and start_marker in content:
            found_start = True
            elapsed = time.time() - start_time
            LOGGER.info("Mission started! (%.1fs elapsed)", elapsed)
            LOGGER.info("Test will run for ~%d seconds...", DEFAULT_TEST_DURATION_S)

        if found_start and end_marker in content:
            elapsed = time.time() - start_time
            LOGGER.info("Test completed! (%.1fs total)", elapsed)
            return True

        if found_start:
            elapsed = time.time() - start_time
            remaining = timeout_s - elapsed
            LOGGER.info("Waiting... (%.0fs elapsed, %.0fs remaining)", elapsed, remaining)

        time.sleep(LOG_POLL_INTERVAL_S)

    LOGGER.error("Timeout waiting for test completion")
    return False


def wait_for_acmi_file(
    mission_start_time: datetime,
    timeout_s: int = 120,
) -> Optional[Path]:
    """Wait for a new ACMI file to appear after mission start.

    Args:
        mission_start_time: Time when the mission started
        timeout_s: Maximum time to wait

    Returns:
        Path to the ACMI file, or None if timeout
    """
    LOGGER.info("=" * 60)
    LOGGER.info("Step 6: Waiting for TacView ACMI file")
    LOGGER.info("=" * 60)

    tacview_dir = get_tacview_dir()
    if not tacview_dir.exists():
        LOGGER.error("TacView directory not found: %s", tacview_dir)
        return None

    LOGGER.info("Monitoring: %s", tacview_dir)
    LOGGER.info("Looking for files created after: %s", mission_start_time)

    start_time = time.time()

    while time.time() - start_time < timeout_s:
        latest = find_latest_acmi(tacview_dir, after_time=mission_start_time)

        if latest:
            # Wait for file to settle (stop being written)
            LOGGER.info("Found ACMI file: %s", latest.name)
            LOGGER.info("Waiting %d seconds for file to settle...", ACMI_SETTLE_TIME_S)
            time.sleep(ACMI_SETTLE_TIME_S)

            # Verify file is stable
            initial_size = latest.stat().st_size
            time.sleep(5)
            final_size = latest.stat().st_size

            if final_size == initial_size:
                LOGGER.info("ACMI file ready: %s (%.1f MB)", latest.name, final_size / 1024 / 1024)
                return latest

            LOGGER.info("File still being written, waiting...")

        time.sleep(ACMI_POLL_INTERVAL_S)

    LOGGER.error("Timeout waiting for ACMI file")
    return None


def copy_acmi_to_test_runs(
    acmi_path: Path,
    repo_root: Path,
    run_id: str,
) -> Path:
    """Copy ACMI file to test_runs directory.

    Args:
        acmi_path: Path to source ACMI file
        repo_root: Repository root
        run_id: Test run ID

    Returns:
        Path to the copied file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = repo_root / "test_runs" / f"{timestamp}_{run_id}_bfm"
    run_dir.mkdir(parents=True, exist_ok=True)

    dest_acmi = run_dir / acmi_path.name
    LOGGER.info("Copying ACMI to: %s", dest_acmi)
    shutil.copy2(acmi_path, dest_acmi)

    # Write run metadata
    metadata = run_dir / "run_info.txt"
    metadata.write_text(
        f"Run ID: {run_id}\n"
        f"Timestamp: {timestamp}\n"
        f"Type: BFM Test\n"
        f"Source ACMI: {acmi_path}\n",
        encoding="utf-8",
    )

    return dest_acmi


def run_analysis(
    repo_root: Path,
    acmi_path: Path,
    run_dir: Path,
) -> bool:
    """Run the ACMI analysis and generate report.

    Args:
        repo_root: Repository root
        acmi_path: Path to ACMI file
        run_dir: Directory for output files

    Returns:
        True if successful
    """
    LOGGER.info("=" * 60)
    LOGGER.info("Step 7: Analyzing ACMI data")
    LOGGER.info("=" * 60)

    analyze_script = repo_root / "tools" / "bfm_acmi_analyzer.py"
    if not analyze_script.exists():
        LOGGER.error("Analyzer script not found: %s", analyze_script)
        return False

    bfm_config = repo_root / "bfm_mission_tests.json"
    report_file = run_dir / "bfm_test_report.txt"
    csv_file = run_dir / "bfm_test_results.csv"

    cmd = [
        sys.executable,
        str(analyze_script),
        str(acmi_path),
        "--output",
        str(report_file),
        "--csv",
        str(csv_file),
    ]

    if bfm_config.exists():
        cmd.extend(["--bfm-config", str(bfm_config)])

    LOGGER.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)

    if result.returncode != 0:
        LOGGER.error("Analysis failed with code %d", result.returncode)
        LOGGER.error("stderr: %s", result.stderr)
        return False

    LOGGER.info("Analysis output:\n%s", result.stdout)
    LOGGER.info("Report saved to: %s", report_file)
    LOGGER.info("CSV saved to: %s", csv_file)

    # Print report
    print("\n" + "=" * 70)
    print("BFM TEST REPORT")
    print("=" * 70)
    if report_file.exists():
        print(report_file.read_text(encoding="utf-8"))

    return True


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Orchestrate BFM test run for MiG-17F"
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
        help=f"Maximum wait time in seconds (default: {DEFAULT_TIMEOUT_S})",
    )
    parser.add_argument(
        "--max-priority",
        type=int,
        default=2,
        choices=[1, 2, 3],
        help="Maximum scenario priority (1=core, 2=standard, 3=all)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building FM variants",
    )
    parser.add_argument(
        "--skip-launch",
        action="store_true",
        help="Skip launching DCS",
    )
    parser.add_argument(
        "--analyze-only",
        type=str,
        metavar="ACMI_PATH",
        help="Skip test, only analyze ACMI file ('latest' for most recent)",
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
        if args.analyze_only.lower() == "latest":
            tacview_dir = get_tacview_dir()
            acmi_path = find_latest_acmi(tacview_dir)
            if not acmi_path:
                LOGGER.error("No ACMI files found in %s", tacview_dir)
                return 1
            LOGGER.info("Using latest ACMI: %s", acmi_path)
        else:
            acmi_path = Path(args.analyze_only)
            if not acmi_path.exists():
                LOGGER.error("ACMI file not found: %s", acmi_path)
                return 1

        # Create run directory for analysis output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = repo_root / "test_runs" / f"{timestamp}_bfm_analysis"
        run_dir.mkdir(parents=True, exist_ok=True)

        dest_acmi = run_dir / acmi_path.name
        shutil.copy2(acmi_path, dest_acmi)

        if not run_analysis(repo_root, dest_acmi, run_dir):
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

    # Step 1: Build variants
    if not args.skip_build:
        if not run_build_variants(repo_root, dcs_paths):
            return 1

    # Step 2: Install base mod
    if not install_base_mod(repo_root, dcs_paths):
        return 1

    # Step 3: Generate mission
    run_id = generate_bfm_mission(repo_root, dcs_paths, args.max_priority)
    if not run_id:
        return 1

    # Step 4: Launch DCS
    if not args.skip_launch:
        if not launch_dcs(dcs_paths):
            return 1

    # Instructions for user
    LOGGER.info("")
    LOGGER.info("*" * 60)
    LOGGER.info("ACTION REQUIRED:")
    LOGGER.info("  1. In DCS, go to Mission Editor")
    LOGGER.info("  2. Load: %s", dcs_paths.missions_dir / "MiG17F_BFM_Test.miz")
    LOGGER.info("  3. Click 'Fly' to start the mission")
    LOGGER.info("  4. Wait for the BFM scenarios to complete (~10 minutes)")
    LOGGER.info("  5. TacView will automatically capture the ACMI data")
    LOGGER.info("*" * 60)
    LOGGER.info("")

    # Record mission start time
    mission_start_time = datetime.now()

    # Step 5: Wait for test completion
    if not wait_for_test_completion(dcs_paths, run_id, args.timeout):
        LOGGER.warning("Test completion markers not found, proceeding anyway...")

    # Step 6: Wait for ACMI file
    acmi_path = wait_for_acmi_file(mission_start_time)
    if not acmi_path:
        LOGGER.error("No ACMI file found - ensure TacView is running in DCS")
        return 1

    # Copy to test_runs
    run_dir = repo_root / "test_runs" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{run_id}_bfm"
    run_dir.mkdir(parents=True, exist_ok=True)
    dest_acmi = copy_acmi_to_test_runs(acmi_path, repo_root, run_id)
    run_dir = dest_acmi.parent

    # Step 7: Analyze
    if not run_analysis(repo_root, dest_acmi, run_dir):
        return 1

    LOGGER.info("")
    LOGGER.info("=" * 60)
    LOGGER.info("BFM TEST RUN COMPLETE")
    LOGGER.info("=" * 60)
    LOGGER.info("Run ID: %s", run_id)
    LOGGER.info("Results: %s", run_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
