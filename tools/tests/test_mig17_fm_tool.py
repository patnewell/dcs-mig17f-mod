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


class TestPromoteVariantCommand(unittest.TestCase):
    """Tests for promote-variant subcommand."""

    def test_required_arguments(self) -> None:
        """Variant ID and version are required."""
        parser = tool.create_parser()
        args = parser.parse_args([
            "promote-variant", "TEST_VARIANT",
            "--version", "RC2",
            "--config-dir", "/tmp/config",
        ])

        self.assertEqual("TEST_VARIANT", args.variant_id)
        self.assertEqual("RC2", args.version)
        self.assertEqual(Path("/tmp/config"), args.config_dir)

    def test_variant_json_argument(self) -> None:
        """Variant JSON argument is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args([
            "promote-variant", "MY_VARIANT",
            "--version", "RC3",
            "--variant-json", "/tmp/flight_models.json",
        ])

        self.assertEqual("MY_VARIANT", args.variant_id)
        self.assertEqual("RC3", args.version)
        self.assertEqual(Path("/tmp/flight_models.json"), args.variant_json)


class TestQuickBfmSetupCommand(unittest.TestCase):
    """Tests for quick-bfm-setup subcommand."""

    def test_default_arguments(self) -> None:
        """Default arguments are set correctly."""
        parser = tool.create_parser()
        args = parser.parse_args(["quick-bfm-setup"])

        self.assertIsNone(args.config_dir)
        self.assertIsNone(args.variant_json)
        self.assertIsNone(args.bfm_config)
        self.assertIsNone(args.dcs_path)
        self.assertIsNone(args.saved_games)
        self.assertEqual(3, args.max_priority)

    def test_config_dir_argument(self) -> None:
        """Config directory argument is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args([
            "quick-bfm-setup",
            "--config-dir", "/tmp/stage4_tuning",
        ])

        self.assertEqual(Path("/tmp/stage4_tuning"), args.config_dir)

    def test_variant_json_argument(self) -> None:
        """Variant JSON argument is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args([
            "quick-bfm-setup",
            "--variant-json", "/tmp/test_variants.json",
        ])

        self.assertEqual(Path("/tmp/test_variants.json"), args.variant_json)

    def test_bfm_config_argument(self) -> None:
        """BFM config argument is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args([
            "quick-bfm-setup",
            "--bfm-config", "/tmp/test_scenarios.json",
        ])

        self.assertEqual(Path("/tmp/test_scenarios.json"), args.bfm_config)

    def test_max_priority_argument(self) -> None:
        """Max priority argument is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args([
            "quick-bfm-setup",
            "--max-priority", "1",
        ])

        self.assertEqual(1, args.max_priority)

    def test_saved_games_argument(self) -> None:
        """Saved games argument is parsed correctly."""
        parser = tool.create_parser()
        args = parser.parse_args([
            "quick-bfm-setup",
            "--saved-games", "/c/Users/test/Saved Games/DCS",
        ])

        self.assertEqual(
            Path("/c/Users/test/Saved Games/DCS"),
            args.saved_games,
        )


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
        self.assertIn("quick-bfm-setup", result.stdout)
        self.assertIn("promote-variant", result.stdout)

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

    def test_quick_bfm_setup_help(self) -> None:
        """quick-bfm-setup help displays correctly."""
        result = subprocess.run(
            [sys.executable, "-m", "tools.mig17_fm_tool", "quick-bfm-setup", "--help"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )

        self.assertEqual(0, result.returncode)
        self.assertIn("usage:", result.stdout)
        self.assertIn("--variant-json", result.stdout)
        self.assertIn("--bfm-config", result.stdout)

    def test_quick_bfm_setup_missing_variant_json(self) -> None:
        """quick-bfm-setup fails gracefully with missing variant JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent_json = Path(tmpdir) / "nonexistent.json"
            saved_games = Path(tmpdir) / "SavedGames" / "DCS"
            saved_games.mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable, "-m", "tools.mig17_fm_tool",
                    "quick-bfm-setup",
                    "--variant-json", str(nonexistent_json),
                    "--saved-games", str(saved_games),
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )

            self.assertEqual(1, result.returncode)
            self.assertIn("not found", result.stderr)

    def test_quick_bfm_setup_missing_bfm_config(self) -> None:
        """quick-bfm-setup fails gracefully with missing BFM config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create minimal variant JSON
            variant_config = {
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
            variant_json = Path(tmpdir) / "variants.json"
            variant_json.write_text(json.dumps(variant_config))

            nonexistent_bfm = Path(tmpdir) / "nonexistent_bfm.json"
            saved_games = Path(tmpdir) / "SavedGames" / "DCS"
            saved_games.mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable, "-m", "tools.mig17_fm_tool",
                    "quick-bfm-setup",
                    "--variant-json", str(variant_json),
                    "--bfm-config", str(nonexistent_bfm),
                    "--saved-games", str(saved_games),
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )

            self.assertEqual(1, result.returncode)
            self.assertIn("not found", result.stderr)

    def test_quick_bfm_setup_e2e(self) -> None:
        """End-to-end test for quick-bfm-setup command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create minimal variant JSON
            variant_config = {
                "version": 1,
                "aircraft": {
                    "id": "vwv_mig17f",
                    "base_mod_dir": "[VWV] MiG-17",
                    "base_display_name": "[VWV] MiG-17F",
                },
                "variants": [
                    {
                        "variant_id": "E2E_TEST",
                        "short_name": "E2E",
                        "mod_dir_name": "[VWV] MiG-17_E2E",
                        "dcs_type_name": "vwv_mig17f_e2e",
                        "shape_username": "mig17f_e2e",
                        "display_name": "[VWV] MiG-17F E2E Test",
                        "scales": {"cx0": 1.0, "polar": 1.0, "engine_drag": 1.0, "pfor": 1.0},
                    }
                ],
            }
            variant_json = tmpdir_path / "variants.json"
            variant_json.write_text(json.dumps(variant_config))

            # Create minimal BFM config
            bfm_config = {
                "version": 1,
                "mission_settings": {
                    "duration_seconds": 60,
                    "test_group_spacing_nm": 20,
                    "origin": {"x": -100000, "y": -300000},
                },
                "flight_envelope_targets": {},
                "opponent_aircraft": [
                    {
                        "id": "f4e",
                        "dcs_type_name": "F-4E-45MC",
                        "display_name": "F-4E Phantom",
                        "group_prefix": "F4E",
                    }
                ],
                "engagement_geometries": [
                    {
                        "id": "head_on",
                        "name": "Head-On",
                        "description": "Head-on merge",
                        "mig17_heading_deg": 0,
                        "opponent_heading_deg": 180,
                        "initial_range_nm": 4.0,
                        "mig17_offset_deg": 0,
                    }
                ],
                "altitude_bands": [
                    {
                        "id": "low",
                        "name": "Low",
                        "altitude_ft": 1000,
                    }
                ],
                "initial_speeds": [
                    {
                        "id": "merge",
                        "name": "Merge Speed",
                        "speed_kt": 380,
                    }
                ],
                "test_scenarios": [
                    {
                        "id": "BFM_E2E_TEST",
                        "opponent": "f4e",
                        "geometry": "head_on",
                        "altitude": "low",
                        "speed": "merge",
                        "priority": 1,
                    }
                ],
            }
            bfm_json = tmpdir_path / "bfm_config.json"
            bfm_json.write_text(json.dumps(bfm_config))

            # Create mock DCS Saved Games structure
            saved_games = tmpdir_path / "SavedGames" / "DCS"
            saved_games.mkdir(parents=True)
            (saved_games / "Mods" / "aircraft").mkdir(parents=True)
            (saved_games / "Missions").mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable, "-m", "tools.mig17_fm_tool",
                    "quick-bfm-setup",
                    "--variant-json", str(variant_json),
                    "--bfm-config", str(bfm_json),
                    "--saved-games", str(saved_games),
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )

            self.assertEqual(0, result.returncode, result.stderr)

            # Verify variant was installed
            variant_dir = saved_games / "Mods" / "aircraft" / "[VWV] MiG-17_E2E"
            self.assertTrue(variant_dir.exists(), f"Variant not installed: {variant_dir}")

            # Verify Database/mig17f.lua was modified
            lua_file = variant_dir / "Database" / "mig17f.lua"
            self.assertTrue(lua_file.exists(), f"lua file not found: {lua_file}")
            lua_content = lua_file.read_text()
            self.assertIn("vwv_mig17f_e2e", lua_content)

            # Verify base mod was installed
            base_mod_dir = saved_games / "Mods" / "aircraft" / "[VWV] MiG-17"
            self.assertTrue(base_mod_dir.exists(), f"Base mod not installed: {base_mod_dir}")

            # Verify mission was created
            mission_file = saved_games / "Missions" / "MiG17F_BFM_Test.miz"
            self.assertTrue(mission_file.exists(), f"Mission not created: {mission_file}")

            # Verify RUN_ID was output
            self.assertIn("RUN_ID=", result.stdout)

            # Verify summary was logged
            self.assertIn("QUICK BFM SETUP COMPLETE", result.stderr)

    def test_quick_bfm_setup_config_dir_e2e(self) -> None:
        """End-to-end test for quick-bfm-setup with --config-dir.

        The --config-dir option only looks for flight_models.json.
        The BFM config defaults to tools/resources/flight_scenarios_f4e_merge.json.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create config directory with only flight_models.json
            config_dir = tmpdir_path / "stage4_tuning"
            config_dir.mkdir()

            # Create flight_models.json (variant config)
            variant_config = {
                "version": 1,
                "aircraft": {
                    "id": "vwv_mig17f",
                    "base_mod_dir": "[VWV] MiG-17",
                    "base_display_name": "[VWV] MiG-17F",
                },
                "variants": [
                    {
                        "variant_id": "DIR_TEST",
                        "short_name": "DIR",
                        "mod_dir_name": "[VWV] MiG-17_DIR",
                        "dcs_type_name": "vwv_mig17f_dir",
                        "shape_username": "mig17f_dir",
                        "display_name": "[VWV] MiG-17F Dir Test",
                        "scales": {"cx0": 1.0, "polar": 1.0, "engine_drag": 1.0, "pfor": 1.0},
                    }
                ],
            }
            (config_dir / "flight_models.json").write_text(json.dumps(variant_config))

            # No flight_profiles.json needed - uses default from tools/resources/

            # Create mock DCS Saved Games structure
            saved_games = tmpdir_path / "SavedGames" / "DCS"
            saved_games.mkdir(parents=True)
            (saved_games / "Mods" / "aircraft").mkdir(parents=True)
            (saved_games / "Missions").mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable, "-m", "tools.mig17_fm_tool",
                    "quick-bfm-setup",
                    "--config-dir", str(config_dir),
                    "--saved-games", str(saved_games),
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )

            self.assertEqual(0, result.returncode, result.stderr)

            # Verify variant was installed
            variant_dir = saved_games / "Mods" / "aircraft" / "[VWV] MiG-17_DIR"
            self.assertTrue(variant_dir.exists(), f"Variant not installed: {variant_dir}")

            # Verify Database/mig17f.lua was modified
            lua_file = variant_dir / "Database" / "mig17f.lua"
            self.assertTrue(lua_file.exists(), f"lua file not found: {lua_file}")
            lua_content = lua_file.read_text()
            self.assertIn("vwv_mig17f_dir", lua_content)

            # Verify mission was created
            mission_file = saved_games / "Missions" / "MiG17F_BFM_Test.miz"
            self.assertTrue(mission_file.exists(), f"Mission not created: {mission_file}")

            # Verify RUN_ID was output
            self.assertIn("RUN_ID=", result.stdout)


if __name__ == "__main__":
    unittest.main()
