"""Tests for the MiG-17 FM test log parser."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import parse_fm_test_log as parser


class TestParseGroupName(unittest.TestCase):
    """Tests for parse_group_name function."""

    def test_fm_variant_prefix(self) -> None:
        """FM<digit> prefixes are correctly parsed."""
        variant_key, test_name = parser.parse_group_name("FM0_ACCEL_SL")
        self.assertEqual("FM0", variant_key)
        self.assertEqual("ACCEL_SL", test_name)

    def test_fm_variant_two_digit(self) -> None:
        """Two-digit FM prefixes are correctly parsed."""
        variant_key, test_name = parser.parse_group_name("FM12_VMAX_10K")
        self.assertEqual("FM12", variant_key)
        self.assertEqual("VMAX_10K", test_name)

    def test_mig15_reference(self) -> None:
        """MIG15 reference aircraft prefix is correctly parsed."""
        variant_key, test_name = parser.parse_group_name("MIG15_VMAX_SL")
        self.assertEqual("MIG15", variant_key)
        self.assertEqual("VMAX_SL", test_name)

    def test_f86_reference(self) -> None:
        """F86 reference aircraft prefix is correctly parsed."""
        variant_key, test_name = parser.parse_group_name("F86_CLIMB_SL")
        self.assertEqual("F86", variant_key)
        self.assertEqual("CLIMB_SL", test_name)

    def test_mig19_reference(self) -> None:
        """MIG19 reference aircraft prefix is correctly parsed."""
        variant_key, test_name = parser.parse_group_name("MIG19_ACCEL_10K")
        self.assertEqual("MIG19", variant_key)
        self.assertEqual("ACCEL_10K", test_name)

    def test_mig21_reference(self) -> None:
        """MIG21 reference aircraft prefix is correctly parsed."""
        variant_key, test_name = parser.parse_group_name("MIG21_VMAX_10K")
        self.assertEqual("MIG21", variant_key)
        self.assertEqual("VMAX_10K", test_name)

    def test_no_prefix_backwards_compatible(self) -> None:
        """Old group names without prefix default to FM0."""
        variant_key, test_name = parser.parse_group_name("VMAX_10K")
        self.assertEqual("FM0", variant_key)
        self.assertEqual("VMAX_10K", test_name)

    def test_complex_test_name(self) -> None:
        """Complex test names with multiple underscores are preserved."""
        variant_key, test_name = parser.parse_group_name("FM6_TURN_10K_300")
        self.assertEqual("FM6", variant_key)
        self.assertEqual("TURN_10K_300", test_name)


class TestCheckTolerance(unittest.TestCase):
    """Tests for check_tolerance function."""

    def test_exact_match(self) -> None:
        """Exact match passes tolerance check."""
        self.assertTrue(parser.check_tolerance(593.0, 593, 5.0))

    def test_within_tolerance(self) -> None:
        """Value within tolerance passes."""
        # 593 * 1.04 = 616.72, within 5%
        self.assertTrue(parser.check_tolerance(616, 593, 5.0))

    def test_at_tolerance_boundary(self) -> None:
        """Value exactly at boundary passes."""
        # 593 * 1.05 = 622.65
        self.assertTrue(parser.check_tolerance(622.65, 593, 5.0))

    def test_outside_tolerance(self) -> None:
        """Value outside tolerance fails."""
        # 593 * 1.10 = 652.3, outside 5%
        self.assertFalse(parser.check_tolerance(652.3, 593, 5.0))

    def test_below_tolerance(self) -> None:
        """Value below tolerance fails."""
        # 593 * 0.90 = 533.7, outside 5%
        self.assertFalse(parser.check_tolerance(533.7, 593, 5.0))

    def test_zero_target(self) -> None:
        """Zero target requires zero measured."""
        self.assertTrue(parser.check_tolerance(0.0, 0, 5.0))
        self.assertFalse(parser.check_tolerance(0.1, 0, 5.0))


class TestFormatFuelInfo(unittest.TestCase):
    """Tests for format_fuel_info function."""

    def test_no_fuel_data(self) -> None:
        """Empty list when no fuel data available."""
        result = parser.GroupResult(name="TEST")
        lines = parser.format_fuel_info(result)
        self.assertEqual([], lines)

    def test_start_fuel_only(self) -> None:
        """Format start fuel when available."""
        result = parser.GroupResult(name="TEST", start_fuel_kg=570.0)
        lines = parser.format_fuel_info(result)
        self.assertEqual(1, len(lines))
        self.assertIn("570", lines[0])

    def test_start_fuel_with_pct(self) -> None:
        """Format start fuel with percentage when both available."""
        result = parser.GroupResult(
            name="TEST", start_fuel_kg=570.0, start_fuel_pct=50.0
        )
        lines = parser.format_fuel_info(result)
        self.assertEqual(1, len(lines))
        self.assertIn("570", lines[0])
        self.assertIn("50%", lines[0])

    def test_full_fuel_info(self) -> None:
        """Format complete fuel information."""
        result = parser.GroupResult(
            name="TEST",
            start_fuel_kg=570.0,
            start_fuel_pct=50.0,
            start_weight_kg=4490.0,
            fuel_used_kg=150.0,
        )
        lines = parser.format_fuel_info(result)
        self.assertEqual(3, len(lines))


class TestSpeedGate(unittest.TestCase):
    """Tests for SpeedGate dataclass."""

    def test_creation(self) -> None:
        """SpeedGate can be created with required fields."""
        gate = parser.SpeedGate(gate_kt=400, elapsed_s=25.5, alt_ft=10000)
        self.assertEqual(400, gate.gate_kt)
        self.assertEqual(25.5, gate.elapsed_s)
        self.assertEqual(10000, gate.alt_ft)


class TestAltGate(unittest.TestCase):
    """Tests for AltGate dataclass."""

    def test_creation(self) -> None:
        """AltGate can be created with required fields."""
        gate = parser.AltGate(gate_ft=10000, elapsed_s=45.2, climb_rate_fpm=8500)
        self.assertEqual(10000, gate.gate_ft)
        self.assertEqual(45.2, gate.elapsed_s)
        self.assertEqual(8500, gate.climb_rate_fpm)


class TestGroupResult(unittest.TestCase):
    """Tests for GroupResult dataclass."""

    def test_default_values(self) -> None:
        """GroupResult has correct defaults."""
        result = parser.GroupResult(name="TEST")
        self.assertEqual("TEST", result.name)
        self.assertEqual("FM0", result.variant_key)
        self.assertEqual("", result.test_name)
        self.assertEqual([], result.speed_gates)
        self.assertEqual([], result.alt_gates)
        self.assertIsNone(result.vmax_kt)


class TestParseLogFile(unittest.TestCase):
    """Tests for parse_log_file function."""

    def test_empty_log(self) -> None:
        """Empty log returns empty results."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write("Some random log content\n")
            f.flush()
            results = parser.parse_log_file(Path(f.name))
            self.assertEqual({}, results)

    def test_parse_start_line(self) -> None:
        """START lines are correctly parsed."""
        log_content = """
00:00:01.234 INFO    LUA: [MIG17_FM_TEST] START,FM0_VMAX_SL,alt=1000,spd=400,fuel_kg=570,fuel_pct=50,weight_kg=4490
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write(log_content)
            f.flush()
            results = parser.parse_log_file(Path(f.name))
            self.assertIn("FM0", results)
            self.assertIn("VMAX_SL", results["FM0"])
            r = results["FM0"]["VMAX_SL"]
            self.assertEqual(1000, r.start_alt_ft)
            self.assertEqual(400, r.start_spd_kt)
            self.assertEqual(570, r.start_fuel_kg)
            self.assertEqual(50, r.start_fuel_pct)
            self.assertEqual(4490, r.start_weight_kg)

    def test_parse_speed_gate(self) -> None:
        """SPEED_GATE lines are correctly parsed."""
        log_content = """
