"""Tests for the BFM test mission generator."""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from tools import generate_bfm_test_mission as bfm_gen


class TestConversionConstants(unittest.TestCase):
    """Tests for conversion constants."""

    def test_ft_to_meters(self) -> None:
        """FT_TO_METERS constant is correct."""
        self.assertAlmostEqual(0.3048, bfm_gen.FT_TO_METERS, places=4)

    def test_kts_to_mps(self) -> None:
        """KTS_TO_MPS constant is correct."""
        self.assertAlmostEqual(0.514444, bfm_gen.KTS_TO_MPS, places=4)

    def test_nm_to_meters(self) -> None:
        """NM_TO_METERS constant is correct."""
        self.assertEqual(1852.0, bfm_gen.NM_TO_METERS)

    def test_deg_to_rad(self) -> None:
        """DEG_TO_RAD constant is correct."""
        self.assertAlmostEqual(math.pi / 180.0, bfm_gen.DEG_TO_RAD, places=6)


class TestOpponentAircraft(unittest.TestCase):
    """Tests for OpponentAircraft dataclass."""

    def test_creation(self) -> None:
        """OpponentAircraft can be created with all fields."""
        opp = bfm_gen.OpponentAircraft(
            id="f86",
            dcs_type_name="F-86F Sabre",
            display_name="F-86F Sabre",
            group_prefix="F86",
        )
        self.assertEqual("f86", opp.id)
        self.assertEqual("F-86F Sabre", opp.dcs_type_name)
        self.assertEqual("F86", opp.group_prefix)


class TestEngagementGeometry(unittest.TestCase):
    """Tests for EngagementGeometry dataclass."""

    def test_creation_minimal(self) -> None:
        """EngagementGeometry can be created with minimal fields."""
        geom = bfm_gen.EngagementGeometry(
            id="test",
            name="Test",
            description="Test description",
            mig17_heading_deg=0.0,
            opponent_heading_deg=180.0,
            initial_range_nm=2.0,
            mig17_offset_deg=180.0,
        )
        self.assertEqual("test", geom.id)
        self.assertEqual(0.0, geom.mig17_altitude_offset_ft)

    def test_creation_with_altitude_offset(self) -> None:
        """EngagementGeometry with altitude offset."""
        geom = bfm_gen.EngagementGeometry(
            id="high",
            name="High",
            description="High attack",
            mig17_heading_deg=0.0,
            opponent_heading_deg=0.0,
            initial_range_nm=2.0,
            mig17_offset_deg=180.0,
            mig17_altitude_offset_ft=3000.0,
        )
        self.assertEqual(3000.0, geom.mig17_altitude_offset_ft)


class TestAltitudeBand(unittest.TestCase):
    """Tests for AltitudeBand dataclass."""

    def test_creation(self) -> None:
        """AltitudeBand can be created."""
        alt = bfm_gen.AltitudeBand(
            id="medium",
            name="Medium Altitude",
            altitude_ft=15000.0,
        )
        self.assertEqual("medium", alt.id)
        self.assertEqual(15000.0, alt.altitude_ft)


class TestInitialSpeed(unittest.TestCase):
    """Tests for InitialSpeed dataclass."""

    def test_creation(self) -> None:
        """InitialSpeed can be created."""
        spd = bfm_gen.InitialSpeed(
            id="corner",
            name="Corner Speed",
            speed_kt=350.0,
        )
        self.assertEqual("corner", spd.id)
        self.assertEqual(350.0, spd.speed_kt)


class TestBFMScenario(unittest.TestCase):
    """Tests for BFMScenario dataclass."""

    def test_creation(self) -> None:
        """BFMScenario can be created."""
        scenario = bfm_gen.BFMScenario(
            id="BFM_F86_OFF6_MED_CORNER",
            opponent="f86",
            geometry="offensive_6",
            altitude="medium",
            speed="corner",
            priority=1,
        )
        self.assertEqual("BFM_F86_OFF6_MED_CORNER", scenario.id)
        self.assertEqual(1, scenario.priority)


