"""Tests for the MiG-17 FM test mission generator."""
from __future__ import annotations

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
EXPECTED_GROUPS = [
    "ACCEL_SL",
    "ACCEL_10K",
    "ACCEL_20K",
    "CLIMB_0K_380",
    "CLIMB_10K_380",
    "TURN_10K_300",
    "TURN_10K_350",
    "TURN_10K_400",
    "DECEL_10K_325",
]


class MissionGeneratorUnitTests(unittest.TestCase):
    def test_detect_type_name_reads_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir = Path(tmpdir) / "Database"
            db_dir.mkdir()
            mig_file = db_dir / "mig17f.lua"
            mig_file.write_text("Name = 'vwv_mig17f'\n")

            detected = gen.detect_type_name(Path(tmpdir))
            self.assertEqual("vwv_mig17f", detected)

    def test_detect_type_name_missing_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            detected = gen.detect_type_name(Path(tmpdir))
            self.assertIsNone(detected)

    def test_ensure_parent_creates_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "nested" / "path" / "file.miz"
            self.assertFalse(target.parent.exists())
            gen.ensure_parent(target)
            self.assertTrue(target.parent.exists())

    def test_build_mission_runs_with_valid_type(self) -> None:
        miz, groups = gen.build_mission("vwv_mig17f")
        self.assertGreater(len(groups), 0)
        self.assertIsNotNone(miz)


class MissionGeneratorEndToEndTests(unittest.TestCase):
    def test_generator_creates_loadable_miz(self) -> None:
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

            self.assertEqual(0, result.returncode, msg=result.stderr or result.stdout)
            self.assertTrue(outfile.exists())
            self.assertGreater(outfile.stat().st_size, 0)

            type_name = gen.detect_type_name(MOD_ROOT) or "vwv_mig17f"
            gen.get_or_create_custom_plane(type_name)
            mission_data = dcs_mission.Mission()
            mission_data.load_file(str(outfile))

            red = mission_data.coalition.get("red")
            self.assertIsNotNone(red, "Red coalition missing in generated mission")
            russia = red.countries.get("Russia") if red else None
            self.assertIsNotNone(russia, "Russia country missing from red coalition")

            groups = {g.name: g for g in getattr(russia, "plane_group", [])}
            self.assertCountEqual(EXPECTED_GROUPS, groups.keys())

            expected_waypoints = {
                "ACCEL_SL": [
                    {"x": 305000, "y": 600000, "alt": 1000 * gen.FT_TO_METERS, "speed": 230 * gen.KTS_TO_MPS},
                    {"x": 397600, "y": 600000, "alt": 1000 * gen.FT_TO_METERS, "speed": 800 * gen.KTS_TO_MPS},
                    {"x": 416120, "y": 600000, "alt": 1000 * gen.FT_TO_METERS, "speed": 800 * gen.KTS_TO_MPS, "orbit": True},
                ],
                "ACCEL_10K": [
                    {"x": 300000, "y": 605000, "alt": 10000 * gen.FT_TO_METERS, "speed": 300 * gen.KTS_TO_MPS},
                    {"x": 300000, "y": 697600, "alt": 10000 * gen.FT_TO_METERS, "speed": 800 * gen.KTS_TO_MPS},
                    {"x": 300000, "y": 716120, "alt": 10000 * gen.FT_TO_METERS, "speed": 800 * gen.KTS_TO_MPS, "orbit": True},
                ],
                "ACCEL_20K": [
                    {"x": 295000, "y": 600000, "alt": 20000 * gen.FT_TO_METERS, "speed": 300 * gen.KTS_TO_MPS},
                    {"x": 295000, "y": 692600, "alt": 20000 * gen.FT_TO_METERS, "speed": 800 * gen.KTS_TO_MPS},
                    {"x": 295000, "y": 711120, "alt": 20000 * gen.FT_TO_METERS, "speed": 800 * gen.KTS_TO_MPS, "orbit": True},
                ],
                "CLIMB_0K_380": [
                    {"x": 315000, "y": 615000, "alt": 1000 * gen.FT_TO_METERS, "speed": 380 * gen.KTS_TO_MPS},
                    {"x": 315000, "y": 615000, "alt": 33000 * gen.FT_TO_METERS, "speed": 380 * gen.KTS_TO_MPS},
                ],
                "CLIMB_10K_380": [
                    {"x": 320000, "y": 585000, "alt": 10000 * gen.FT_TO_METERS, "speed": 380 * gen.KTS_TO_MPS},
                    {"x": 320000, "y": 585000, "alt": 33000 * gen.FT_TO_METERS, "speed": 380 * gen.KTS_TO_MPS},
                ],
                "TURN_10K_300": [
                    {"x": 285000, "y": 594000, "alt": 10000 * gen.FT_TO_METERS, "speed": 300 * gen.KTS_TO_MPS},
                    {"x": 285000, "y": 594000, "alt": 10000 * gen.FT_TO_METERS, "speed": 300 * gen.KTS_TO_MPS, "orbit": True},
                ],
                "TURN_10K_350": [
                    {"x": 285000, "y": 593000, "alt": 10000 * gen.FT_TO_METERS, "speed": 350 * gen.KTS_TO_MPS},
                    {"x": 285000, "y": 593000, "alt": 10000 * gen.FT_TO_METERS, "speed": 350 * gen.KTS_TO_MPS, "orbit": True},
                ],
                "TURN_10K_400": [
                    {"x": 285000, "y": 592000, "alt": 10000 * gen.FT_TO_METERS, "speed": 400 * gen.KTS_TO_MPS},
                    {"x": 285000, "y": 592000, "alt": 10000 * gen.FT_TO_METERS, "speed": 400 * gen.KTS_TO_MPS, "orbit": True},
                ],
                "DECEL_10K_325": [
                    {"x": 330000, "y": 600000, "alt": 10000 * gen.FT_TO_METERS, "speed": 325 * gen.KTS_TO_MPS},
                    {"x": 404080, "y": 600000, "alt": 10000 * gen.FT_TO_METERS, "speed": 200 * gen.KTS_TO_MPS},
                ],
            }

            orbit_classes = tuple(
                cls for cls in (getattr(dcs_task, "OrbitAction", None), getattr(dcs_task, "Orbit", None)) if cls
            )
            self.assertTrue(orbit_classes, "No orbit task class available in dcs library")

            for name, expected_points in expected_waypoints.items():
                group = groups.get(name)
                self.assertIsNotNone(group, f"Missing group {name}")
                if group is None:  # pragma: no cover - guard for mypy
                    continue

                self.assertEqual(len(expected_points), len(group.points), f"Unexpected waypoint count for {name}")
                for idx, expected in enumerate(expected_points):
                    wp = group.points[idx]
                    self.assertAlmostEqual(expected["x"], wp.position.x, delta=1.0)
                    self.assertAlmostEqual(expected["y"], wp.position.y, delta=1.0)
                    self.assertAlmostEqual(expected["alt"], wp.alt, delta=0.5)
                    self.assertAlmostEqual(expected["speed"], wp.speed, delta=0.1)

                    expect_orbit = expected.get("orbit", False)
                    tasks = getattr(wp, "tasks", []) or []
                    has_orbit = any(isinstance(t, orbit_classes) for t in tasks)
                    if expect_orbit:
                        self.assertTrue(has_orbit, f"Missing orbit task at waypoint {idx} for {name}")
                    else:
                        self.assertFalse(has_orbit, f"Unexpected orbit task at waypoint {idx} for {name}")


if __name__ == "__main__":
    unittest.main()
