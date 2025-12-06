"""Tests for the consolidated MiG-17 FM development tool."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import mig17_fm_tool as tool

ROOT = Path(__file__).resolve().parents[2]
MOD_ROOT = ROOT / "[VWV] MiG-17"


class TestCreateParser(unittest.TestCase):
    """Tests for create_parser function."""

    def test_creates_main_parser(self) -> None:
        """Creates a valid argument parser."""
        parser = tool.create_parser()
        self.assertIsNotNone(parser)

    def test_parser_has_subcommands(self) -> None:
        """Parser has all expected subcommands."""
        parser = tool.create_parser()
        # Test that parsing known subcommands works
        args = parser.parse_args(["generate-mission"])
        self.assertEqual("generate-mission", args.command)

        args = parser.parse_args(["parse-log"])
        self.assertEqual("parse-log", args.command)

        args = parser.parse_args(["build-variants"])
        self.assertEqual("build-variants", args.command)

        args = parser.parse_args(["run-test"])
        self.assertEqual("run-test", args.command)

    def test_verbose_flag(self) -> None:
        """Verbose flag is recognized."""
        parser = tool.create_parser()
        args = parser.parse_args(["-v", "parse-log"])
        self.assertTrue(args.verbose)

        args = parser.parse_args(["--verbose", "parse-log"])
        self.assertTrue(args.verbose)


class TestGenerateMissionCommand(unittest.TestCase):
    """Tests for generate-mission subcommand."""

    def test_default_arguments(self) -> None:
        """Default arguments are set correctly."""
        parser = tool.create_parser()
        args = parser.parse_args(["generate-mission"])

        self.assertIn("MiG17F_FM_Test.miz", str(args.outfile))
        self.assertIn("[VWV] MiG-17", str(args.mod_root))

    def test_custom_outfile(self) -> None:
        """Custom outfile path is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args(["generate-mission", "--outfile", "/tmp/test.miz"])

        self.assertEqual(Path("/tmp/test.miz"), args.outfile)

    def test_type_name_override(self) -> None:
        """Type name override is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args(["generate-mission", "--type-name", "custom_type"])

        self.assertEqual("custom_type", args.type_name)


class TestParseLogCommand(unittest.TestCase):
    """Tests for parse-log subcommand."""

    def test_default_arguments(self) -> None:
        """Default arguments are set correctly."""
        parser = tool.create_parser()
        args = parser.parse_args(["parse-log"])

        self.assertIsNone(args.log_file)
        self.assertIsNone(args.output)
        self.assertIsNone(args.csv)

    def test_log_file_argument(self) -> None:
        """Log file argument is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args(["parse-log", "--log-file", "/tmp/dcs.log"])

        self.assertEqual(Path("/tmp/dcs.log"), args.log_file)

    def test_output_and_csv_arguments(self) -> None:
        """Output and CSV arguments are parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args([
            "parse-log",
            "--output", "/tmp/report.txt",
            "--csv", "/tmp/results.csv",
        ])

        self.assertEqual(Path("/tmp/report.txt"), args.output)
        self.assertEqual(Path("/tmp/results.csv"), args.csv)


class TestBuildVariantsCommand(unittest.TestCase):
    """Tests for build-variants subcommand."""

    def test_default_arguments(self) -> None:
        """Default arguments are set correctly."""
        parser = tool.create_parser()
        args = parser.parse_args(["build-variants"])

        # Use Path comparison to be platform-agnostic
        self.assertEqual("mods", args.variants_root.name)
        self.assertEqual("fm_variants", args.variants_root.parent.name)
        self.assertEqual("mig17f_fm_variants.json", args.json_file.name)

    def test_dcs_saved_games_argument(self) -> None:
        """DCS saved games path is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args([
            "build-variants",
            "--dcs-saved-games", "/c/Users/test/Saved Games/DCS",
        ])

        self.assertEqual(
            Path("/c/Users/test/Saved Games/DCS"),
            args.dcs_saved_games,
        )


