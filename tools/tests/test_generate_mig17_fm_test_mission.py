"""Tests for the MiG-17 FM test mission generator."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

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

            mission_loader = gen.mission.Mission()
            type_name = gen.detect_type_name(MOD_ROOT) or "vwv_mig17f"
            gen.get_or_create_custom_plane(type_name)
            load = getattr(mission_loader, "load_file", None) or getattr(mission_loader, "load", None)
            self.assertIsNotNone(load, "Mission class does not expose a loader")
            load(str(outfile))

            with zipfile.ZipFile(outfile, "r") as miz_zip:
                self.assertIn("mission", miz_zip.namelist())
                mission_content = miz_zip.read("mission").decode("utf-8", errors="ignore")

            for name in EXPECTED_GROUPS:
                self.assertIn(name, mission_content)


if __name__ == "__main__":
    unittest.main()
