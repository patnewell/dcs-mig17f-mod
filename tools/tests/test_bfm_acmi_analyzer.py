"""Tests for the BFM ACMI analyzer."""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from tools import bfm_acmi_analyzer as analyzer


# Path to test data (in tools/tests/resources for CI reproducibility)
TEST_RESOURCES_DIR = Path(__file__).parent / "resources" / "acmi_golden_records"
GOLDEN_RECORDS_PATH = TEST_RESOURCES_DIR / "golden_records.json"
BFM_CONFIG_PATH = Path(__file__).parent.parent.parent / "bfm_mission_tests.json"


class TestConversionConstants(unittest.TestCase):
    """Tests for conversion constants."""

    def test_ft_per_meter(self) -> None:
        """FT_PER_METER constant is correct."""
        self.assertAlmostEqual(3.28084, analyzer.FT_PER_METER, places=4)

    def test_kt_per_mps(self) -> None:
        """KT_PER_MPS constant is correct."""
        self.assertAlmostEqual(1.94384, analyzer.KT_PER_MPS, places=4)

    def test_fpm_per_mps(self) -> None:
        """FPM_PER_MPS constant is correct."""
        self.assertAlmostEqual(196.85, analyzer.FPM_PER_MPS, places=1)


class TestAircraftState(unittest.TestCase):
    """Tests for AircraftState dataclass."""

    def test_creation_minimal(self) -> None:
        """AircraftState can be created with minimal fields."""
        state = analyzer.AircraftState(
            time=10.0,
            lon=-43.5,
            lat=41.2,
            alt_m=5000.0,
        )
        self.assertEqual(10.0, state.time)
        self.assertEqual(-43.5, state.lon)
        self.assertEqual(41.2, state.lat)
        self.assertEqual(5000.0, state.alt_m)
        self.assertIsNone(state.u)
        self.assertIsNone(state.v)

    def test_creation_full(self) -> None:
        """AircraftState can be created with all fields."""
        state = analyzer.AircraftState(
            time=10.0,
            lon=-43.5,
            lat=41.2,
            alt_m=5000.0,
            u=100000.0,
            v=200000.0,
            roll_deg=30.0,
            pitch_deg=5.0,
            yaw_deg=90.0,
            heading_deg=95.0,
            aoa_deg=8.0,
            tas_mps=200.0,
            mach=0.85,
        )
        self.assertEqual(100000.0, state.u)
        self.assertEqual(30.0, state.roll_deg)
        self.assertEqual(8.0, state.aoa_deg)


class TestAircraftTrack(unittest.TestCase):
    """Tests for AircraftTrack dataclass."""

    def test_creation(self) -> None:
        """AircraftTrack can be created."""
        track = analyzer.AircraftTrack(
            object_id="abc123",
            name="F-86F Sabre",
            group_name="TEST_1_OPP",
            aircraft_type="F-86F Sabre",
            coalition="blue",
        )
        self.assertEqual("abc123", track.object_id)
        self.assertEqual("TEST_1_OPP", track.group_name)
        self.assertEqual([], track.states)


class TestTurnMetrics(unittest.TestCase):
    """Tests for TurnMetrics dataclass."""

    def test_creation(self) -> None:
        """TurnMetrics can be created with defaults."""
        metrics = analyzer.TurnMetrics()
        self.assertEqual(0.0, metrics.max_turn_rate_deg_s)
        self.assertEqual(0.0, metrics.avg_turn_rate_deg_s)
        self.assertIsNone(metrics.time_to_360_s)


class TestEnergyMetrics(unittest.TestCase):
    """Tests for EnergyMetrics dataclass."""

    def test_creation(self) -> None:
        """EnergyMetrics can be created with defaults."""
        metrics = analyzer.EnergyMetrics()
        self.assertEqual(0.0, metrics.initial_speed_kt)
        self.assertEqual(0.0, metrics.altitude_variation_ft)


class TestManeuveringMetrics(unittest.TestCase):
    """Tests for ManeuveringMetrics dataclass."""

    def test_creation(self) -> None:
        """ManeuveringMetrics can be created with defaults."""
        metrics = analyzer.ManeuveringMetrics()
        self.assertEqual(0.0, metrics.max_g_loading)
        self.assertEqual(0.0, metrics.max_aoa_deg)