class TestRunTestCommand(unittest.TestCase):
    """Tests for run-test subcommand."""

    def test_default_arguments(self) -> None:
        """Default arguments are set correctly."""
        parser = tool.create_parser()
        args = parser.parse_args(["run-test"])

        self.assertIsNone(args.dcs_path)
        self.assertIsNone(args.saved_games)
        self.assertEqual(900, args.timeout)
        self.assertFalse(args.skip_build)
        self.assertFalse(args.skip_launch)
        self.assertIsNone(args.analyze_only)

    def test_skip_flags(self) -> None:
        """Skip flags are parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args(["run-test", "--skip-build", "--skip-launch"])

        self.assertTrue(args.skip_build)
        self.assertTrue(args.skip_launch)

    def test_analyze_only_argument(self) -> None:
        """Analyze-only argument is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args(["run-test", "--analyze-only", "/tmp/dcs.log"])

        self.assertEqual(Path("/tmp/dcs.log"), args.analyze_only)

    def test_timeout_argument(self) -> None:
        """Timeout argument is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args(["run-test", "--timeout", "1200"])

        self.assertEqual(1200, args.timeout)


class TestCLIIntegration(unittest.TestCase):
    """Integration tests for CLI execution."""

    def test_main_help(self) -> None:
        """Main help displays correctly."""
        result = subprocess.run(
            [sys.executable, "-m", "tools.mig17_fm_tool", "--help"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )

        self.assertEqual(0, result.returncode)
        self.assertIn("MiG-17F Flight Model Development Tool", result.stdout)
        self.assertIn("generate-mission", result.stdout)
        self.assertIn("parse-log", result.stdout)
        self.assertIn("build-variants", result.stdout)
        self.assertIn("run-test", result.stdout)

    def test_subcommand_help(self) -> None:
        """Subcommand help displays correctly."""
        for subcommand in ["generate-mission", "parse-log", "build-variants", "run-test"]:
            result = subprocess.run(
                [sys.executable, "-m", "tools.mig17_fm_tool", subcommand, "--help"],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            self.assertEqual(0, result.returncode, f"{subcommand} help failed")
            self.assertIn("usage:", result.stdout)

    def test_generate_mission_runs(self) -> None:
        """generate-mission subcommand runs successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = Path(tmpdir) / "test.miz"
            # Use non-existent variant JSON to force single-FM mode
            nonexistent_json = Path(tmpdir) / "nonexistent.json"

            result = subprocess.run(
                [
                    sys.executable, "-m", "tools.mig17_fm_tool",
                    "generate-mission",
                    "--outfile", str(outfile),
                    "--mod-root", str(MOD_ROOT),
                    "--variant-json", str(nonexistent_json),
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )

            self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            self.assertTrue(outfile.exists())
            self.assertIn("RUN_ID=", result.stdout)

    def test_parse_log_with_empty_log(self) -> None:
        """parse-log subcommand handles missing data gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "empty.log"
            log_file.write_text("No FM test data here\n")

            result = subprocess.run(
                [
                    sys.executable, "-m", "tools.mig17_fm_tool",
                    "parse-log",
                    "--log-file", str(log_file),
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )

            # Should return non-zero when no data found
            self.assertEqual(2, result.returncode)

    def test_parse_log_with_valid_data(self) -> None:
        """parse-log subcommand parses valid log data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            log_file.write_text(
                "[MIG17_FM_TEST] START,VMAX_SL,alt=1000,spd=400\n"
                "[MIG17_FM_TEST] VMAX,VMAX_SL,593.5,1000,0.893\n"
                "[MIG17_FM_TEST] SUMMARY,VMAX_SL,595.0,1100,500\n"
            )

            result = subprocess.run(
                [
                    sys.executable, "-m", "tools.mig17_fm_tool",
                    "parse-log",
                    "--log-file", str(log_file),
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("MiG-17F Flight Model Test Report", result.stdout)
            self.assertIn("VMAX_SL", result.stdout)

    def test_build_variants_missing_json(self) -> None:
        """build-variants fails gracefully with missing JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent_json = Path(tmpdir) / "nonexistent.json"

            result = subprocess.run(
                [
                    sys.executable, "-m", "tools.mig17_fm_tool",
                    "build-variants",
                    "--json-file", str(nonexistent_json),
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )

            self.assertEqual(1, result.returncode)

    def test_build_variants_runs(self) -> None:
        """build-variants subcommand runs successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create minimal test JSON
            config = {
                "version": 1,
                "aircraft": {
                    "id": "vwv_mig17f",
                    "base_mod_dir": "[VWV] MiG-17",
                    "base_display_name": "[VWV] MiG-17F",
                },
                "variants": [
                    {
                        "variant_id": "TEST",
                        "short_name": "TST",
                        "mod_dir_name": "[VWV] MiG-17_TEST",
                        "dcs_type_name": "vwv_mig17f_test",
                        "shape_username": "mig17f_test",
                        "display_name": "[VWV] MiG-17F TEST",
                        "scales": {"cx0": 1.0, "polar": 1.0, "engine_drag": 1.0, "pfor": 1.0},
                    }
                ],
            }
            json_file = Path(tmpdir) / "test.json"
            json_file.write_text(json.dumps(config))

            variants_root = Path(tmpdir) / "variants"

            result = subprocess.run(
                [
                    sys.executable, "-m", "tools.mig17_fm_tool",
                    "build-variants",
                    "--json-file", str(json_file),
                    "--base-mod-root", str(MOD_ROOT),
                    "--variants-root", str(variants_root),
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((variants_root / "[VWV] MiG-17_TEST").exists())


if __name__ == "__main__":
    unittest.main()
