"""Build MiG-17F flight model variant mod folders from JSON configuration.

This script reads the FM variant definitions from mig17f_fm_variants.json and
generates variant mod folders with appropriately scaled SFM coefficients.

Usage:
    python build_mig17f_variants_from_json.py [options]

Options:
    --base-mod-root PATH      Path to base mod (default: repo root + base_mod_dir from JSON)
    --variants-root PATH      Output directory for variants (default: ./fm_variants)
    --dcs-saved-games PATH    Optional path to DCS Saved Games for installation
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Scales:
    """Scaling factors for SFM coefficients."""

    cx0: float
    polar: float
    engine_drag: float
    pfor: float


@dataclass(frozen=True)
class Variant:
    """FM variant definition loaded from JSON."""

    variant_id: str
    short_name: str
    mod_dir_name: str
    dcs_type_name: str
    shape_username: str
    display_name: str
    scales: Scales
    notes: str


@dataclass
class VariantConfig:
    """Complete configuration loaded from JSON."""

    version: int
    aircraft_id: str
    base_mod_dir: str
    base_display_name: str
    description: str
    variants: list[Variant]


def load_variant_config(json_path: Path) -> VariantConfig:
    """Load and parse the FM variant JSON configuration."""
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    aircraft = data["aircraft"]
    variants = []

    for v in data["variants"]:
        scales = Scales(
            cx0=v["scales"]["cx0"],
            polar=v["scales"]["polar"],
            engine_drag=v["scales"]["engine_drag"],
            pfor=v["scales"]["pfor"],
        )
        variants.append(
            Variant(
                variant_id=v["variant_id"],
                short_name=v["short_name"],
                mod_dir_name=v["mod_dir_name"],
                dcs_type_name=v["dcs_type_name"],
                shape_username=v["shape_username"],
                display_name=v["display_name"],
                scales=scales,
                notes=v.get("notes", ""),
            )
        )

    return VariantConfig(
        version=data["version"],
        aircraft_id=aircraft["id"],
        base_mod_dir=aircraft["base_mod_dir"],
        base_display_name=aircraft["base_display_name"],
        description=aircraft.get("description", ""),
        variants=variants,
    )


def scale_aero_table_data(lua_content: str, scales: Scales) -> str:
    """Apply scaling to aerodynamics.table_data entries.

    Each row in table_data is: { M, Cx0, Cya, B2, B4, Omxmax, Aldop, Cymax }
    We multiply: Cx0 by scales.cx0, B2 and B4 by scales.polar.
    """
    # Pattern to match table rows in aerodynamics.table_data
    # Example: { 0.0,  0.0162  ,       0.0715 ,       0.072   ,       0.010   , ...}
    aero_row_pattern = re.compile(
        r"(\{\s*"
        r"([\d.]+)\s*,\s*"  # M (index 0)
        r")([\d.]+)(\s*,\s*"  # Cx0 (index 1) - scale this
        r"[\d.]+\s*,\s*"  # Cya (index 2)
        r")([\d.]+)(\s*,\s*"  # B2 (index 3) - scale this
        r")([\d.]+)(\s*,\s*"  # B4 (index 4) - scale this
        r"[\d.]+\s*,\s*"  # Omxmax (index 5)
        r"[\d.]+\s*,\s*"  # Aldop (index 6)
        r"[\d.]+\s*\})"  # Cymax (index 7)
    )

    # Find the aerodynamics.table_data section
    aero_start = lua_content.find("aerodynamics")
    if aero_start == -1:
        LOGGER.warning("Could not find aerodynamics section")
        return lua_content

    # Find table_data within aerodynamics
    table_data_start = lua_content.find("table_data", aero_start)
    if table_data_start == -1:
        LOGGER.warning("Could not find table_data in aerodynamics section")
        return lua_content

    # Find the end of the table_data block (look for closing }, --)
    # We need to find the matching closing brace after 'table_data ='
    search_start = lua_content.find("=", table_data_start)
    if search_start == -1:
        return lua_content

    # Find the end of table_data section by looking for '}, -- end of table_data'
    table_data_end = lua_content.find("}, -- end of table_data", search_start)
    if table_data_end == -1:
        # Try alternative pattern
        table_data_end = lua_content.find("end of table_data", search_start)
        if table_data_end == -1:
            # Estimate the end by looking for 'engine' section
            engine_start = lua_content.find("engine", search_start)
            table_data_end = engine_start if engine_start != -1 else len(lua_content)

    aero_section = lua_content[search_start:table_data_end]

    def replace_aero_row(match: re.Match) -> str:
        prefix = match.group(1)  # { M,
        cx0 = float(match.group(3))
        mid1 = match.group(4)  # , Cya,
        b2 = float(match.group(5))
        mid2 = match.group(6)  # ,
        b4 = float(match.group(7))
        suffix = match.group(8)  # , Omxmax, Aldop, Cymax }

        new_cx0 = cx0 * scales.cx0
        new_b2 = b2 * scales.polar
        new_b4 = b4 * scales.polar

        return f"{prefix}{new_cx0:.4f}{mid1}{new_b2:.3f}{mid2}{new_b4:.3f}{suffix}"

    new_aero_section = aero_row_pattern.sub(replace_aero_row, aero_section)
    return lua_content[:search_start] + new_aero_section + lua_content[table_data_end:]


def scale_engine_dcx_eng(lua_content: str, scales: Scales) -> str:
    """Apply scaling to engine.dcx_eng."""
    pattern = re.compile(r"(dcx_eng\s*=\s*)([\d.]+)")

    def replace_dcx_eng(match: re.Match) -> str:
        prefix = match.group(1)
        value = float(match.group(2))
        new_value = value * scales.engine_drag
        return f"{prefix}{new_value:.4f}"

    return pattern.sub(replace_dcx_eng, lua_content)


def scale_engine_pfor(lua_content: str, scales: Scales) -> str:
    """Apply scaling to Pfor values in engine.table_data.

    Each row is: { M, Pmax, Pfor }
    We only multiply Pfor, NOT Pmax.
    """
    # Find the SFM engine section (engine = {) after aerodynamics
    # This is distinct from engines_count, engines_nozzles, etc.
    aero_end = lua_content.find("end of aerodynamics")
    if aero_end == -1:
        LOGGER.warning("Could not find aerodynamics section end")
        return lua_content

    # Find "engine =" or "engine=" after aerodynamics
    engine_match = re.search(r"engine\s*=\s*\{", lua_content[aero_end:])
    if not engine_match:
        LOGGER.warning("Could not find SFM engine section")
        return lua_content

    engine_start = aero_end + engine_match.start()

    # Find table_data within this engine section
    engine_table_match = re.search(r"table_data\s*=", lua_content[engine_start:])
    if not engine_table_match:
        LOGGER.warning("Could not find table_data in engine section")
        return lua_content

    engine_table_start = engine_start + engine_table_match.start()

    # Find the end of the engine table_data
    engine_table_end = lua_content.find("}, -- end of table_data", engine_table_start)
    if engine_table_end == -1:
        engine_table_end = lua_content.find("end of table_data", engine_table_start)
        if engine_table_end == -1:
            end_engine = lua_content.find("end of engine", engine_table_start)
            engine_table_end = end_engine if end_engine != -1 else len(lua_content)

    # Pattern for engine table rows: { M, Pmax, Pfor }
    engine_row_pattern = re.compile(
        r"(\{\s*"
        r"[\d.]+\s*,\s*"  # M
        r"[\d]+\s*,\s*"  # Pmax (do not change)
        r")(\d+)(\s*\})"  # Pfor (scale this)
    )

    table_start = lua_content.find("=", engine_table_start)
    if table_start == -1:
        return lua_content

    engine_section = lua_content[table_start:engine_table_end]

    def replace_pfor(match: re.Match) -> str:
        prefix = match.group(1)
        pfor = int(match.group(2))
        suffix = match.group(3)
        new_pfor = int(round(pfor * scales.pfor))
        return f"{prefix}{new_pfor}{suffix}"

    new_engine_section = engine_row_pattern.sub(replace_pfor, engine_section)
    return lua_content[:table_start] + new_engine_section + lua_content[engine_table_end:]


def patch_identity_fields(lua_content: str, variant: Variant) -> str:
    """Patch the Name, DisplayName, and shape_table_data.username fields."""
    # Patch Name field
    name_pattern = re.compile(r"(Name\s*=\s*['\"])([^'\"]+)(['\"])")
    lua_content = name_pattern.sub(
        rf"\g<1>{variant.dcs_type_name}\g<3>", lua_content, count=1
    )

    # Patch DisplayName field - handle _('...') format with possible internal quotes
    # Original format: DisplayName = _('[VWV] MiG-17F "Fresco C"'),
    # We match from the opening quote to the closing quote before the closing paren
    display_pattern = re.compile(
        r"(DisplayName\s*=\s*_\(['\"])(.+?)(['\"])\)"
    )
    lua_content = display_pattern.sub(
        rf"\g<1>{variant.display_name}\g<3>)", lua_content, count=1
    )

    # Patch shape_table_data[0].username (which appears as 'username' inside the table)
    # Look for username in the shape_table_data section
    shape_start = lua_content.find("shape_table_data")
    if shape_start != -1:
        # Find the first username field after shape_table_data
        username_pattern = re.compile(r"(username\s*=\s*['\"])([^'\"]+)(['\"])")
        # We need to only replace the first occurrence after shape_table_data
        before_shape = lua_content[:shape_start]
        after_shape = lua_content[shape_start:]
        after_shape = username_pattern.sub(
            rf"\g<1>{variant.shape_username}\g<3>", after_shape, count=1
        )
        lua_content = before_shape + after_shape

    return lua_content


def apply_variant_modifications(lua_content: str, variant: Variant) -> str:
    """Apply all modifications for a variant to the Lua content."""
    # First patch identity fields
    lua_content = patch_identity_fields(lua_content, variant)

    # Apply SFM scaling
    lua_content = scale_aero_table_data(lua_content, variant.scales)
    lua_content = scale_engine_dcx_eng(lua_content, variant.scales)
    lua_content = scale_engine_pfor(lua_content, variant.scales)

    return lua_content


def build_variant(
    base_mod_path: Path,
    variant: Variant,
    variants_root: Path,
) -> Path:
    """Build a single variant mod folder.

    Args:
        base_mod_path: Path to the base MiG-17 mod folder
        variant: Variant configuration
        variants_root: Directory to create variant folders in

    Returns:
        Path to the created variant folder
    """
    variant_path = variants_root / variant.mod_dir_name

    # Remove existing variant folder if present
    if variant_path.exists():
        LOGGER.info("Removing existing variant folder: %s", variant_path)
        shutil.rmtree(variant_path)

    # Copy base mod to variant folder
    LOGGER.info("Copying base mod to: %s", variant_path)
    shutil.copytree(base_mod_path, variant_path)

    # Modify Database/mig17f.lua
    lua_path = variant_path / "Database" / "mig17f.lua"
    if not lua_path.exists():
        LOGGER.error("Database/mig17f.lua not found in variant: %s", variant_path)
        return variant_path

    lua_content = lua_path.read_text(encoding="utf-8")
    modified_content = apply_variant_modifications(lua_content, variant)
    lua_path.write_text(modified_content, encoding="utf-8")

    LOGGER.info(
        "Applied scales to %s: cx0=%.2f, polar=%.2f, engine_drag=%.2f, pfor=%.2f",
        variant.short_name,
        variant.scales.cx0,
        variant.scales.polar,
        variant.scales.engine_drag,
        variant.scales.pfor,
    )

    return variant_path


def install_to_saved_games(
    variant_path: Path,
    dcs_saved_games: Path,
) -> None:
    """Install a variant mod folder to DCS Saved Games."""
    mods_path = dcs_saved_games / "Mods" / "aircraft" / variant_path.name

    if mods_path.exists():
        LOGGER.info("Removing existing installation: %s", mods_path)
        shutil.rmtree(mods_path)

    LOGGER.info("Installing to: %s", mods_path)
    shutil.copytree(variant_path, mods_path)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Build MiG-17F FM variant mod folders from JSON configuration"
    )
    parser.add_argument(
        "--base-mod-root",
        type=Path,
        help="Path to base mod folder (default: repo root + base_mod_dir from JSON)",
    )
    parser.add_argument(
        "--variants-root",
        type=Path,
        default=Path("./fm_variants/mods"),
        help="Output directory for variant folders (default: ./fm_variants/mods)",
    )
    parser.add_argument(
        "--dcs-saved-games",
        type=Path,
        help="Path to DCS Saved Games folder for optional installation",
    )
    parser.add_argument(
        "--json-file",
        type=Path,
        default=Path("./fm_variants/mig17f_fm_variants.json"),
        help="Path to FM variants JSON (default: ./fm_variants/mig17f_fm_variants.json)",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    args = parse_args()

    # Resolve paths
    json_path = args.json_file.resolve()
    variants_root = args.variants_root.resolve()
    variants_root.mkdir(parents=True, exist_ok=True)

    if not json_path.exists():
        LOGGER.error("FM variants JSON not found: %s", json_path)
        return 1

    LOGGER.info("Loading variant configuration from: %s", json_path)
    config = load_variant_config(json_path)
    LOGGER.info("Found %d variants to build", len(config.variants))

    # Resolve base mod path
    base_mod_path = args.base_mod_root
    if not base_mod_path:
        # Default to repo root + base_mod_dir from JSON
        repo_root = json_path.parent.parent
        base_mod_path = repo_root / config.base_mod_dir

    base_mod_path = base_mod_path.resolve()

    if not base_mod_path.exists():
        LOGGER.error("Base mod not found: %s", base_mod_path)
        return 1

    LOGGER.info("Base mod path: %s", base_mod_path)
    LOGGER.info("Variants output: %s", variants_root)

    # Build each variant
    built_variants: list[Path] = []
    for variant in config.variants:
        LOGGER.info("Building variant: %s (%s)", variant.short_name, variant.variant_id)
        variant_path = build_variant(base_mod_path, variant, variants_root)
        built_variants.append(variant_path)
        LOGGER.info("  Created: %s", variant_path)

    # Optional installation to Saved Games
    if args.dcs_saved_games:
        dcs_saved_games = args.dcs_saved_games.resolve()
        if not dcs_saved_games.exists():
            LOGGER.warning("DCS Saved Games path does not exist: %s", dcs_saved_games)
        else:
            LOGGER.info("Installing variants to DCS Saved Games: %s", dcs_saved_games)
            for variant_path in built_variants:
                install_to_saved_games(variant_path, dcs_saved_games)
            LOGGER.info("Installation complete")

    # Summary
    LOGGER.info("=" * 60)
    LOGGER.info("Build Summary")
    LOGGER.info("=" * 60)
    LOGGER.info("Variants built: %d", len(built_variants))
    for path in built_variants:
        LOGGER.info("  - %s", path.name)
    if args.dcs_saved_games:
        LOGGER.info("Installed to: %s", args.dcs_saved_games)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