class TestEngagementMetrics(unittest.TestCase):
    """Tests for EngagementMetrics dataclass."""

    def test_creation(self) -> None:
        """EngagementMetrics can be created with defaults."""
        metrics = analyzer.EngagementMetrics()
        self.assertEqual(0.0, metrics.duration_s)
        self.assertFalse(metrics.closure_achieved)


class TestBFMAnalysisResult(unittest.TestCase):
    """Tests for BFMAnalysisResult dataclass."""

    def test_creation(self) -> None:
        """BFMAnalysisResult can be created."""
        result = analyzer.BFMAnalysisResult(
            scenario_id="TEST_1",
            mig17_group="FM0_TEST_1",
            opponent_group="FM0_TEST_1_OPP",
            mig17_variant="FM0",
            opponent_type="F-86F Sabre",
            turn_metrics=analyzer.TurnMetrics(),
            energy_metrics=analyzer.EnergyMetrics(),
            maneuvering_metrics=analyzer.ManeuveringMetrics(),
            engagement_metrics=analyzer.EngagementMetrics(),
            envelope_assessment="NOMINAL",
        )
        self.assertEqual("TEST_1", result.scenario_id)
        self.assertEqual("NOMINAL", result.envelope_assessment)
        self.assertEqual([], result.notes)


