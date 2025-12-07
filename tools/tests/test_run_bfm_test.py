"""Tests for the BFM test runner."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from tools import run_bfm_test as runner


class TestConstants(unittest.TestCase):
    """Tests for module constants."""

    def test_default_timeout(self) -> None:
        """Default timeout is reasonable."""
        self.assertGreaterEqual(runner.DEFAULT_TIMEOUT_S, 600)
        self.assertLessEqual(runner.DEFAULT_TIMEOUT_S, 3600)

    def test_poll_interval(self) -> None:
        """Poll interval is reasonable."""
        self.assertGreaterEqual(runner.LOG_POLL_INTERVAL_S, 1)
        self.assertLessEqual(runner.LOG_POLL_INTERVAL_S, 30)


class TestDCSPaths(unittest.TestCase):
    """Tests for DCSPaths dataclass."""

    def test_creation(self) -> None:
        """DCSPaths can be created."""
        paths = runner.DCSPaths(
            install_dir=Path("C:/DCS"),
            saved_games=Path("C:/Users/test/Saved Games/DCS"),
            mods_dir=Path("C:/Users/test/Saved Games/DCS/Mods/aircraft"),
            missions_dir=Path("C:/Users/test/Saved Games/DCS/Missions"),
            log_file=Path("C:/Users/test/Saved Games/DCS/Logs/dcs.log"),
            executable=Path("C:/DCS/bin/DCS.exe"),
        )
        self.assertEqual(Path("C:/DCS"), paths.install_dir)


class TestFindRepoRoot(unittest.TestCase):
    """Tests for find_repo_root function."""

    def test_finds_repo_root(self) -> None:
        """Finds repository root from tools directory."""
        root = runner.find_repo_root()
        self.assertTrue(root.exists())
        # Should contain tools directory
        self.assertTrue((root / "tools").exists())


class TestGetTacviewDir(unittest.TestCase):
    """Tests for get_tacview_dir function."""

    def test_returns_documents_tacview(self) -> None:
        """Returns ~/Documents/Tacview path."""
        tacview_dir = runner.get_tacview_dir()
        self.assertEqual("Tacview", tacview_dir.name)
        self.assertIn("Documents", str(tacview_dir))


class TestFindLatestAcmi(unittest.TestCase):
    """Tests for find_latest_acmi function."""

    def test_finds_latest_file(self) -> None:
        """Finds the most recent ACMI file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            file1 = Path(tmpdir) / "test1.acmi"
            file2 = Path(tmpdir) / "test2.acmi"
            file1.write_text("content1")
            file2.write_text("content2")

            # Make file2 newer
            import time
            time.sleep(0.1)
            file2.write_text("content2_updated")

            result = runner.find_latest_acmi(Path(tmpdir))

        self.assertIsNotNone(result)
        self.assertEqual("test2.acmi", result.name)

    def test_returns_none_for_empty_dir(self) -> None:
        """Returns None for directory with no ACMI files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.find_latest_acmi(Path(tmpdir))
        self.assertIsNone(result)

    def test_returns_none_for_missing_dir(self) -> None:
        """Returns None for non-existent directory."""
        result = runner.find_latest_acmi(Path("/nonexistent/path"))
        self.assertIsNone(result)

    def test_filters_by_time(self) -> None:
        """Filters files by modification time."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create old file
            old_file = Path(tmpdir) / "old.acmi"
            old_file.write_text("old content")

            # Record time
            after_time = datetime.now() + timedelta(seconds=1)

            # File created before after_time should not be found
            result = runner.find_latest_acmi(Path(tmpdir), after_time=after_time)
            self.assertIsNone(result)


class TestCopyAcmiToTestRuns(unittest.TestCase):
    """Tests for copy_acmi_to_test_runs function."""

    def test_copies_file(self) -> None:
        """Copies ACMI file to test_runs directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create source ACMI
            acmi = tmpdir / "source.acmi"
            acmi.write_text("test content")

            # Create repo root with test_runs
            repo = tmpdir / "repo"
            repo.mkdir()

            result = runner.copy_acmi_to_test_runs(acmi, repo, "test123")

            # Check within the tempdir context (before cleanup)
            self.assertTrue(result.exists())
            self.assertEqual("source.acmi", result.name)
            self.assertIn("test123", str(result.parent))
            self.assertIn("bfm", str(result.parent))


class TestParseArgs(unittest.TestCase):
    """Tests for parse_args function."""

    def test_default_args(self) -> None:
        """Default arguments are set."""
        with mock.patch("sys.argv", ["run_bfm_test.py"]):
            args = runner.parse_args()

        self.assertEqual(runner.DEFAULT_TIMEOUT_S, args.timeout)
        self.assertEqual(2, args.max_priority)
        self.assertFalse(args.skip_build)
        self.assertFalse(args.skip_launch)
        self.assertIsNone(args.analyze_only)

    def test_analyze_only(self) -> None:
        """--analyze-only argument is parsed."""
        with mock.patch("sys.argv", ["run_bfm_test.py", "--analyze-only", "latest"]):
            args = runner.parse_args()

        self.assertEqual("latest", args.analyze_only)

    def test_max_priority(self) -> None:
        """--max-priority argument is parsed."""
        with mock.patch("sys.argv", ["run_bfm_test.py", "--max-priority", "3"]):
            args = runner.parse_args()

        self.assertEqual(3, args.max_priority)

    def test_skip_flags(self) -> None:
        """Skip flags are parsed."""
        with mock.patch(
            "sys.argv",
            ["run_bfm_test.py", "--skip-build", "--skip-launch"],
        ):
            args = runner.parse_args()

        self.assertTrue(args.skip_build)
        self.assertTrue(args.skip_launch)


if __name__ == "__main__":
    unittest.main()
