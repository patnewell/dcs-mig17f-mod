"""Tests for the MiG-17 FM test orchestration script."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import run_fm_test as runner


class TestDCSPaths(unittest.TestCase):
    """Tests for DCSPaths dataclass."""

    def test_dataclass_creation(self) -> None:
        """DCSPaths can be created with all fields."""
        paths = runner.DCSPaths(
            install_dir=Path("C:/DCS"),
            saved_games=Path("C:/Users/test/Saved Games/DCS"),
            mods_dir=Path("C:/Users/test/Saved Games/DCS/Mods/aircraft"),
            missions_dir=Path("C:/Users/test/Saved Games/DCS/Missions"),
            log_file=Path("C:/Users/test/Saved Games/DCS/Logs/dcs.log"),
            executable=Path("C:/DCS/bin/DCS.exe"),
        )
        self.assertEqual(Path("C:/DCS"), paths.install_dir)
        self.assertEqual(Path("C:/DCS/bin/DCS.exe"), paths.executable)

    def test_detect_with_explicit_paths(self) -> None:
        """Detect returns paths when explicitly provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create mock DCS structure
            install_dir = tmpdir_path / "DCS"
            install_dir.mkdir()
            (install_dir / "bin").mkdir()
            (install_dir / "bin" / "DCS.exe").touch()

            saved_games = tmpdir_path / "Saved Games" / "DCS"
            saved_games.mkdir(parents=True)

            paths = runner.DCSPaths.detect(
                install_dir=install_dir,
                saved_games=saved_games,
            )

            self.assertEqual(install_dir, paths.install_dir)
            self.assertEqual(saved_games, paths.saved_games)
            self.assertEqual(saved_games / "Mods" / "aircraft", paths.mods_dir)
            self.assertEqual(saved_games / "Missions", paths.missions_dir)
            self.assertEqual(saved_games / "Logs" / "dcs.log", paths.log_file)
            self.assertEqual(install_dir / "bin" / "DCS.exe", paths.executable)


class TestFindRepoRoot(unittest.TestCase):
    """Tests for find_repo_root function."""

    def test_finds_repo_root(self) -> None:
        """Finds repository root from script location."""
        root = runner.find_repo_root()
        # Should contain .git directory or be a parent of tools/
        self.assertTrue(
            (root / ".git").exists() or (root / "tools").exists(),
            f"Expected repo root, got {root}",
        )


class TestConstants(unittest.TestCase):
    """Tests for module constants."""

    def test_default_timeout(self) -> None:
        """Default timeout is reasonable."""
        self.assertEqual(900, runner.DEFAULT_TIMEOUT_S)

    def test_log_poll_interval(self) -> None:
        """Log poll interval is reasonable."""
        self.assertEqual(5, runner.LOG_POLL_INTERVAL_S)

    def test_test_duration(self) -> None:
        """Test duration constant is set."""
        self.assertEqual(600, runner.DEFAULT_TEST_DURATION_S)


class TestCopyLogToTestRuns(unittest.TestCase):
    """Tests for copy_log_to_test_runs function."""

    def test_copies_log_file(self) -> None:
        """Log file is copied to test_runs directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create mock log file
            log_dir = tmpdir_path / "Logs"
            log_dir.mkdir()
            log_file = log_dir / "dcs.log"
            log_file.write_text("[MIG17_FM_TEST] test data\n")

            # Create mock DCS paths
            dcs_paths = runner.DCSPaths(
                install_dir=tmpdir_path / "DCS",
                saved_games=tmpdir_path,
                mods_dir=tmpdir_path / "Mods" / "aircraft",
                missions_dir=tmpdir_path / "Missions",
                log_file=log_file,
                executable=tmpdir_path / "DCS" / "bin" / "DCS.exe",
            )

            repo_root = tmpdir_path / "repo"
            repo_root.mkdir()

            result = runner.copy_log_to_test_runs(
                dcs_paths, repo_root, "test_run_123"
            )

            self.assertIsNotNone(result)
            self.assertTrue(result.exists())
            self.assertEqual("dcs.log", result.name)
            self.assertIn("test_run_123", str(result.parent))

            # Check metadata file was created
            metadata = result.parent / "run_info.txt"
            self.assertTrue(metadata.exists())
            metadata_content = metadata.read_text()
            self.assertIn("test_run_123", metadata_content)

    def test_returns_none_if_log_missing(self) -> None:
        """Returns None if log file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            dcs_paths = runner.DCSPaths(
                install_dir=tmpdir_path / "DCS",
                saved_games=tmpdir_path,
                mods_dir=tmpdir_path / "Mods" / "aircraft",
                missions_dir=tmpdir_path / "Missions",
                log_file=tmpdir_path / "Logs" / "dcs.log",  # Does not exist
                executable=tmpdir_path / "DCS" / "bin" / "DCS.exe",
            )

            result = runner.copy_log_to_test_runs(
                dcs_paths, tmpdir_path, "test_run_123"
            )
            self.assertIsNone(result)


