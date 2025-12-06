"""Tests for the MiG-17F FM variant builder."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import build_mig17f_variants_from_json as builder


class TestScales(unittest.TestCase):
    """Tests for Scales dataclass."""

    def test_creation(self) -> None:
        """Scales dataclass can be created with all fields."""
        scales = builder.Scales(cx0=0.6, polar=0.5, engine_drag=0.7, pfor=1.05)
        self.assertEqual(0.6, scales.cx0)
        self.assertEqual(0.5, scales.polar)
        self.assertEqual(0.7, scales.engine_drag)
        self.assertEqual(1.05, scales.pfor)

    def test_frozen(self) -> None:
        """Scales dataclass is frozen (immutable)."""
        scales = builder.Scales(cx0=0.6, polar=0.5, engine_drag=0.7, pfor=1.05)
        with self.assertRaises(Exception):  # FrozenInstanceError
            scales.cx0 = 0.8  # type: ignore


class TestVariant(unittest.TestCase):
    """Tests for Variant dataclass."""

    def test_creation(self) -> None:
        """Variant dataclass can be created with all fields."""
        scales = builder.Scales(cx0=1.0, polar=1.0, engine_drag=1.0, pfor=1.0)
        variant = builder.Variant(
            variant_id="FM0_BASE",
            short_name="FM0",
            mod_dir_name="[VWV] MiG-17_FM0",
            dcs_type_name="vwv_mig17f_fm0",
            shape_username="MiG-17F FM0",
            display_name="[VWV] MiG-17F FM0",
            scales=scales,
            notes="Base variant",
        )
        self.assertEqual("FM0_BASE", variant.variant_id)
        self.assertEqual("FM0", variant.short_name)


class TestVariantConfig(unittest.TestCase):
    """Tests for VariantConfig dataclass."""

    def test_creation(self) -> None:
        """VariantConfig can be created with all fields."""
        config = builder.VariantConfig(
            version=1,
            aircraft_id="vwv_mig17f",
            base_mod_dir="[VWV] MiG-17",
            base_display_name="[VWV] MiG-17F",
            description="Test config",
            variants=[],
        )
        self.assertEqual(1, config.version)
        self.assertEqual("vwv_mig17f", config.aircraft_id)


class TestLoadVariantConfig(unittest.TestCase):
    """Tests for load_variant_config function."""

    def test_load_valid_json(self) -> None:
        """Valid JSON is loaded correctly."""
        config_data = {
            "version": 1,
            "aircraft": {
                "id": "vwv_mig17f",
                "base_mod_dir": "[VWV] MiG-17",
                "base_display_name": "[VWV] MiG-17F",
                "description": "Test aircraft",
            },
            "variants": [
                {
                    "variant_id": "FM0_BASE",
                    "short_name": "FM0",
                    "mod_dir_name": "[VWV] MiG-17_FM0",
                    "dcs_type_name": "vwv_mig17f_fm0",
                    "shape_username": "MiG-17F FM0",
                    "display_name": "[VWV] MiG-17F FM0",
                    "scales": {
                        "cx0": 1.0,
                        "polar": 1.0,
                        "engine_drag": 1.0,
                        "pfor": 1.0,
                    },
                    "notes": "Base variant",
                }
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()
            config = builder.load_variant_config(Path(f.name))
            self.assertEqual(1, config.version)
            self.assertEqual("vwv_mig17f", config.aircraft_id)
            self.assertEqual(1, len(config.variants))
            self.assertEqual("FM0", config.variants[0].short_name)

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
                    "variant_id": "FM0",
                    "short_name": "FM0",
                    "mod_dir_name": "mod0",
                    "dcs_type_name": "type0",
                    "shape_username": "user0",
                    "display_name": "display0",
                    "scales": {"cx0": 1.0, "polar": 1.0, "engine_drag": 1.0, "pfor": 1.0},
                },
                {
                    "variant_id": "FM1",
                    "short_name": "FM1",
                    "mod_dir_name": "mod1",
                    "dcs_type_name": "type1",
                    "shape_username": "user1",
                    "display_name": "display1",
                    "scales": {"cx0": 0.8, "polar": 0.9, "engine_drag": 0.7, "pfor": 1.05},
                },
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()
            config = builder.load_variant_config(Path(f.name))
            self.assertEqual(2, len(config.variants))
            self.assertEqual("FM0", config.variants[0].short_name)
            self.assertEqual("FM1", config.variants[1].short_name)


class TestScaleAeroTableData(unittest.TestCase):
    """Tests for scale_aero_table_data function."""

    def test_scale_cx0_and_polar(self) -> None:
        """Cx0, B2, and B4 values are scaled correctly."""
        lua_content = """