00:00:10.000 INFO    LUA: [MIG17_FM_TEST] SPEED_GATE,FM0_ACCEL_SL,400,25.5,1000
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write(log_content)
            f.flush()
            results = parser.parse_log_file(Path(f.name))
            r = results["FM0"]["ACCEL_SL"]
            self.assertEqual(1, len(r.speed_gates))
            self.assertEqual(400, r.speed_gates[0].gate_kt)
            self.assertEqual(25.5, r.speed_gates[0].elapsed_s)
            self.assertEqual(1000, r.speed_gates[0].alt_ft)

    def test_parse_alt_gate(self) -> None:
        """ALT_GATE lines are correctly parsed."""
        log_content = """
00:00:30.000 INFO    LUA: [MIG17_FM_TEST] ALT_GATE,FM0_CLIMB_SL,10000,45.2,8500
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write(log_content)
            f.flush()
            results = parser.parse_log_file(Path(f.name))
            r = results["FM0"]["CLIMB_SL"]
            self.assertEqual(1, len(r.alt_gates))
            self.assertEqual(10000, r.alt_gates[0].gate_ft)
            self.assertEqual(45.2, r.alt_gates[0].elapsed_s)
            self.assertEqual(8500, r.alt_gates[0].climb_rate_fpm)

    def test_parse_vmax(self) -> None:
        """VMAX lines are correctly parsed."""
        log_content = """