class TestIterAcmiLines(unittest.TestCase):
    """Tests for iter_acmi_lines function."""

    def test_reads_plain_text(self) -> None:
        """Reads plain text ACMI file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".acmi", delete=False
        ) as f:
            f.write("FileType=text/acmi/tacview\n")
            f.write("FileVersion=2.2\n")
            f.write("#0\n")
            f.write("abc,T=1|2|3\n")
            f.flush()

            lines = list(analyzer.iter_acmi_lines(Path(f.name)))

        self.assertEqual(4, len(lines))
        self.assertIn("FileType=text/acmi/tacview", lines[0])


class TestParseTransform(unittest.TestCase):
    """Tests for parse_transform function."""

    def test_simple_format(self) -> None:
        """Parses T=Lon|Lat|Alt format."""
        result = analyzer.parse_transform("1.5|2.5|3000", None)
        self.assertEqual(1.5, result["lon"])
        self.assertEqual(2.5, result["lat"])
        self.assertEqual(3000.0, result["alt_m"])

    def test_with_uv(self) -> None:
        """Parses T=Lon|Lat|Alt|U|V format."""
        result = analyzer.parse_transform("1|2|3000|100000|200000", None)
        self.assertEqual(100000.0, result["u"])
        self.assertEqual(200000.0, result["v"])

    def test_with_attitude(self) -> None:
        """Parses T=Lon|Lat|Alt|Roll|Pitch|Yaw format."""
        result = analyzer.parse_transform("1|2|3000|30|5|90", None)
        self.assertEqual(30.0, result["roll_deg"])
        self.assertEqual(5.0, result["pitch_deg"])
        self.assertEqual(90.0, result["yaw_deg"])

    def test_preserves_previous_values(self) -> None:
        """Preserves values from previous state when not specified."""
        prev = analyzer.AircraftState(
            time=0, lon=1.0, lat=2.0, alt_m=3000.0, u=100.0, v=200.0
        )
        result = analyzer.parse_transform("||4000", prev)
        self.assertEqual(1.0, result["lon"])
        self.assertEqual(2.0, result["lat"])
        self.assertEqual(4000.0, result["alt_m"])


class TestIsaSpeedOfSound(unittest.TestCase):
    """Tests for isa_speed_of_sound function."""

    def test_sea_level(self) -> None:
        """Speed of sound at sea level."""
        sos = analyzer.isa_speed_of_sound(0)
        self.assertAlmostEqual(340.3, sos, delta=1.0)

    def test_at_altitude(self) -> None:
        """Speed of sound decreases with altitude."""
        sos_sl = analyzer.isa_speed_of_sound(0)
        sos_10k = analyzer.isa_speed_of_sound(3048)  # ~10,000 ft
        self.assertLess(sos_10k, sos_sl)

    def test_stratosphere(self) -> None:
        """Speed of sound is constant in stratosphere."""
        sos_11k = analyzer.isa_speed_of_sound(11000)
        sos_15k = analyzer.isa_speed_of_sound(15000)
        self.assertAlmostEqual(sos_11k, sos_15k, delta=1.0)


class TestCalculateDerivedValues(unittest.TestCase):
    """Tests for calculate_derived_values function."""

    def test_calculates_speed_from_uv(self) -> None:
        """Calculates speed from U/V position changes."""
        track = analyzer.AircraftTrack(
            object_id="test",
            name="Test",
            group_name="TEST",
            aircraft_type="Test",
            coalition="red",
        )
        # 100 m/s over 1 second
        track.states = [
            analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, u=0, v=0),
            analyzer.AircraftState(time=1, lon=0, lat=0, alt_m=1000, u=100, v=0),
        ]
        analyzer.calculate_derived_values(track)

        # Second state should have calculated TAS
        self.assertAlmostEqual(100.0, track.states[1].tas_mps, places=1)


class TestCalculateInstantaneousTurnRate(unittest.TestCase):
    """Tests for calculate_instantaneous_turn_rate function."""

    def test_calculates_turn_rate_from_uv(self) -> None:
        """Calculates turn rate from U/V position changes."""
        track = analyzer.AircraftTrack(
            object_id="test",
            name="Test",
            group_name="TEST",
            aircraft_type="Test",
            coalition="red",
        )
        # Create a 90-degree turn over 2 seconds (must be <= 5s per interval)
        # Start heading east (u increasing), then head north (v increasing)
        # At 100 m/s for 1s = 100m displacement each segment
        track.states = [
            analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, u=0, v=0),
            analyzer.AircraftState(time=1, lon=0, lat=0, alt_m=1000, u=100, v=0),
            analyzer.AircraftState(time=2, lon=0, lat=0, alt_m=1000, u=100, v=100),
        ]
        rates = analyzer.calculate_instantaneous_turn_rate(track)

        self.assertEqual(3, len(rates))
        # First point has no meaningful rate (copied from second)
        # Second point: heading is east (0 deg)
        # Third point: heading changed ~90 degrees over 1s = 90 deg/s
        self.assertAlmostEqual(90.0, rates[2], places=0)

    def test_handles_wraparound(self) -> None:
        """Handles heading wraparound correctly using U/V coordinates."""
        track = analyzer.AircraftTrack(
            object_id="test",
            name="Test",
            group_name="TEST",
            aircraft_type="Test",
            coalition="red",
        )
        # Create a turn that crosses the -pi/+pi boundary
        # Heading from ~-170 deg (heading south-southwest) to ~170 deg (south-southeast)
        # That's a 20-degree left turn, not 340 degrees right
        # At u=-100,v=-100 to u=0,v=0 => heading ~45 deg (atan2(-100,-100) = -135 deg = 225 deg)
        # At u=0,v=0 to u=100,v=-100 => heading ~315 deg (atan2(-100,100) = -45 deg = 315 deg)
        # Delta = 315 - 225 = 90 degrees over 1 second
        track.states = [
            analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, u=-100, v=-100),
            analyzer.AircraftState(time=1, lon=0, lat=0, alt_m=1000, u=0, v=0),
            analyzer.AircraftState(time=2, lon=0, lat=0, alt_m=1000, u=100, v=-100),
        ]
        rates = analyzer.calculate_instantaneous_turn_rate(track)

        # Third point should show ~90 deg/s turn rate
        self.assertAlmostEqual(90.0, rates[2], places=0)


class TestCalculateGLoading(unittest.TestCase):
    """Tests for calculate_g_loading function."""

    def test_no_turn_no_g(self) -> None:
        """G is 0.0 when not turning (below threshold)."""
        track = analyzer.AircraftTrack(
            object_id="test",
            name="Test",
            group_name="TEST",
            aircraft_type="Test",
            coalition="red",
        )
        track.states = [
            analyzer.AircraftState(
                time=0, lon=0, lat=0, alt_m=1000, roll_deg=0, tas_mps=200.0
            ),
        ]
        turn_rates = [0.0]  # No turn
        g_values = analyzer.calculate_g_loading(track, turn_rates)

        self.assertAlmostEqual(0.0, g_values[0], places=1)

    def test_g_from_turn_rate(self) -> None:
        """G is calculated from turn rate and speed."""
        track = analyzer.AircraftTrack(
            object_id="test",
            name="Test",
            group_name="TEST",
            aircraft_type="Test",
            coalition="red",
        )
        # At 200 m/s and 10 deg/s turn rate:
        # omega = 10 * pi/180 = 0.1745 rad/s
        # g = v * omega / g0 = 200 * 0.1745 / 9.80665 = ~3.56 G
        track.states = [
            analyzer.AircraftState(
                time=0, lon=0, lat=0, alt_m=1000, roll_deg=60, tas_mps=200.0
            ),
        ]
        turn_rates = [10.0]  # 10 deg/s turn
        g_values = analyzer.calculate_g_loading(track, turn_rates)

        self.assertAlmostEqual(3.56, g_values[0], places=1)


class TestCalculateRange(unittest.TestCase):
    """Tests for calculate_range function."""

    def test_same_position(self) -> None:
        """Range is 0 for same position."""
        state1 = analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, u=100, v=200)
        state2 = analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, u=100, v=200)
        range_m = analyzer.calculate_range(state1, state2)
        self.assertAlmostEqual(0.0, range_m, places=1)

    def test_horizontal_range(self) -> None:
        """Calculates horizontal range from U/V."""
        state1 = analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, u=0, v=0)
        state2 = analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, u=1000, v=0)
        range_m = analyzer.calculate_range(state1, state2)
        self.assertAlmostEqual(1000.0, range_m, places=1)

    def test_vertical_range(self) -> None:
        """Includes altitude difference in range."""
        state1 = analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, u=0, v=0)
        state2 = analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=2000, u=0, v=0)
        range_m = analyzer.calculate_range(state1, state2)
        self.assertAlmostEqual(1000.0, range_m, places=1)


class TestFindEngagementPairs(unittest.TestCase):
    """Tests for find_engagement_pairs function."""

    def test_finds_pairs(self) -> None:
        """Finds MiG-17 / opponent pairs."""
        tracks = {
            "a": analyzer.AircraftTrack(
                object_id="a",
                name="MiG-17",
                group_name="FM0_TEST_1",
                aircraft_type="MiG-17",
                coalition="red",
            ),
            "b": analyzer.AircraftTrack(
                object_id="b",
                name="F-86",
                group_name="FM0_TEST_1_OPP",
                aircraft_type="F-86",
                coalition="blue",
            ),
        }
        pairs = analyzer.find_engagement_pairs(tracks)

        self.assertEqual(1, len(pairs))
        self.assertEqual("FM0_TEST_1", pairs[0][0].group_name)
        self.assertEqual("FM0_TEST_1_OPP", pairs[0][1].group_name)

    def test_no_pairs(self) -> None:
        """Returns empty list when no pairs found."""
        tracks = {
            "a": analyzer.AircraftTrack(
                object_id="a",
                name="MiG-17",
                group_name="TEST_1",
                aircraft_type="MiG-17",
                coalition="red",
            ),
        }
        pairs = analyzer.find_engagement_pairs(tracks)
        self.assertEqual([], pairs)


class TestGenerateReport(unittest.TestCase):
    """Tests for generate_report function."""

    def test_generates_report(self) -> None:
        """Generates a report from results."""
        results = [
            analyzer.BFMAnalysisResult(
                scenario_id="TEST_1",
                mig17_group="FM0_TEST_1",
                opponent_group="FM0_TEST_1_OPP",
                mig17_variant="FM0",
                opponent_type="F-86",
                turn_metrics=analyzer.TurnMetrics(max_turn_rate_deg_s=15.0),
                energy_metrics=analyzer.EnergyMetrics(initial_speed_kt=350),
                maneuvering_metrics=analyzer.ManeuveringMetrics(max_g_loading=5.0),
                engagement_metrics=analyzer.EngagementMetrics(duration_s=60),
                envelope_assessment="NOMINAL",
            )
        ]
        report = analyzer.generate_report(results)

        self.assertIn("BFM TEST ANALYSIS REPORT", report)
        self.assertIn("FM0", report)
        self.assertIn("TEST_1", report)
        self.assertIn("NOMINAL", report)


class TestWriteCSV(unittest.TestCase):
    """Tests for write_csv function."""

    def test_writes_csv(self) -> None:
        """Writes results to CSV file."""
        results = [
            analyzer.BFMAnalysisResult(
                scenario_id="TEST_1",
                mig17_group="FM0_TEST_1",
                opponent_group="FM0_TEST_1_OPP",
                mig17_variant="FM0",
                opponent_type="F-86",
                turn_metrics=analyzer.TurnMetrics(max_turn_rate_deg_s=15.0),
                energy_metrics=analyzer.EnergyMetrics(initial_speed_kt=350),
                maneuvering_metrics=analyzer.ManeuveringMetrics(max_g_loading=5.0),
                engagement_metrics=analyzer.EngagementMetrics(duration_s=60),
                envelope_assessment="NOMINAL",
            )
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            output_path = Path(f.name)

        analyzer.write_csv(results, output_path)

        content = output_path.read_text()
        self.assertIn("variant", content)
        self.assertIn("FM0", content)
        self.assertIn("TEST_1", content)


# =============================================================================
# E2E Integration Tests using Golden Records
# =============================================================================


def _load_golden_records() -> dict:
    """Load the golden records JSON file."""
    if not GOLDEN_RECORDS_PATH.exists():
        return {}
    with GOLDEN_RECORDS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _within_tolerance(actual: float, expected: float, tolerance: float) -> bool:
    """Check if actual value is within tolerance of expected."""
    return abs(actual - expected) <= tolerance


@unittest.skipUnless(
    GOLDEN_RECORDS_PATH.exists() and TEST_RESOURCES_DIR.exists(),
    "Golden records or test data not available"
)
class TestACMIAnalyzerE2EGoldenRecords(unittest.TestCase):
    """E2E integration tests using golden records from manual BFM test flights.

    These tests verify that the ACMI analyzer produces consistent results
    against known test data. If these tests fail, it indicates a regression
    in the analyzer's calculations.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """Load golden records once for all tests."""
        cls.golden_records = _load_golden_records()
        cls.test_files = cls.golden_records.get("test_files", [])
        cls.object_filter = cls.golden_records.get("object_filter", "vwv_mig17f_fm5")

    def test_golden_records_loaded(self) -> None:
        """Golden records file is loaded and contains test files."""
        self.assertIsNotNone(self.golden_records)
        self.assertGreater(len(self.test_files), 0, "No test files in golden records")

    def test_all_test_files_exist(self) -> None:
        """All test files referenced in golden records exist."""
        for test_file in self.test_files:
            filename = test_file["filename"]
            path = TEST_RESOURCES_DIR / filename
            self.assertTrue(
                path.exists(),
                f"Test file not found: {path}"
            )

    def _run_analysis(self, filename: str) -> list:
        """Run analysis on a test file and return results."""
        acmi_path = TEST_RESOURCES_DIR / filename
        return analyzer.analyze_acmi_file(
            acmi_path,
            BFM_CONFIG_PATH if BFM_CONFIG_PATH.exists() else None,
            self.object_filter,
        )

    def _get_expected(self, test_file: dict) -> dict:
        """Get expected values from a test file entry."""
        return test_file.get("expected", {})

    def test_file_01_num_tracks(self) -> None:
        """Test file 01 finds expected number of matching tracks."""
        test_file = self.test_files[0]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertEqual(
            expected["num_matching_tracks"],
            len(results),
            f"Expected {expected['num_matching_tracks']} tracks, got {len(results)}"
        )

    def test_file_01_aircraft_identification(self) -> None:
        """Test file 01 correctly identifies the aircraft."""
        test_file = self.test_files[0]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]
        self.assertEqual(expected["group_name"], result.mig17_group)

    def test_file_01_envelope_assessment(self) -> None:
        """Test file 01 returns correct envelope assessment."""
        test_file = self.test_files[0]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]
        self.assertEqual(
            expected["envelope_assessment"],
            result.envelope_assessment,
            f"Expected assessment '{expected['envelope_assessment']}', "
            f"got '{result.envelope_assessment}'"
        )

    def test_file_01_max_turn_rate(self) -> None:
        """Test file 01 max turn rate matches golden record."""
        test_file = self.test_files[0]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]
        exp_val = expected["max_turn_rate_deg_s"]["value"]
        tolerance = expected["max_turn_rate_deg_s"]["tolerance"]

        self.assertTrue(
            _within_tolerance(
                result.turn_metrics.max_turn_rate_deg_s, exp_val, tolerance
            ),
            f"Max turn rate {result.turn_metrics.max_turn_rate_deg_s:.1f} deg/s "
            f"not within {tolerance} of expected {exp_val} deg/s"
        )

    def test_file_01_max_g(self) -> None:
        """Test file 01 max G loading matches golden record."""
        test_file = self.test_files[0]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]
        exp_val = expected["max_g"]["value"]
        tolerance = expected["max_g"]["tolerance"]

        self.assertTrue(
            _within_tolerance(result.maneuvering_metrics.max_g_loading, exp_val, tolerance),
            f"Max G {result.maneuvering_metrics.max_g_loading:.2f} "
            f"not within {tolerance} of expected {exp_val}"
        )

    def test_file_01_min_turn_radius(self) -> None:
        """Test file 01 min turn radius matches golden record."""
        test_file = self.test_files[0]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]
        exp_val = expected["min_turn_radius_ft"]["value"]
        tolerance = expected["min_turn_radius_ft"]["tolerance"]

        self.assertTrue(
            _within_tolerance(result.turn_metrics.min_turn_radius_ft, exp_val, tolerance),
            f"Min turn radius {result.turn_metrics.min_turn_radius_ft:.0f} ft "
            f"not within {tolerance} of expected {exp_val} ft"
        )

    def test_file_01_speed_range(self) -> None:
        """Test file 01 speed range matches golden record."""
        test_file = self.test_files[0]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]

        min_exp = expected["min_speed_kt"]["value"]
        min_tol = expected["min_speed_kt"]["tolerance"]
        max_exp = expected["max_speed_kt"]["value"]
        max_tol = expected["max_speed_kt"]["tolerance"]

        self.assertTrue(
            _within_tolerance(result.energy_metrics.min_speed_kt, min_exp, min_tol),
            f"Min speed {result.energy_metrics.min_speed_kt:.0f} kt "
            f"not within {min_tol} of expected {min_exp} kt"
        )
        self.assertTrue(
            _within_tolerance(result.energy_metrics.max_speed_kt, max_exp, max_tol),
            f"Max speed {result.energy_metrics.max_speed_kt:.0f} kt "
            f"not within {max_tol} of expected {max_exp} kt"
        )

    def test_file_02_envelope_assessment(self) -> None:
        """Test file 02 returns correct envelope assessment."""
        if len(self.test_files) < 2:
            self.skipTest("Test file 02 not in golden records")

        test_file = self.test_files[1]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]
        self.assertEqual(expected["envelope_assessment"], result.envelope_assessment)

    def test_file_02_max_turn_rate(self) -> None:
        """Test file 02 max turn rate matches golden record."""
        if len(self.test_files) < 2:
            self.skipTest("Test file 02 not in golden records")

        test_file = self.test_files[1]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]
        exp_val = expected["max_turn_rate_deg_s"]["value"]
        tolerance = expected["max_turn_rate_deg_s"]["tolerance"]

        self.assertTrue(
            _within_tolerance(
                result.turn_metrics.max_turn_rate_deg_s, exp_val, tolerance
            ),
            f"Max turn rate {result.turn_metrics.max_turn_rate_deg_s:.1f} deg/s "
            f"not within {tolerance} of expected {exp_val} deg/s"
        )

    def test_file_02_max_g(self) -> None:
        """Test file 02 max G loading matches golden record."""
        if len(self.test_files) < 2:
            self.skipTest("Test file 02 not in golden records")

        test_file = self.test_files[1]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]
        exp_val = expected["max_g"]["value"]
        tolerance = expected["max_g"]["tolerance"]

        self.assertTrue(
            _within_tolerance(result.maneuvering_metrics.max_g_loading, exp_val, tolerance),
            f"Max G {result.maneuvering_metrics.max_g_loading:.2f} "
            f"not within {tolerance} of expected {exp_val}"
        )

    def test_file_03_envelope_assessment(self) -> None:
        """Test file 03 returns correct envelope assessment."""
        if len(self.test_files) < 3:
            self.skipTest("Test file 03 not in golden records")

        test_file = self.test_files[2]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]
        self.assertEqual(expected["envelope_assessment"], result.envelope_assessment)

    def test_file_03_max_turn_rate(self) -> None:
        """Test file 03 max turn rate matches golden record."""
        if len(self.test_files) < 3:
            self.skipTest("Test file 03 not in golden records")

        test_file = self.test_files[2]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]
        exp_val = expected["max_turn_rate_deg_s"]["value"]
        tolerance = expected["max_turn_rate_deg_s"]["tolerance"]

        self.assertTrue(
            _within_tolerance(
                result.turn_metrics.max_turn_rate_deg_s, exp_val, tolerance
            ),
            f"Max turn rate {result.turn_metrics.max_turn_rate_deg_s:.1f} deg/s "
            f"not within {tolerance} of expected {exp_val} deg/s"
        )

    def test_file_03_duration(self) -> None:
        """Test file 03 duration matches golden record."""
        if len(self.test_files) < 3:
            self.skipTest("Test file 03 not in golden records")

        test_file = self.test_files[2]
        results = self._run_analysis(test_file["filename"])
        expected = self._get_expected(test_file)

        self.assertGreater(len(results), 0, "No results returned")
        result = results[0]
        exp_val = expected["duration_s"]["value"]
        tolerance = expected["duration_s"]["tolerance"]

        self.assertTrue(
            _within_tolerance(result.engagement_metrics.duration_s, exp_val, tolerance),
            f"Duration {result.engagement_metrics.duration_s:.1f}s "
            f"not within {tolerance} of expected {exp_val}s"
        )