aerodynamics =
{
    table_data =
    {
        { 0.0,  0.0200  ,       0.0715 ,       0.100   ,       0.010   ,  1.0,  15.0,  1.20},
        { 0.5,  0.0180  ,       0.0700 ,       0.090   ,       0.009   ,  1.0,  15.0,  1.15},
    }, -- end of table_data
}, -- end of aerodynamics
engine = {}
"""
        scales = builder.Scales(cx0=0.5, polar=0.8, engine_drag=1.0, pfor=1.0)
        result = builder.scale_aero_table_data(lua_content, scales)

        # Cx0 should be scaled: 0.0200 * 0.5 = 0.0100
        self.assertIn("0.0100", result)
        # B2 should be scaled: 0.100 * 0.8 = 0.080
        self.assertIn("0.080", result)
        # B4 should be scaled: 0.010 * 0.8 = 0.008
        self.assertIn("0.008", result)

    def test_no_aerodynamics_section(self) -> None:
        """Returns unchanged content if no aerodynamics section."""
        lua_content = "some_other_content = {}"
        scales = builder.Scales(cx0=0.5, polar=0.8, engine_drag=1.0, pfor=1.0)
        result = builder.scale_aero_table_data(lua_content, scales)
        self.assertEqual(lua_content, result)


class TestScaleEngineDcxEng(unittest.TestCase):
    """Tests for scale_engine_dcx_eng function."""

    def test_scale_dcx_eng(self) -> None:
        """dcx_eng value is scaled correctly."""
        lua_content = """
engine =
{
    dcx_eng = 0.0050,
    table_data = {},
}
"""
        scales = builder.Scales(cx0=1.0, polar=1.0, engine_drag=0.6, pfor=1.0)
        result = builder.scale_engine_dcx_eng(lua_content, scales)
        # 0.0050 * 0.6 = 0.0030
        self.assertIn("0.0030", result)

    def test_no_dcx_eng(self) -> None:
        """Returns unchanged content if no dcx_eng."""
        lua_content = "engine = { table_data = {} }"
        scales = builder.Scales(cx0=1.0, polar=1.0, engine_drag=0.6, pfor=1.0)
        result = builder.scale_engine_dcx_eng(lua_content, scales)
        self.assertEqual(lua_content, result)


class TestScaleEnginePfor(unittest.TestCase):
    """Tests for scale_engine_pfor function."""

    def test_scale_pfor_values(self) -> None:
        """Pfor values are scaled correctly without changing Pmax."""
        lua_content = """