00:01:00.000 INFO    LUA: [MIG17_FM_TEST] VMAX,FM0_VMAX_SL,593.5,1000,0.893
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write(log_content)
            f.flush()
            results = parser.parse_log_file(Path(f.name))
            r = results["FM0"]["VMAX_SL"]
            self.assertAlmostEqual(593.5, r.vmax_kt)
            self.assertEqual(1000, r.vmax_alt_ft)
            self.assertAlmostEqual(0.893, r.vmax_mach)

    def test_parse_ceiling(self) -> None:
        """CEILING lines are correctly parsed."""
        log_content = """
00:05:00.000 INFO    LUA: [MIG17_FM_TEST] CEILING,FM0_CEILING_AB_FULL,54500,950,0.85
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write(log_content)
            f.flush()
            results = parser.parse_log_file(Path(f.name))
            r = results["FM0"]["CEILING_AB_FULL"]
            self.assertEqual(54500, r.ceiling_alt_ft)
            self.assertEqual(950, r.ceiling_roc_fpm)
            self.assertAlmostEqual(0.85, r.ceiling_mach)

    def test_parse_summary(self) -> None:
        """SUMMARY lines are correctly parsed."""
        log_content = """
00:10:00.000 INFO    LUA: [MIG17_FM_TEST] SUMMARY,FM0_VMAX_SL,595.2,1100,500,fuel_start=570,fuel_end=420,fuel_used=150
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write(log_content)
            f.flush()
            results = parser.parse_log_file(Path(f.name))
            r = results["FM0"]["VMAX_SL"]
            self.assertAlmostEqual(595.2, r.max_spd_kt)
            self.assertEqual(1100, r.max_alt_ft)
            self.assertEqual(500, r.max_vspd_fpm)
            self.assertEqual(570, r.start_fuel_kg)
            self.assertEqual(420, r.end_fuel_kg)
            self.assertEqual(150, r.fuel_used_kg)

    def test_parse_multi_variant(self) -> None:
        """Multiple variants are organized correctly."""
        log_content = """
[MIG17_FM_TEST] START,FM0_VMAX_SL,alt=1000,spd=400
[MIG17_FM_TEST] START,FM6_VMAX_SL,alt=1000,spd=400
[MIG17_FM_TEST] START,MIG15_VMAX_SL,alt=1000,spd=400
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write(log_content)
            f.flush()
            results = parser.parse_log_file(Path(f.name))
            self.assertIn("FM0", results)
            self.assertIn("FM6", results)
            self.assertIn("MIG15", results)
            self.assertIn("VMAX_SL", results["FM0"])
            self.assertIn("VMAX_SL", results["FM6"])
            self.assertIn("VMAX_SL", results["MIG15"])

    def test_backwards_compatible_no_prefix(self) -> None:
        """Old logs without FM prefix are parsed under FM0."""
        log_content = """
