"""Tests for the MiG-17 FM test mission generator."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from dcs import mission as dcs_mission
from dcs import task as dcs_task

from tools import generate_mig17_fm_test_mission as gen

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "tools" / "generate_mig17_fm_test_mission.py"
MOD_ROOT = ROOT / "[VWV] MiG-17"

# Current expected groups in single-FM mode
EXPECTED_GROUPS_SINGLE_FM = [
    "ACCEL_SL",
    "ACCEL_10K",
    "ACCEL_20K",
    "CLIMB_SL",
    "CLIMB_10K",
    "TURN_10K_300",
    "TURN_10K_350",
    "TURN_10K_400",
    "DECEL_10K",
    "VMAX_SL",
    "VMAX_10K",
    "CEILING_AB_FULL",
    "CLIMB_10K_AB_FULL",
    "VMAX_SL_100F",
    "VMAX_SL_25F",
    "VMAX_10K_MIL",
    "DECEL_SL",
    "DECEL_10K_IDLE",
]


class TestConversionConstants(unittest.TestCase):
    """Tests for conversion constants."""

    def test_ft_to_meters(self) -> None:
        """FT_TO_METERS constant is correct."""
        self.assertAlmostEqual(0.3048, gen.FT_TO_METERS, places=4)

    def test_kts_to_mps(self) -> None:
        """KTS_TO_MPS constant is correct."""
        self.assertAlmostEqual(0.514444, gen.KTS_TO_MPS, places=4)

    def test_nm_to_meters(self) -> None:
        """NM_TO_METERS constant is correct."""
        self.assertEqual(1852.0, gen.NM_TO_METERS)


class TestMig17Constants(unittest.TestCase):
    """Tests for MiG-17 aircraft constants."""

    def test_empty_weight(self) -> None:
        """Empty weight constant is correct."""
        self.assertEqual(3920, gen.MIG17_EMPTY_KG)

    def test_nominal_weight(self) -> None:
        """Nominal weight constant is correct."""
        self.assertEqual(5345, gen.MIG17_NOMINAL_KG)

    def test_max_weight(self) -> None:
        """Max weight constant is correct."""
        self.assertEqual(6075, gen.MIG17_MAX_KG)

    def test_fuel_max(self) -> None:
        """Fuel max constant is correct."""
        self.assertEqual(1140, gen.MIG17_FUEL_MAX_KG)

    def test_default_fuel_fraction(self) -> None:
        """Default fuel fraction is 50%."""
        self.assertEqual(0.50, gen.MIG17_FUEL_FRACTION_DEFAULT)


class TestVariantDescriptor(unittest.TestCase):
    """Tests for VariantDescriptor dataclass."""

    def test_creation(self) -> None:
        """VariantDescriptor can be created with all fields."""
        desc = gen.VariantDescriptor(
            short_name="FM0",
            mod_dir_name="[VWV] MiG-17_FM0",
            dcs_type_name="vwv_mig17f_fm0",
        )
        self.assertEqual("FM0", desc.short_name)
        self.assertEqual("[VWV] MiG-17_FM0", desc.mod_dir_name)
        self.assertEqual("vwv_mig17f_fm0", desc.dcs_type_name)

    def test_frozen(self) -> None:
        """VariantDescriptor is frozen."""
        desc = gen.VariantDescriptor(
            short_name="FM0",
            mod_dir_name="[VWV] MiG-17_FM0",
            dcs_type_name="vwv_mig17f_fm0",
        )
        with self.assertRaises(Exception):
            desc.short_name = "FM1"  # type: ignore


class TestWaypointSpec(unittest.TestCase):
    """Tests for WaypointSpec dataclass."""

    def test_creation_minimal(self) -> None:
        """WaypointSpec can be created with minimal fields."""
        wp = gen.WaypointSpec(x=100000, y=200000)
        self.assertEqual(100000, wp.x)
        self.assertEqual(200000, wp.y)
        self.assertIsNone(wp.alt_ft)
        self.assertIsNone(wp.speed_kts)
        self.assertEqual((), wp.tasks)

    def test_creation_full(self) -> None:
        """WaypointSpec can be created with all fields."""
        wp = gen.WaypointSpec(
            x=100000,
            y=200000,
            alt_ft=10000,
            speed_kts=400,
            tasks=(),
        )
        self.assertEqual(10000, wp.alt_ft)
        self.assertEqual(400, wp.speed_kts)

    def test_altitude_meters_with_default(self) -> None:
        """altitude_meters uses default when alt_ft is None."""
        wp = gen.WaypointSpec(x=0, y=0)
        result = wp.altitude_meters(10000)
        self.assertAlmostEqual(10000 * gen.FT_TO_METERS, result, places=1)

    def test_altitude_meters_with_override(self) -> None:
        """altitude_meters uses specified alt_ft."""
        wp = gen.WaypointSpec(x=0, y=0, alt_ft=20000)
        result = wp.altitude_meters(10000)
        self.assertAlmostEqual(20000 * gen.FT_TO_METERS, result, places=1)

    def test_speed_kph_with_default(self) -> None:
        """speed_kph uses default when speed_kts is None."""
        wp = gen.WaypointSpec(x=0, y=0)
        result = wp.speed_kph(400)
        self.assertAlmostEqual(400 * 1.852, result, places=1)

    def test_speed_kph_with_override(self) -> None:
        """speed_kph uses specified speed_kts."""
        wp = gen.WaypointSpec(x=0, y=0, speed_kts=500)
        result = wp.speed_kph(400)
        self.assertAlmostEqual(500 * 1.852, result, places=1)

    def test_speed_mps(self) -> None:
        """speed_mps correctly converts knots to m/s."""
        wp = gen.WaypointSpec(x=0, y=0, speed_kts=400)
        result = wp.speed_mps(300)
        self.assertAlmostEqual(400 * gen.KTS_TO_MPS, result, places=2)

    def test_offset_x(self) -> None:
        """offset_x returns new WaypointSpec with offset X coordinate."""
        wp = gen.WaypointSpec(x=100000, y=200000, alt_ft=10000, speed_kts=400)
        offset_wp = wp.offset_x(50000)
        self.assertEqual(150000, offset_wp.x)
        self.assertEqual(200000, offset_wp.y)
        self.assertEqual(10000, offset_wp.alt_ft)
        self.assertEqual(400, offset_wp.speed_kts)


class TestLoadVariantDescriptors(unittest.TestCase):
    """Tests for load_variant_descriptors function."""

    def test_load_single_variant(self) -> None:
        """Single variant is loaded correctly."""
        config_data = {
            "version": 1,
            "aircraft": {
                "id": "vwv_mig17f",
                "base_mod_dir": "[VWV] MiG-17",
                "base_display_name": "[VWV] MiG-17F",
            },
            "variants": [
                {
                    "variant_id": "FM0_BASE",
                    "short_name": "FM0",
                    "mod_dir_name": "[VWV] MiG-17_FM0",
                    "dcs_type_name": "vwv_mig17f_fm0",
                    "shape_username": "MiG-17F FM0",
                    "display_name": "[VWV] MiG-17F FM0",
                    "scales": {"cx0": 1.0, "polar": 1.0, "engine_drag": 1.0, "pfor": 1.0},
                }
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()
            descriptors = gen.load_variant_descriptors(Path(f.name))
            self.assertEqual(1, len(descriptors))
            self.assertEqual("FM0", descriptors[0].short_name)
            self.assertEqual("[VWV] MiG-17_FM0", descriptors[0].mod_dir_name)
            self.assertEqual("vwv_mig17f_fm0", descriptors[0].dcs_type_name)

    def test_load_multiple_variants(self) -> None:
        """Multiple variants are loaded correctly."""
        config_data = {
            "version": 1,
            "aircraft": {
                "id": "vwv_mig17f",
                "base_mod_dir": "[VWV] MiG-17",
                "base_display_name": "[VWV] MiG-17F",
            },
            "variants": [
                {
                    "short_name": "FM0",
                    "mod_dir_name": "mod0",
                    "dcs_type_name": "type0",
                    "variant_id": "id0",
                    "shape_username": "user0",
                    "display_name": "display0",
                    "scales": {"cx0": 1.0, "polar": 1.0, "engine_drag": 1.0, "pfor": 1.0},
                },
                {
                    "short_name": "FM6",
                    "mod_dir_name": "mod6",
                    "dcs_type_name": "type6",
                    "variant_id": "id6",
                    "shape_username": "user6",
                    "display_name": "display6",
                    "scales": {"cx0": 0.5, "polar": 0.5, "engine_drag": 0.5, "pfor": 1.05},
                },
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()
            descriptors = gen.load_variant_descriptors(Path(f.name))
            self.assertEqual(2, len(descriptors))
            self.assertEqual("FM0", descriptors[0].short_name)
            self.assertEqual("FM6", descriptors[1].short_name)


class TestDetectTypeName(unittest.TestCase):
    """Tests for detect_type_name function."""

    def test_reads_name_single_quotes(self) -> None:
        """Detects type name with single quotes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir = Path(tmpdir) / "Database"
            db_dir.mkdir()
            mig_file = db_dir / "mig17f.lua"
            mig_file.write_text("Name = 'vwv_mig17f'\n")
            detected = gen.detect_type_name(Path(tmpdir))
            self.assertEqual("vwv_mig17f", detected)

    def test_reads_name_double_quotes(self) -> None:
        """Detects type name with double quotes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir = Path(tmpdir) / "Database"
            db_dir.mkdir()
            mig_file = db_dir / "mig17f.lua"
            mig_file.write_text('Name = "vwv_mig17f"\n')
            detected = gen.detect_type_name(Path(tmpdir))
            self.assertEqual("vwv_mig17f", detected)

    def test_missing_file_returns_none(self) -> None:
        """Returns None if database file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            detected = gen.detect_type_name(Path(tmpdir))
            self.assertIsNone(detected)

    def test_missing_name_field_returns_none(self) -> None:
        """Returns None if Name field is not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir = Path(tmpdir) / "Database"
            db_dir.mkdir()
            mig_file = db_dir / "mig17f.lua"
            mig_file.write_text("-- No name field\n")
            detected = gen.detect_type_name(Path(tmpdir))
            self.assertIsNone(detected)


class TestEnsureParent(unittest.TestCase):
    """Tests for ensure_parent function."""

    def test_creates_nested_directories(self) -> None:
        """Creates parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "nested" / "path" / "file.miz"
            self.assertFalse(target.parent.exists())
            gen.ensure_parent(target)
            self.assertTrue(target.parent.exists())

    def test_handles_existing_directory(self) -> None:
        """Doesn't error if parent directory already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "file.miz"
            gen.ensure_parent(target)  # Should not raise


class TestGetOrCreateCustomPlane(unittest.TestCase):
    """Tests for get_or_create_custom_plane function."""

    def test_creates_new_plane_type(self) -> None:
        """Creates a new plane type if not exists."""
        plane_type = gen.get_or_create_custom_plane("test_plane_type")
        self.assertIsNotNone(plane_type)
        self.assertEqual("test_plane_type", plane_type.id)

    def test_returns_existing_plane_type(self) -> None:
        """Returns existing plane type if already registered."""
        plane_type_1 = gen.get_or_create_custom_plane("test_plane_existing")
        plane_type_2 = gen.get_or_create_custom_plane("test_plane_existing")
        self.assertIs(plane_type_1, plane_type_2)


class TestRenderLoggerLua(unittest.TestCase):
    """Tests for render_logger_lua function."""

    def test_includes_group_names(self) -> None:
        """Generated Lua includes group names."""
        groups = ["ACCEL_SL", "VMAX_10K", "CLIMB_SL"]
        lua = gen.render_logger_lua(groups, "test123")
        self.assertIn('"ACCEL_SL"', lua)
        self.assertIn('"VMAX_10K"', lua)
        self.assertIn('"CLIMB_SL"', lua)

    def test_includes_run_id(self) -> None:
        """Generated Lua includes run ID."""
        lua = gen.render_logger_lua(["TEST"], "abc123def")
        self.assertIn("abc123def", lua)

    def test_includes_logger_marker(self) -> None:
        """Generated Lua includes MIG17_FM_TEST marker."""
        lua = gen.render_logger_lua(["TEST"], "123")
        self.assertIn("[MIG17_FM_TEST]", lua)


class TestBuildMission(unittest.TestCase):
    """Tests for build_mission function."""

    def test_builds_single_fm_mission(self) -> None:
        """Builds mission in single-FM mode."""
        miz, groups, run_id = gen.build_mission("vwv_mig17f")
        self.assertIsNotNone(miz)
        self.assertGreater(len(groups), 0)
        self.assertIsNotNone(run_id)
        self.assertEqual(12, len(run_id))  # UUID hex[:12]

    def test_single_fm_creates_expected_groups(self) -> None:
        """Single-FM mode creates expected test groups."""
        miz, groups, run_id = gen.build_mission("vwv_mig17f")
        self.assertCountEqual(EXPECTED_GROUPS_SINGLE_FM, groups)

    def test_uses_provided_run_id(self) -> None:
        """Uses provided run_id if given."""
        miz, groups, run_id = gen.build_mission("vwv_mig17f", run_id="custom_run_id")
        self.assertEqual("custom_run_id", run_id)

    def test_builds_multi_fm_mission(self) -> None:
        """Builds mission in multi-FM mode."""
        variants = [
            gen.VariantDescriptor("FM0", "mod0", "type0"),
            gen.VariantDescriptor("FM6", "mod6", "type6"),
        ]
        miz, groups, run_id = gen.build_mission("unused", variants=variants)
        self.assertIsNotNone(miz)

        # Groups should have variant prefixes
        fm0_groups = [g for g in groups if g.startswith("FM0_")]
        fm6_groups = [g for g in groups if g.startswith("FM6_")]
        self.assertGreater(len(fm0_groups), 0)
        self.assertGreater(len(fm6_groups), 0)

        # Should also have reference aircraft groups
        mig15_groups = [g for g in groups if g.startswith("MIG15_")]
        self.assertGreater(len(mig15_groups), 0)

    def test_mission_has_trigger(self) -> None:
        """Mission includes the logger trigger."""
        miz, groups, run_id = gen.build_mission("vwv_mig17f")
        self.assertGreater(len(miz.triggerrules.triggers), 0)


class TestBaseTestPatterns(unittest.TestCase):
    """Tests for BASE_TEST_PATTERNS constant."""

    def test_includes_accel_tests(self) -> None:
        """Includes acceleration tests."""
        self.assertIn("ACCEL_SL", gen.BASE_TEST_PATTERNS)
        self.assertIn("ACCEL_10K", gen.BASE_TEST_PATTERNS)
        self.assertIn("ACCEL_20K", gen.BASE_TEST_PATTERNS)

    def test_includes_climb_tests(self) -> None:
        """Includes climb tests."""
        self.assertIn("CLIMB_SL", gen.BASE_TEST_PATTERNS)
        self.assertIn("CLIMB_10K", gen.BASE_TEST_PATTERNS)
        self.assertIn("CLIMB_10K_AB_FULL", gen.BASE_TEST_PATTERNS)
        self.assertIn("CEILING_AB_FULL", gen.BASE_TEST_PATTERNS)

    def test_includes_turn_tests(self) -> None:
        """Includes turn tests."""
        self.assertIn("TURN_10K_300", gen.BASE_TEST_PATTERNS)
        self.assertIn("TURN_10K_350", gen.BASE_TEST_PATTERNS)
        self.assertIn("TURN_10K_400", gen.BASE_TEST_PATTERNS)

    def test_includes_vmax_tests(self) -> None:
        """Includes Vmax tests."""
        self.assertIn("VMAX_SL", gen.BASE_TEST_PATTERNS)
        self.assertIn("VMAX_10K", gen.BASE_TEST_PATTERNS)
        self.assertIn("VMAX_SL_100F", gen.BASE_TEST_PATTERNS)
        self.assertIn("VMAX_SL_25F", gen.BASE_TEST_PATTERNS)
        self.assertIn("VMAX_10K_MIL", gen.BASE_TEST_PATTERNS)

    def test_includes_decel_tests(self) -> None:
        """Includes deceleration tests."""
        self.assertIn("DECEL_10K", gen.BASE_TEST_PATTERNS)
        self.assertIn("DECEL_SL", gen.BASE_TEST_PATTERNS)
        self.assertIn("DECEL_10K_IDLE", gen.BASE_TEST_PATTERNS)


class TestReferenceAircraft(unittest.TestCase):
    """Tests for REFERENCE_AIRCRAFT constant."""

    def test_includes_mig15(self) -> None:
        """Includes MiG-15bis reference."""
        names = [r["type_name"] for r in gen.REFERENCE_AIRCRAFT]
        self.assertIn("MiG-15bis", names)

    def test_includes_f86(self) -> None:
        """Includes F-86F reference."""
        names = [r["type_name"] for r in gen.REFERENCE_AIRCRAFT]
        self.assertIn("F-86F Sabre", names)

    def test_includes_mig19(self) -> None:
        """Includes MiG-19P reference."""
        names = [r["type_name"] for r in gen.REFERENCE_AIRCRAFT]
        self.assertIn("MiG-19P", names)

    def test_includes_mig21(self) -> None:
        """Includes MiG-21bis reference."""
        names = [r["type_name"] for r in gen.REFERENCE_AIRCRAFT]
        self.assertIn("MiG-21Bis", names)

    def test_all_have_prefixes(self) -> None:
        """All reference aircraft have prefixes."""
        for ref in gen.REFERENCE_AIRCRAFT:
            self.assertIn("prefix", ref)
            self.assertTrue(ref["prefix"].endswith("_"))


class MissionGeneratorEndToEndTests(unittest.TestCase):
    """End-to-end tests that generate and load actual .miz files."""

    def test_generator_creates_loadable_miz(self) -> None:
        """Generated .miz file can be loaded by pydcs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = Path(tmpdir) / "MiG17F_FM_Test.miz"
            # Use a non-existent variant JSON to force single-FM mode
            nonexistent_variant_json = Path(tmpdir) / "nonexistent.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--outfile",
                    str(outfile),
                    "--mod-root",
                    str(MOD_ROOT),
                    "--variant-json",
                    str(nonexistent_variant_json),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, msg=result.stderr or result.stdout)
            self.assertTrue(outfile.exists())
            self.assertGreater(outfile.stat().st_size, 0)

            # Register the custom plane type before loading
            type_name = gen.detect_type_name(MOD_ROOT) or "vwv_mig17f"
            gen.get_or_create_custom_plane(type_name)

            # Load and verify mission structure
            mission_data = dcs_mission.Mission()
            mission_data.load_file(str(outfile))

            red = mission_data.coalition.get("red")
            self.assertIsNotNone(red, "Red coalition missing in generated mission")
            russia = red.countries.get("Russia") if red else None
            self.assertIsNotNone(russia, "Russia country missing from red coalition")

            groups = {g.name: g for g in getattr(russia, "plane_group", [])}
            self.assertCountEqual(EXPECTED_GROUPS_SINGLE_FM, groups.keys())

    def test_generator_outputs_run_id(self) -> None:
        """Generator outputs RUN_ID for scripting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = Path(tmpdir) / "MiG17F_FM_Test.miz"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--outfile",
                    str(outfile),
                    "--mod-root",
                    str(MOD_ROOT),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode)
            # Check for RUN_ID in output
            self.assertIn("RUN_ID=", result.stdout)
            # Extract and verify run_id format
            for line in result.stdout.splitlines():
                if line.startswith("RUN_ID="):
                    run_id = line.split("=", 1)[1].strip()
                    self.assertEqual(12, len(run_id))
                    break


if __name__ == "__main__":
    unittest.main()