aerodynamics = {}
}, -- end of aerodynamics
engine =
{
    dcx_eng = 0.0050,
    table_data =
    {
        { 0.0,  26500,  33800},
        { 0.5,  25000,  32000},
    }, -- end of table_data
}, -- end of engine
"""
        scales = builder.Scales(cx0=1.0, polar=1.0, engine_drag=1.0, pfor=1.10)
        result = builder.scale_engine_pfor(lua_content, scales)
        # Pfor 33800 * 1.10 = 37180
        self.assertIn("37180", result)
        # Pfor 32000 * 1.10 = 35200
        self.assertIn("35200", result)
        # Pmax should be unchanged
        self.assertIn("26500", result)
        self.assertIn("25000", result)


class TestPatchEntryLua(unittest.TestCase):
    """Tests for patch_entry_lua function."""

    def test_patch_self_id(self) -> None:
        """self_ID is patched with variant suffix."""
        entry_content = 'self_ID = "tetet_mig17f"'
        scales = builder.Scales(cx0=1.0, polar=1.0, engine_drag=1.0, pfor=1.0)
        variant = builder.Variant(
            variant_id="FM6_TEST",
            short_name="FM6",
            mod_dir_name="mod",
            dcs_type_name="vwv_mig17f_fm6",
            shape_username="user",
            display_name="display",
            scales=scales,
            notes="",
        )
        result = builder.patch_entry_lua(entry_content, variant)
        self.assertIn("tetet_mig17f_fm6", result)

    def test_patch_display_name(self) -> None:
        """displayName is patched with variant display_name."""
        entry_content = 'displayName = _("mig17f"),'
        scales = builder.Scales(cx0=1.0, polar=1.0, engine_drag=1.0, pfor=1.0)
        variant = builder.Variant(
            variant_id="FM6_TEST",
            short_name="FM6",
            mod_dir_name="mod",
            dcs_type_name="vwv_mig17f_fm6",
            shape_username="user",
            display_name="[VWV] MiG-17F FM6",
            scales=scales,
            notes="",
        )
        result = builder.patch_entry_lua(entry_content, variant)
        self.assertIn("[VWV] MiG-17F FM6", result)

    def test_patch_file_menu_name(self) -> None:
        """fileMenuName is patched with variant short_name."""
        entry_content = 'fileMenuName = _("MiG-17F"),'
        scales = builder.Scales(cx0=1.0, polar=1.0, engine_drag=1.0, pfor=1.0)
        variant = builder.Variant(
            variant_id="FM6_TEST",
            short_name="FM6",
            mod_dir_name="mod",
            dcs_type_name="vwv_mig17f_fm6",
            shape_username="user",
            display_name="display",
            scales=scales,
            notes="",
        )
        result = builder.patch_entry_lua(entry_content, variant)
        self.assertIn("FM6 MiG-17F", result)


class TestPatchIdentityFields(unittest.TestCase):
    """Tests for patch_identity_fields function."""

    def test_patch_name_field(self) -> None:
        """Name field is patched with dcs_type_name."""
        lua_content = "Name = 'vwv_mig17f'"
        scales = builder.Scales(cx0=1.0, polar=1.0, engine_drag=1.0, pfor=1.0)
        variant = builder.Variant(
            variant_id="FM6_TEST",
            short_name="FM6",
            mod_dir_name="mod",
            dcs_type_name="vwv_mig17f_fm6",
            shape_username="user",
            display_name="display",
            scales=scales,
            notes="",
        )
        result = builder.patch_identity_fields(lua_content, variant)
        self.assertIn("vwv_mig17f_fm6", result)
        self.assertNotIn("'vwv_mig17f'", result)

    def test_patch_display_name_field(self) -> None:
        """DisplayName field is patched with display_name."""
        lua_content = "DisplayName = _('[VWV] MiG-17F \"Fresco C\"'),"
        scales = builder.Scales(cx0=1.0, polar=1.0, engine_drag=1.0, pfor=1.0)
        variant = builder.Variant(
            variant_id="FM6_TEST",
            short_name="FM6",
            mod_dir_name="mod",
            dcs_type_name="vwv_mig17f_fm6",
            shape_username="user",
            display_name="[VWV] MiG-17F FM6",
            scales=scales,
            notes="",
        )
        result = builder.patch_identity_fields(lua_content, variant)
        self.assertIn("[VWV] MiG-17F FM6", result)

    def test_patch_shape_username(self) -> None:
        """username in shape_table_data is patched."""
        lua_content = """
shape_table_data = {
    {
        username = 'MiG-17F',
        file = 'mig17f',
    },
}
"""
        scales = builder.Scales(cx0=1.0, polar=1.0, engine_drag=1.0, pfor=1.0)
        variant = builder.Variant(
            variant_id="FM6_TEST",
            short_name="FM6",
            mod_dir_name="mod",
            dcs_type_name="vwv_mig17f_fm6",
            shape_username="MiG-17F FM6 Test",
            display_name="display",
            scales=scales,
            notes="",
        )
        result = builder.patch_identity_fields(lua_content, variant)
        self.assertIn("MiG-17F FM6 Test", result)


class TestApplyVariantModifications(unittest.TestCase):
    """Tests for apply_variant_modifications function."""

    def test_applies_all_modifications(self) -> None:
        """All modifications are applied to lua content."""
        lua_content = """
Name = 'vwv_mig17f'
DisplayName = _('[VWV] MiG-17F')

shape_table_data = {
    { username = 'MiG-17F', file = 'mig17f' },
}

aerodynamics = {
    table_data = {
        { 0.0,  0.0200  ,       0.0715 ,       0.100   ,       0.010   ,  1.0,  15.0,  1.20},
    }, -- end of table_data
}, -- end of aerodynamics