@unittest.skipUnless(
    GOLDEN_RECORDS_PATH.exists() and TEST_RESOURCES_DIR.exists(),
    "Golden records or test data not available"
)
class TestACMIAnalyzerE2EParameterized(unittest.TestCase):
    """Parameterized E2E tests that run against all golden record files."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load golden records once for all tests."""
        cls.golden_records = _load_golden_records()
        cls.test_files = cls.golden_records.get("test_files", [])
        cls.object_filter = cls.golden_records.get("object_filter", "vwv_mig17f_fm5")

    def test_all_files_detect_envelope_violations(self) -> None:
        """All test files should detect envelope violations (OVER assessment)."""
        for test_file in self.test_files:
            with self.subTest(filename=test_file["filename"]):
                acmi_path = TEST_RESOURCES_DIR / test_file["filename"]
                results = analyzer.analyze_acmi_file(
                    acmi_path,
                    BFM_CONFIG_PATH if BFM_CONFIG_PATH.exists() else None,
                    self.object_filter,
                )

                expected = test_file.get("expected", {})
                self.assertGreater(len(results), 0, "No results returned")
                self.assertEqual(
                    expected.get("envelope_assessment", "OVER"),
                    results[0].envelope_assessment,
                )

    def test_all_files_max_g_exceeds_limit(self) -> None:
        """All test files should show max G exceeding the 8.0 limit."""
        for test_file in self.test_files:
            with self.subTest(filename=test_file["filename"]):
                acmi_path = TEST_RESOURCES_DIR / test_file["filename"]
                results = analyzer.analyze_acmi_file(
                    acmi_path,
                    BFM_CONFIG_PATH if BFM_CONFIG_PATH.exists() else None,
                    self.object_filter,
                )

                self.assertGreater(len(results), 0, "No results returned")
                # Max G should exceed 8.0 (the limit)
                self.assertGreater(
                    results[0].maneuvering_metrics.max_g_loading,
                    8.0,
                    "Max G should exceed limit of 8.0"
                )

    def test_all_files_max_turn_rate_exceeds_envelope(self) -> None:
        """All test files should show max turn rate exceeding 25 deg/s."""
        for test_file in self.test_files:
            with self.subTest(filename=test_file["filename"]):
                acmi_path = TEST_RESOURCES_DIR / test_file["filename"]
                results = analyzer.analyze_acmi_file(
                    acmi_path,
                    BFM_CONFIG_PATH if BFM_CONFIG_PATH.exists() else None,
                    self.object_filter,
                )

                self.assertGreater(len(results), 0, "No results returned")
                # Max turn rate should exceed 25 deg/s (instantaneous max)
                self.assertGreater(
                    results[0].turn_metrics.max_turn_rate_deg_s,
                    25.0,
                    "Max turn rate should exceed instantaneous limit of 25 deg/s"
                )

    def test_all_files_min_radius_below_threshold(self) -> None:
        """All test files should show min turn radius below 2200 ft threshold."""
        for test_file in self.test_files:
            with self.subTest(filename=test_file["filename"]):
                acmi_path = TEST_RESOURCES_DIR / test_file["filename"]
                results = analyzer.analyze_acmi_file(
                    acmi_path,
                    BFM_CONFIG_PATH if BFM_CONFIG_PATH.exists() else None,
                    self.object_filter,
                )

                self.assertGreater(len(results), 0, "No results returned")
                # Min turn radius should be significantly below 2200 ft
                # (threshold * 0.8 = 1760 ft for TIGHT_OVER classification)
                self.assertLess(
                    results[0].turn_metrics.min_turn_radius_ft,
                    1760,
                    "Min turn radius should be below tight threshold (1760 ft)"
                )


if __name__ == "__main__":
    unittest.main()