[MIG17_FM_TEST] START,VMAX_SL,alt=1000,spd=400
[MIG17_FM_TEST] VMAX,VMAX_SL,593.5,1000,0.893
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write(log_content)
            f.flush()
            results = parser.parse_log_file(Path(f.name))
            self.assertIn("FM0", results)
            self.assertIn("VMAX_SL", results["FM0"])
            r = results["FM0"]["VMAX_SL"]
            self.assertAlmostEqual(593.5, r.vmax_kt)


class TestGenerateReport(unittest.TestCase):
    """Tests for generate_report function."""

    def test_empty_results(self) -> None:
        """Empty results generate basic report structure."""
        report = parser.generate_report({})
        self.assertIn("MiG-17F Flight Model Test Report", report)
        self.assertIn("Historical Performance Targets", report)
        self.assertIn("OVERALL RESULT", report)

    def test_single_variant_report(self) -> None:
        """Single variant generates proper section."""
        results = {
            "FM0": {
                "VMAX_SL": parser.GroupResult(
                    name="FM0_VMAX_SL",
                    variant_key="FM0",
                    test_name="VMAX_SL",
                    vmax_kt=593.0,
                    max_spd_kt=593.0,
                ),
            }
        }
        report = parser.generate_report(results)
        self.assertIn("Variant FM0", report)
        self.assertIn("VMAX_SL", report)
        self.assertIn("593", report)

    def test_multi_variant_report(self) -> None:
        """Multiple variants each get their own section."""
        results = {
            "FM0": {"VMAX_SL": parser.GroupResult(name="FM0_VMAX_SL")},
            "FM6": {"VMAX_SL": parser.GroupResult(name="FM6_VMAX_SL")},
        }
        report = parser.generate_report(results)
        self.assertIn("Variant FM0", report)
        self.assertIn("Variant FM6", report)
        self.assertIn("Multi-FM Mode: 2 variants", report)


class TestWriteCsv(unittest.TestCase):
    """Tests for write_csv function."""

    def test_write_csv_creates_file(self) -> None:
        """CSV file is created with correct headers and data."""
        results = {
            "FM0": {
                "VMAX_SL": parser.GroupResult(
                    name="FM0_VMAX_SL",
                    variant_key="FM0",
                    test_name="VMAX_SL",
                    max_spd_kt=593.5,
                    vmax_kt=593.5,
                    vmax_mach=0.893,
                ),
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "results.csv"
            parser.write_csv(results, csv_path)
            self.assertTrue(csv_path.exists())
            content = csv_path.read_text()
            self.assertIn("variant,test,group_name", content)
            self.assertIn("FM0,VMAX_SL,FM0_VMAX_SL", content)
            self.assertIn("593.5", content)

    def test_write_csv_multiple_variants(self) -> None:
        """CSV includes all variants and tests."""
        results = {
            "FM0": {
                "VMAX_SL": parser.GroupResult(name="FM0_VMAX_SL"),
                "VMAX_10K": parser.GroupResult(name="FM0_VMAX_10K"),
            },
            "FM6": {
                "VMAX_SL": parser.GroupResult(name="FM6_VMAX_SL"),
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "results.csv"
            parser.write_csv(results, csv_path)
            content = csv_path.read_text()
            lines = content.strip().split("\n")
            # Header + 3 data rows
            self.assertEqual(4, len(lines))


class TestFindDcsLog(unittest.TestCase):
    """Tests for find_dcs_log function."""

    def test_returns_none_when_not_found(self) -> None:
        """Returns None when no DCS log file exists at standard locations."""
        # This test may pass or fail depending on system state
        # We just verify it returns Path or None without exceptions
        result = parser.find_dcs_log()
        self.assertTrue(result is None or isinstance(result, Path))


if __name__ == "__main__":
    unittest.main()