engine = {
    dcx_eng = 0.0050,
    table_data = {
        { 0.0,  26500,  33800},
    }, -- end of table_data
}, -- end of engine
"""
        scales = builder.Scales(cx0=0.5, polar=0.8, engine_drag=0.6, pfor=1.10)
        variant = builder.Variant(
            variant_id="FM6_TEST",
            short_name="FM6",
            mod_dir_name="mod",
            dcs_type_name="vwv_mig17f_fm6",
            shape_username="MiG-17F FM6",
            display_name="[VWV] MiG-17F FM6",
            scales=scales,
            notes="",
        )
        result = builder.apply_variant_modifications(lua_content, variant)

        # Identity patches
        self.assertIn("vwv_mig17f_fm6", result)
        self.assertIn("[VWV] MiG-17F FM6", result)
        self.assertIn("MiG-17F FM6", result)

        # Cx0 scaled: 0.02 * 0.5 = 0.01
        self.assertIn("0.0100", result)

        # dcx_eng scaled: 0.005 * 0.6 = 0.003
        self.assertIn("0.0030", result)

        # Pfor scaled: 33800 * 1.10 = 37180
        self.assertIn("37180", result)


class TestBuildVariant(unittest.TestCase):
    """Tests for build_variant function."""

    def test_build_variant_copies_and_modifies(self) -> None:
        """Variant is built by copying base mod and applying modifications."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a minimal base mod
            base_mod = tmpdir_path / "base_mod"
            base_mod.mkdir()
            (base_mod / "Database").mkdir()
            (base_mod / "Database" / "mig17f.lua").write_text(
                """
Name = 'vwv_mig17f'
DisplayName = _('[VWV] MiG-17F')
shape_table_data = {
    { username = 'MiG-17F', file = 'mig17f' },
}
aerodynamics = {
    table_data = {
        { 0.0,  0.0200  ,       0.0715 ,       0.100   ,       0.010   ,  1.0,  15.0,  1.20},
    }, -- end of table_data
}, -- end of aerodynamics
engine = {
    dcx_eng = 0.0050,
    table_data = {
        { 0.0,  26500,  33800},
    }, -- end of table_data
}, -- end of engine
"""
            )
            (base_mod / "entry.lua").write_text(
                """
self_ID = "tetet_mig17f"
displayName = _("mig17f")
"""
            )

            variants_root = tmpdir_path / "variants"
            variants_root.mkdir()

            scales = builder.Scales(cx0=0.5, polar=0.8, engine_drag=0.6, pfor=1.10)
            variant = builder.Variant(
                variant_id="FM6_TEST",
                short_name="FM6",
                mod_dir_name="[VWV] MiG-17_FM6",
                dcs_type_name="vwv_mig17f_fm6",
                shape_username="MiG-17F FM6",
                display_name="[VWV] MiG-17F FM6",
                scales=scales,
                notes="Test variant",
            )

            result_path = builder.build_variant(base_mod, variant, variants_root)

            # Check variant folder was created
            self.assertTrue(result_path.exists())
            self.assertEqual("[VWV] MiG-17_FM6", result_path.name)

            # Check mig17f.lua was modified
            lua_content = (result_path / "Database" / "mig17f.lua").read_text()
            self.assertIn("vwv_mig17f_fm6", lua_content)

            # Check entry.lua was modified
            entry_content = (result_path / "entry.lua").read_text()
            self.assertIn("fm6", entry_content.lower())


class TestInstallToSavedGames(unittest.TestCase):
    """Tests for install_to_saved_games function."""

    def test_install_copies_variant(self) -> None:
        """Variant is copied to DCS saved games folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a variant folder
            variant_path = tmpdir_path / "[VWV] MiG-17_FM6"
            variant_path.mkdir()
            (variant_path / "test.txt").write_text("test content")

            # Create a mock saved games folder
            saved_games = tmpdir_path / "Saved Games" / "DCS"
            saved_games.mkdir(parents=True)

            builder.install_to_saved_games(variant_path, saved_games)

            # Check installation
            installed = saved_games / "Mods" / "aircraft" / "[VWV] MiG-17_FM6"
            self.assertTrue(installed.exists())
            self.assertTrue((installed / "test.txt").exists())

    def test_install_removes_existing(self) -> None:
        """Existing installation is removed before installing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a variant folder
            variant_path = tmpdir_path / "[VWV] MiG-17_FM6"
            variant_path.mkdir()
            (variant_path / "new.txt").write_text("new content")

            # Create existing installation
            saved_games = tmpdir_path / "Saved Games" / "DCS"
            existing = saved_games / "Mods" / "aircraft" / "[VWV] MiG-17_FM6"
            existing.mkdir(parents=True)
            (existing / "old.txt").write_text("old content")

            builder.install_to_saved_games(variant_path, saved_games)

            # Check new content
            installed = saved_games / "Mods" / "aircraft" / "[VWV] MiG-17_FM6"
            self.assertTrue((installed / "new.txt").exists())
            self.assertFalse((installed / "old.txt").exists())


if __name__ == "__main__":
    unittest.main()
