"""Tests for the BFM ACMI analyzer."""
from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from tools import bfm_acmi_analyzer as analyzer


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

    def test_calculates_turn_rate(self) -> None:
        """Calculates turn rate from heading changes."""
        track = analyzer.AircraftTrack(
            object_id="test",
            name="Test",
            group_name="TEST",
            aircraft_type="Test",
            coalition="red",
        )
        # 90 degrees in 10 seconds = 9 deg/s
        track.states = [
            analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, heading_deg=0),
            analyzer.AircraftState(time=10, lon=0, lat=0, alt_m=1000, heading_deg=90),
        ]
        rates = analyzer.calculate_instantaneous_turn_rate(track)

        self.assertEqual(2, len(rates))
        self.assertEqual(0.0, rates[0])  # First point has no rate
        self.assertAlmostEqual(9.0, rates[1], places=1)

    def test_handles_wraparound(self) -> None:
        """Handles heading wraparound correctly."""
        track = analyzer.AircraftTrack(
            object_id="test",
            name="Test",
            group_name="TEST",
            aircraft_type="Test",
            coalition="red",
        )
        # 350 to 10 = 20 degrees, not 340
        track.states = [
            analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, heading_deg=350),
            analyzer.AircraftState(time=1, lon=0, lat=0, alt_m=1000, heading_deg=10),
        ]
        rates = analyzer.calculate_instantaneous_turn_rate(track)

        self.assertAlmostEqual(20.0, rates[1], places=1)


class TestCalculateGLoading(unittest.TestCase):
    """Tests for calculate_g_loading function."""

    def test_level_flight(self) -> None:
        """G is 1.0 in level flight."""
        track = analyzer.AircraftTrack(
            object_id="test",
            name="Test",
            group_name="TEST",
            aircraft_type="Test",
            coalition="red",
        )
        track.states = [
            analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, roll_deg=0),
        ]
        g_values = analyzer.calculate_g_loading(track)

        self.assertAlmostEqual(1.0, g_values[0], places=1)

    def test_banked_turn(self) -> None:
        """G increases in banked turn."""
        track = analyzer.AircraftTrack(
            object_id="test",
            name="Test",
            group_name="TEST",
            aircraft_type="Test",
            coalition="red",
        )
        # 60 degree bank = 2G
        track.states = [
            analyzer.AircraftState(time=0, lon=0, lat=0, alt_m=1000, roll_deg=60),
        ]
        g_values = analyzer.calculate_g_loading(track)

        self.assertAlmostEqual(2.0, g_values[0], places=1)


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


if __name__ == "__main__":
    unittest.main()