class TestIsDcsRunning(unittest.TestCase):
    """Tests for is_dcs_running function."""

    @mock.patch("subprocess.run")
    def test_returns_true_when_running(self, mock_run: mock.Mock) -> None:
        """Returns True when DCS.exe is in tasklist."""
        mock_run.return_value = mock.Mock(
            stdout="Image Name                     PID Session Name\n"
            "DCS.exe                       1234 Console\n"
        )
        self.assertTrue(runner.is_dcs_running())

    @mock.patch("subprocess.run")
    def test_returns_false_when_not_running(self, mock_run: mock.Mock) -> None:
        """Returns False when DCS.exe is not in tasklist."""
        mock_run.return_value = mock.Mock(
            stdout="INFO: No tasks are running which match the specified criteria.\n"
        )
        self.assertFalse(runner.is_dcs_running())

    @mock.patch("subprocess.run")
    def test_returns_false_on_error(self, mock_run: mock.Mock) -> None:
        """Returns False when subprocess raises exception."""
        mock_run.side_effect = Exception("Process error")
        self.assertFalse(runner.is_dcs_running())


class TestInstallBaseMod(unittest.TestCase):
    """Tests for install_base_mod function."""

    def test_installs_base_mod(self) -> None:
        """Base mod is copied to mods directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create mock repo with base mod
            repo_root = tmpdir_path / "repo"
            repo_root.mkdir()
            base_mod = repo_root / "[VWV] MiG-17"
            base_mod.mkdir()
            (base_mod / "entry.lua").write_text("-- entry")
            (base_mod / "Database").mkdir()
            (base_mod / "Database" / "mig17f.lua").write_text("-- db")

            # Create mock DCS paths
            mods_dir = tmpdir_path / "DCS" / "Mods" / "aircraft"
            mods_dir.mkdir(parents=True)

            dcs_paths = runner.DCSPaths(
                install_dir=tmpdir_path / "DCS",
                saved_games=tmpdir_path / "DCS",
                mods_dir=mods_dir,
                missions_dir=tmpdir_path / "DCS" / "Missions",
                log_file=tmpdir_path / "DCS" / "Logs" / "dcs.log",
                executable=tmpdir_path / "DCS" / "bin" / "DCS.exe",
            )

            result = runner.install_base_mod(repo_root, dcs_paths)

            self.assertTrue(result)
            installed = mods_dir / "[VWV] MiG-17"
            self.assertTrue(installed.exists())
            self.assertTrue((installed / "entry.lua").exists())

    def test_removes_existing_installation(self) -> None:
        """Existing installation is removed before new install."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create mock repo with base mod
            repo_root = tmpdir_path / "repo"
            repo_root.mkdir()
            base_mod = repo_root / "[VWV] MiG-17"
            base_mod.mkdir()
            (base_mod / "new.lua").write_text("-- new")

            # Create existing installation
            mods_dir = tmpdir_path / "DCS" / "Mods" / "aircraft"
            existing = mods_dir / "[VWV] MiG-17"
            existing.mkdir(parents=True)
            (existing / "old.lua").write_text("-- old")

            dcs_paths = runner.DCSPaths(
                install_dir=tmpdir_path / "DCS",
                saved_games=tmpdir_path / "DCS",
                mods_dir=mods_dir,
                missions_dir=tmpdir_path / "DCS" / "Missions",
                log_file=tmpdir_path / "DCS" / "Logs" / "dcs.log",
                executable=tmpdir_path / "DCS" / "bin" / "DCS.exe",
            )

            result = runner.install_base_mod(repo_root, dcs_paths)

            self.assertTrue(result)
            installed = mods_dir / "[VWV] MiG-17"
            self.assertTrue((installed / "new.lua").exists())
            self.assertFalse((installed / "old.lua").exists())

    def test_returns_false_if_base_mod_missing(self) -> None:
        """Returns False if base mod doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            repo_root = tmpdir_path / "repo"
            repo_root.mkdir()
            # No base mod created

            dcs_paths = runner.DCSPaths(
                install_dir=tmpdir_path / "DCS",
                saved_games=tmpdir_path / "DCS",
                mods_dir=tmpdir_path / "DCS" / "Mods" / "aircraft",
                missions_dir=tmpdir_path / "DCS" / "Missions",
                log_file=tmpdir_path / "DCS" / "Logs" / "dcs.log",
                executable=tmpdir_path / "DCS" / "bin" / "DCS.exe",
            )

            result = runner.install_base_mod(repo_root, dcs_paths)
            self.assertFalse(result)


class TestWaitForTestCompletion(unittest.TestCase):
    """Tests for wait_for_test_completion function."""

    def test_detects_completion(self) -> None:
        """Detects test completion from log markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create log file with start and end markers
            log_file = tmpdir_path / "dcs.log"
            log_file.write_text(
                "[MIG17_FM_TEST] RUN_START,test123\n"
                "[MIG17_FM_TEST] DATA,...\n"
                "[MIG17_FM_TEST] RUN_END,test123\n"
            )

            dcs_paths = runner.DCSPaths(
                install_dir=tmpdir_path / "DCS",
                saved_games=tmpdir_path,
                mods_dir=tmpdir_path / "Mods" / "aircraft",
                missions_dir=tmpdir_path / "Missions",
                log_file=log_file,
                executable=tmpdir_path / "DCS" / "bin" / "DCS.exe",
            )

            # Short timeout since log already has markers
            result = runner.wait_for_test_completion(dcs_paths, "test123", timeout_s=1)
            self.assertTrue(result)

    def test_timeout_without_start(self) -> None:
        """Returns False if mission never starts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create log file without markers
            log_file = tmpdir_path / "dcs.log"
            log_file.write_text("Some other log content\n")

            dcs_paths = runner.DCSPaths(
                install_dir=tmpdir_path / "DCS",
                saved_games=tmpdir_path,
                mods_dir=tmpdir_path / "Mods" / "aircraft",
                missions_dir=tmpdir_path / "Missions",
                log_file=log_file,
                executable=tmpdir_path / "DCS" / "bin" / "DCS.exe",
            )

            result = runner.wait_for_test_completion(dcs_paths, "test123", timeout_s=1)
            self.assertFalse(result)


class TestRunBuildVariants(unittest.TestCase):
    """Tests for run_build_variants function."""

    @mock.patch("subprocess.run")
    def test_runs_build_script(self, mock_run: mock.Mock) -> None:
        """Build script is invoked with correct arguments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create mock build script
            tools_dir = tmpdir_path / "tools"
            tools_dir.mkdir()
            build_script = tools_dir / "build_mig17f_variants_from_json.py"
            build_script.write_text("# build script")

            mock_run.return_value = mock.Mock(returncode=0, stdout="Built variants", stderr="")

            dcs_paths = runner.DCSPaths(
                install_dir=tmpdir_path / "DCS",
                saved_games=tmpdir_path / "SavedGames",
                mods_dir=tmpdir_path / "SavedGames" / "Mods" / "aircraft",
                missions_dir=tmpdir_path / "SavedGames" / "Missions",
                log_file=tmpdir_path / "SavedGames" / "Logs" / "dcs.log",
                executable=tmpdir_path / "DCS" / "bin" / "DCS.exe",
            )

            result = runner.run_build_variants(tmpdir_path, dcs_paths)

            self.assertTrue(result)
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            self.assertIn("build_mig17f_variants_from_json.py", str(call_args))

    @mock.patch("subprocess.run")
    def test_returns_false_on_failure(self, mock_run: mock.Mock) -> None:
        """Returns False if build script fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            tools_dir = tmpdir_path / "tools"
            tools_dir.mkdir()
            build_script = tools_dir / "build_mig17f_variants_from_json.py"
            build_script.write_text("# build script")

            mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="Error")

            dcs_paths = runner.DCSPaths(
                install_dir=tmpdir_path / "DCS",
                saved_games=tmpdir_path / "SavedGames",
                mods_dir=tmpdir_path / "SavedGames" / "Mods" / "aircraft",
                missions_dir=tmpdir_path / "SavedGames" / "Missions",
                log_file=tmpdir_path / "SavedGames" / "Logs" / "dcs.log",
                executable=tmpdir_path / "DCS" / "bin" / "DCS.exe",
            )

            result = runner.run_build_variants(tmpdir_path, dcs_paths)
            self.assertFalse(result)


class TestGenerateMission(unittest.TestCase):
    """Tests for generate_mission function."""

    @mock.patch("subprocess.run")
    def test_extracts_run_id(self, mock_run: mock.Mock) -> None:
        """Run ID is extracted from generator output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            tools_dir = tmpdir_path / "tools"
            tools_dir.mkdir()
            gen_script = tools_dir / "generate_mig17_fm_test_mission.py"
            gen_script.write_text("# generator script")

            mock_run.return_value = mock.Mock(
                returncode=0,
                stdout="Mission generated\nRUN_ID=abc123def456\n",
                stderr="",
            )

            missions_dir = tmpdir_path / "SavedGames" / "Missions"
            missions_dir.mkdir(parents=True)

            dcs_paths = runner.DCSPaths(
                install_dir=tmpdir_path / "DCS",
                saved_games=tmpdir_path / "SavedGames",
                mods_dir=tmpdir_path / "SavedGames" / "Mods" / "aircraft",
                missions_dir=missions_dir,
                log_file=tmpdir_path / "SavedGames" / "Logs" / "dcs.log",
                executable=tmpdir_path / "DCS" / "bin" / "DCS.exe",
            )

            run_id = runner.generate_mission(tmpdir_path, dcs_paths)

            self.assertEqual("abc123def456", run_id)

    @mock.patch("subprocess.run")
    def test_returns_none_on_failure(self, mock_run: mock.Mock) -> None:
        """Returns None if generator fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            tools_dir = tmpdir_path / "tools"
            tools_dir.mkdir()
            gen_script = tools_dir / "generate_mig17_fm_test_mission.py"
            gen_script.write_text("# generator script")

            mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="Error")

            dcs_paths = runner.DCSPaths(
                install_dir=tmpdir_path / "DCS",
                saved_games=tmpdir_path / "SavedGames",
                mods_dir=tmpdir_path / "SavedGames" / "Mods" / "aircraft",
                missions_dir=tmpdir_path / "SavedGames" / "Missions",
                log_file=tmpdir_path / "SavedGames" / "Logs" / "dcs.log",
                executable=tmpdir_path / "DCS" / "bin" / "DCS.exe",
            )

            run_id = runner.generate_mission(tmpdir_path, dcs_paths)
            self.assertIsNone(run_id)


class TestRunAnalysis(unittest.TestCase):
    """Tests for run_analysis function."""

    @mock.patch("subprocess.run")
    def test_runs_parser_script(self, mock_run: mock.Mock) -> None:
        """Parser script is invoked with correct arguments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            tools_dir = tmpdir_path / "tools"
            tools_dir.mkdir()
            parse_script = tools_dir / "parse_fm_test_log.py"
            parse_script.write_text("# parser script")

            log_file = tmpdir_path / "dcs.log"
            log_file.write_text("log content")

            run_dir = tmpdir_path / "run_dir"
            run_dir.mkdir()

            mock_run.return_value = mock.Mock(returncode=0, stdout="Analysis complete", stderr="")

            result = runner.run_analysis(tmpdir_path, log_file, run_dir)

            self.assertTrue(result)
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            self.assertIn("parse_fm_test_log.py", str(call_args))


if __name__ == "__main__":
    unittest.main()