class TestLoadBFMConfig(unittest.TestCase):
    """Tests for load_bfm_config function."""

    def _create_minimal_config(self) -> dict:
        """Create a minimal valid BFM config."""
        return {
            "version": 1,
            "mission_settings": {
                "duration_seconds": 600,
                "test_group_spacing_nm": 20,
                "origin": {"x": -100000, "y": -300000},
            },
            "flight_envelope_targets": {
                "max_sustained_turn_rate_deg_s": 14.5,
            },
            "opponent_aircraft": [
                {
                    "id": "f86",
                    "dcs_type_name": "F-86F Sabre",
                    "display_name": "F-86F Sabre",
                    "group_prefix": "F86",
                }
            ],
            "engagement_geometries": [
                {
                    "id": "offensive_6",
                    "name": "Offensive Six",
                    "description": "Behind opponent",
                    "mig17_heading_deg": 0,
                    "opponent_heading_deg": 0,
                    "initial_range_nm": 1.5,
                    "mig17_offset_deg": 180,
                }
            ],
            "altitude_bands": [
                {
                    "id": "medium",
                    "name": "Medium",
                    "altitude_ft": 15000,
                }
            ],
            "initial_speeds": [
                {
                    "id": "corner",
                    "name": "Corner Speed",
                    "speed_kt": 350,
                }
            ],
            "test_scenarios": [
                {
                    "id": "BFM_TEST_1",
                    "opponent": "f86",
                    "geometry": "offensive_6",
                    "altitude": "medium",
                    "speed": "corner",
                    "priority": 1,
                }
            ],
        }

    def test_loads_basic_config(self) -> None:
        """Loads a basic BFM configuration."""
        config_data = self._create_minimal_config()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()
            config = bfm_gen.load_bfm_config(Path(f.name))

        self.assertEqual(600, config.duration_seconds)
        self.assertEqual(20, config.test_group_spacing_nm)
        self.assertEqual(-100000, config.origin_x)
        self.assertEqual(-300000, config.origin_y)

    def test_loads_opponents(self) -> None:
        """Loads opponent aircraft correctly."""
        config_data = self._create_minimal_config()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()
            config = bfm_gen.load_bfm_config(Path(f.name))

        self.assertIn("f86", config.opponents)
        self.assertEqual("F-86F Sabre", config.opponents["f86"].dcs_type_name)

    def test_loads_geometries(self) -> None:
        """Loads engagement geometries correctly."""
        config_data = self._create_minimal_config()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()
            config = bfm_gen.load_bfm_config(Path(f.name))

        self.assertIn("offensive_6", config.geometries)
        self.assertEqual(180, config.geometries["offensive_6"].mig17_offset_deg)

    def test_loads_scenarios(self) -> None:
        """Loads test scenarios correctly."""
        config_data = self._create_minimal_config()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()
            config = bfm_gen.load_bfm_config(Path(f.name))

        self.assertEqual(1, len(config.scenarios))
        self.assertEqual("BFM_TEST_1", config.scenarios[0].id)


class TestGetOrCreatePlaneType(unittest.TestCase):
    """Tests for get_or_create_plane_type function."""

    def test_creates_new_type(self) -> None:
        """Creates a new plane type if not exists."""
        plane = bfm_gen.get_or_create_plane_type("bfm_test_plane")
        self.assertIsNotNone(plane)
        self.assertEqual("bfm_test_plane", plane.id)

    def test_returns_existing_type(self) -> None:
        """Returns existing plane type."""
        plane1 = bfm_gen.get_or_create_plane_type("bfm_test_existing")
        plane2 = bfm_gen.get_or_create_plane_type("bfm_test_existing")
        self.assertIs(plane1, plane2)


class TestCalculateEngagementPositions(unittest.TestCase):
    """Tests for calculate_engagement_positions function."""

    def test_offensive_6_positions(self) -> None:
        """Calculate positions for offensive 6 o'clock geometry."""
        geom = bfm_gen.EngagementGeometry(
            id="off6",
            name="Offensive 6",
            description="Behind",
            mig17_heading_deg=0,
            opponent_heading_deg=0,
            initial_range_nm=1.5,
            mig17_offset_deg=180,
        )
        mig17_pos, opp_pos = bfm_gen.calculate_engagement_positions(
            geom, 15000, 0, 0
        )

        # Both should have positions
        self.assertEqual(4, len(mig17_pos))
        self.assertEqual(4, len(opp_pos))

        # MiG-17 should be behind opponent (larger X or Y depending on heading)
        # Altitude should match base for opponent
        self.assertAlmostEqual(15000 * bfm_gen.FT_TO_METERS, opp_pos[2], places=0)

    def test_altitude_offset(self) -> None:
        """Calculate positions with altitude offset."""
        geom = bfm_gen.EngagementGeometry(
            id="high",
            name="High",
            description="Above",
            mig17_heading_deg=0,
            opponent_heading_deg=0,
            initial_range_nm=2.0,
            mig17_offset_deg=180,
            mig17_altitude_offset_ft=3000,
        )
        mig17_pos, opp_pos = bfm_gen.calculate_engagement_positions(
            geom, 15000, 0, 0
        )

        # MiG-17 should be 3000 ft higher
        expected_mig17_alt = (15000 + 3000) * bfm_gen.FT_TO_METERS
        self.assertAlmostEqual(expected_mig17_alt, mig17_pos[2], places=0)


class TestLoadVariantDescriptors(unittest.TestCase):
    """Tests for load_variant_descriptors function."""

    def test_loads_variants(self) -> None:
        """Loads variant descriptors from JSON."""
        config_data = {
            "variants": [
                {"short_name": "FM0", "dcs_type_name": "type0"},
                {"short_name": "FM6", "dcs_type_name": "type6"},
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()
            variants = bfm_gen.load_variant_descriptors(Path(f.name))

        self.assertEqual(2, len(variants))
        self.assertEqual("FM0", variants[0]["short_name"])
        self.assertEqual("type6", variants[1]["dcs_type_name"])

    def test_returns_empty_for_missing_file(self) -> None:
        """Returns empty list for missing file."""
        variants = bfm_gen.load_variant_descriptors(Path("/nonexistent/path.json"))
        self.assertEqual([], variants)


class TestBuildBFMMission(unittest.TestCase):
    """Tests for build_bfm_mission function."""

    def _create_test_config(self) -> bfm_gen.BFMConfig:
        """Create a test BFM config."""
        return bfm_gen.BFMConfig(
            duration_seconds=600,
            test_group_spacing_nm=20,
            origin_x=-100000,
            origin_y=-300000,
            opponents={
                "f86": bfm_gen.OpponentAircraft(
                    id="f86",
                    dcs_type_name="F-86F Sabre",
                    display_name="F-86F Sabre",
                    group_prefix="F86",
                )
            },
            geometries={
                "offensive_6": bfm_gen.EngagementGeometry(
                    id="offensive_6",
                    name="Offensive 6",
                    description="Behind",
                    mig17_heading_deg=0,
                    opponent_heading_deg=0,
                    initial_range_nm=1.5,
                    mig17_offset_deg=180,
                )
            },
            altitudes={
                "medium": bfm_gen.AltitudeBand(
                    id="medium", name="Medium", altitude_ft=15000
                )
            },
            speeds={
                "corner": bfm_gen.InitialSpeed(
                    id="corner", name="Corner", speed_kt=350
                )
            },
            scenarios=[
                bfm_gen.BFMScenario(
                    id="TEST_1",
                    opponent="f86",
                    geometry="offensive_6",
                    altitude="medium",
                    speed="corner",
                    priority=1,
                )
            ],
            envelope_targets={},
        )

    def test_builds_mission(self) -> None:
        """Builds a BFM mission successfully."""
        config = self._create_test_config()
        miz, groups, run_id = bfm_gen.build_bfm_mission(
            config, "vwv_mig17f"
        )

        self.assertIsNotNone(miz)
        self.assertGreater(len(groups), 0)
        self.assertIsNotNone(run_id)

    def test_creates_paired_groups(self) -> None:
        """Creates MiG-17 and opponent group pairs."""
        config = self._create_test_config()
        miz, groups, run_id = bfm_gen.build_bfm_mission(
            config, "vwv_mig17f"
        )

        # Should have both MiG-17 and opponent groups
        mig17_groups = [g for g in groups if not g.endswith("_OPP")]
        opp_groups = [g for g in groups if g.endswith("_OPP")]
        self.assertGreater(len(mig17_groups), 0)
        self.assertEqual(len(mig17_groups), len(opp_groups))

    def test_uses_custom_run_id(self) -> None:
        """Uses provided run_id."""
        config = self._create_test_config()
        miz, groups, run_id = bfm_gen.build_bfm_mission(
            config, "vwv_mig17f", run_id="custom123"
        )
        self.assertEqual("custom123", run_id)

    def test_filters_by_priority(self) -> None:
        """Filters scenarios by max_priority."""
        config = self._create_test_config()
        config.scenarios.append(
            bfm_gen.BFMScenario(
                id="TEST_P3",
                opponent="f86",
                geometry="offensive_6",
                altitude="medium",
                speed="corner",
                priority=3,
            )
        )

        # Priority 1 only
        miz1, groups1, _ = bfm_gen.build_bfm_mission(
            config, "vwv_mig17f", max_priority=1
        )
        # Priority 3 includes all
        miz3, groups3, _ = bfm_gen.build_bfm_mission(
            config, "vwv_mig17f", max_priority=3
        )

        self.assertGreater(len(groups3), len(groups1))

    def test_multi_fm_mode(self) -> None:
        """Builds mission with multiple FM variants."""
        config = self._create_test_config()
        variants = [
            {"short_name": "FM0", "dcs_type_name": "type0"},
            {"short_name": "FM6", "dcs_type_name": "type6"},
        ]
        miz, groups, run_id = bfm_gen.build_bfm_mission(
            config, "unused", variants=variants
        )

        # Should have groups for both variants
        fm0_groups = [g for g in groups if g.startswith("FM0_")]
        fm6_groups = [g for g in groups if g.startswith("FM6_")]
        self.assertGreater(len(fm0_groups), 0)
        self.assertGreater(len(fm6_groups), 0)


if __name__ == "__main__":
    unittest.main()
