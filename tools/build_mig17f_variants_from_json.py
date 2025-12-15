"""Build MiG-17F flight model variant mod folders from JSON configuration.

This script reads FM variant definitions from a JSON file and generates *variant*
mod folders with appropriately scaled SFM coefficients (SFM_Data).

It is intentionally lightweight and uses simple text/regex patching against the
baseline mod's `Database/mig17f.lua` and `entry.lua`.

Usage:
    python build_mig17f_variants_from_json.py [options]

Options:
    --base-mod-root PATH      Path to base mod folder (default: repo root + base_mod_dir from JSON)
    --variants-root PATH      Output directory for variants (default: ./fm_variants/mods)
    --dcs-saved-games PATH    Optional path to DCS Saved Games for installation
    --json-file PATH          Path to the variants JSON (default: ./fm_variants/mig17f_fm_variants.json)

JSON schema (high level):
    {
      "version": <int>,
      "aircraft": { ... },
      "variants": [
        {
          "variant_id": "...",
          "short_name": "...",
          "mod_dir_name": "...",
          "dcs_type_name": "...",
          "shape_username": "...",
          "display_name": "...",
          "scales": { ... },
          "notes": "..."
        }
      ]
    }

Notes:
- Identity fields (Name/DisplayName/shape username + entry.lua IDs) are always
  patched so each variant can coexist in DCS.
- Numeric FM patches are only applied when the corresponding scale differs from
  baseline (1.0) to avoid rewriting baseline numbers due to formatting/rounding.
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


# Mach thresholds for high-AoA scaling (polar_high_aoa applies for 0.2 <= M <= 0.8)
HIGH_AOA_MACH_MIN = 0.2
HIGH_AOA_MACH_MAX = 0.8
# Legacy threshold for cymax_high_aoa (M < 0.5)
CYMAX_HIGH_AOA_MACH_THRESHOLD = 0.5


def _is_close(a: float, b: float = 1.0, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def _format_scaled_value(new_value: float, original_text: str) -> str:
    """Format a scaled numeric value in a way that preserves the *style* of the original.

    - If the original looks like an int (no '.', 'e', 'E'), emit an int.
    - Otherwise, preserve the original number of decimal places (up to 6).
    """
    if re.search(r"[.eE]", original_text):
        if "." in original_text:
            decimals = len(original_text.split(".", 1)[1])
            decimals = max(0, min(decimals, 6))
            return f"{new_value:.{decimals}f}"
        return str(new_value)
    return str(int(round(new_value)))


@dataclass(frozen=True)
class Scales:
    """Scaling factors for SFM coefficients.

    All multipliers apply relative to the *baseline mod* you are copying.
    """

    # Aerodynamics
    cx0: float = 1.0
    polar: float = 1.0
    polar_high_aoa: float = 1.0  # extra B4 multiplier at Mach 0.2-0.8 (high-AoA drag regime)
    cymax_high_aoa: float = 1.0  # Cymax multiplier at low Mach (<0.5)
    cymax: float = 1.0  # global Cymax multiplier (all Mach numbers)
    aldop: float = 1.0  # Aldop (departure AoA) multiplier

    # Engine / thrust
    engine_drag: float = 1.0  # dcx_eng multiplier
    pmax: float = 1.0  # military thrust multiplier (Pmax column)
    pfor: float = 1.0  # afterburner thrust multiplier (Pfor column)
    dpdh_m_scale: float = 1.0  # dpdh_m multiplier (mil altitude lapse)
    dpdh_f_scale: float = 1.0  # dpdh_f multiplier (AB altitude lapse)

    # AI limits
    ny_max_abs: Optional[float] = None  # absolute Ny_max/Ny_max_e override (not a scale)
    flaps_maneuver_scale: float = 1.0  # flaps_maneuver multiplier


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
    variants: list[Variant] = []

    for v in data["variants"]:
        s = v.get("scales", {})
        scales = Scales(
            cx0=s.get("cx0", 1.0),
            polar=s.get("polar", 1.0),
            polar_high_aoa=s.get("polar_high_aoa", 1.0),
            cymax_high_aoa=s.get("cymax_high_aoa", 1.0),
            cymax=s.get("cymax", 1.0),
            aldop=s.get("aldop", 1.0),
            engine_drag=s.get("engine_drag", 1.0),
            pmax=s.get("pmax", 1.0),
            pfor=s.get("pfor", 1.0),
            dpdh_m_scale=s.get("dpdh_m_scale", 1.0),
            dpdh_f_scale=s.get("dpdh_f_scale", 1.0),
            ny_max_abs=s.get("ny_max_abs"),
            flaps_maneuver_scale=s.get("flaps_maneuver_scale", 1.0),
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


def _should_scale_aero(scales: Scales) -> bool:
    return not (
        _is_close(scales.cx0)
        and _is_close(scales.polar)
        and _is_close(scales.polar_high_aoa)
        and _is_close(scales.cymax)
        and _is_close(scales.cymax_high_aoa)
        and _is_close(scales.aldop)
    )


def _should_scale_engine_drag(scales: Scales) -> bool:
    return not _is_close(scales.engine_drag)


def _should_scale_engine_thrust(scales: Scales) -> bool:
    return not (_is_close(scales.pmax) and _is_close(scales.pfor))


def _should_scale_engine_dpdh(scales: Scales) -> bool:
    return not (_is_close(scales.dpdh_m_scale) and _is_close(scales.dpdh_f_scale))


def scale_aero_table_data(lua_content: str, scales: Scales) -> str:
    """Apply scaling to aerodynamics.table_data entries.

    Each row in table_data is:
        { M, Cx0, Cya, B2, B4, Omxmax, Aldop, Cymax }

    We multiply:
    - Cx0 by scales.cx0
    - B2 by scales.polar
    - B4 by scales.polar (and additionally by scales.polar_high_aoa at Mach 0.2-0.8)
    - Aldop by scales.aldop
    - Cymax by scales.cymax (and additionally by scales.cymax_high_aoa at low Mach)

    NOTE: This routine rewrites numeric formatting. Call it only when you are
    actually changing something (see _should_scale_aero).
    """

    aero_row_pattern = re.compile(
        r"(\{\s*)"
        r"([\d.]+)(\s*,\s*)"  # M (group 2)
        r"([\d.]+)(\s*,\s*)"  # Cx0 (group 4)
        r"([\d.]+)(\s*,\s*)"  # Cya (group 6)
        r"([\d.]+)(\s*,\s*)"  # B2 (group 8)
        r"([\d.]+)(\s*,\s*)"  # B4 (group 10)
        r"([\d.]+)(\s*,\s*)"  # Omxmax (group 12)
        r"([\d.]+)(\s*,\s*)"  # Aldop (group 14)
        r"([\d.]+)(\s*\})"  # Cymax (group 16)
    )

    aero_start = lua_content.find("aerodynamics")
    if aero_start == -1:
        LOGGER.warning("Could not find aerodynamics section")
        return lua_content

    table_data_start = lua_content.find("table_data", aero_start)
    if table_data_start == -1:
        LOGGER.warning("Could not find table_data in aerodynamics section")
        return lua_content

    search_start = lua_content.find("=", table_data_start)
    if search_start == -1:
        return lua_content

    table_data_end = lua_content.find("}, -- end of table_data", search_start)
    if table_data_end == -1:
        table_data_end = lua_content.find("end of table_data", search_start)
        if table_data_end == -1:
            engine_start = lua_content.find("engine", search_start)
            table_data_end = engine_start if engine_start != -1 else len(lua_content)

    aero_section = lua_content[search_start:table_data_end]

    def replace_aero_row(match: re.Match) -> str:
        brace_open = match.group(1)
        mach = float(match.group(2))
        sep1 = match.group(3)
        cx0 = float(match.group(4))
        sep2 = match.group(5)
        cya_txt = match.group(6)
        sep3 = match.group(7)
        b2 = float(match.group(8))
        sep4 = match.group(9)
        b4 = float(match.group(10))
        sep5 = match.group(11)
        omx_txt = match.group(12)
        sep6 = match.group(13)
        aldop = float(match.group(14))
        sep7 = match.group(15)
        cymax = float(match.group(16))
        brace_close = match.group(17)

        new_cx0 = cx0 * scales.cx0
        new_b2 = b2 * scales.polar
        new_b4 = b4 * scales.polar
        new_aldop = aldop * scales.aldop
        new_cymax = cymax * scales.cymax

        if HIGH_AOA_MACH_MIN <= mach <= HIGH_AOA_MACH_MAX:
            new_b4 *= scales.polar_high_aoa

        if mach < CYMAX_HIGH_AOA_MACH_THRESHOLD:
            new_cymax *= scales.cymax_high_aoa

        # Keep formatting stable-ish (same as previous versions of this tool)
        return (
            f"{brace_open}{mach}{sep1}"
            f"{new_cx0:.4f}{sep2}"
            f"{cya_txt}{sep3}"
            f"{new_b2:.3f}{sep4}"
            f"{new_b4:.3f}{sep5}"
            f"{omx_txt}{sep6}"
            f"{new_aldop:.1f}{sep7}"
            f"{new_cymax:.2f}{brace_close}"
        )

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

    return pattern.sub(replace_dcx_eng, lua_content, count=1)


def _find_sfm_engine_start(lua_content: str) -> int:
    """Find the start index of the SFM_Data.engine = { ... } block."""
    aero_end = lua_content.find("end of aerodynamics")
    if aero_end == -1:
        return -1

    engine_match = re.search(r"engine\s*=\s*\{", lua_content[aero_end:])
    if not engine_match:
        return -1

    return aero_end + engine_match.start()


def _find_sfm_engine_end(lua_content: str, engine_start: int) -> int:
    """Best-effort end index for SFM engine section."""
    if engine_start < 0:
        return -1

    end_marker = lua_content.find("}, -- end of engine", engine_start)
    if end_marker != -1:
        return end_marker

    end_marker = lua_content.find("end of engine", engine_start)
    if end_marker != -1:
        return end_marker

    return len(lua_content)


def _find_engine_table_bounds(lua_content: str, engine_start: int) -> tuple[int, int] | None:
    """Return (table_start_idx, table_end_idx) covering the engine.table_data content.

    The returned slice is suitable for re.sub on table rows.
    """
    if engine_start < 0:
        return None

    engine_table_match = re.search(r"table_data\s*=", lua_content[engine_start:])
    if not engine_table_match:
        return None

    engine_table_start = engine_start + engine_table_match.start()

    engine_table_end = lua_content.find("}, -- end of table_data", engine_table_start)
    if engine_table_end == -1:
        engine_table_end = lua_content.find("end of table_data", engine_table_start)
        if engine_table_end == -1:
            end_engine = lua_content.find("end of engine", engine_table_start)
            engine_table_end = end_engine if end_engine != -1 else len(lua_content)

    table_start = lua_content.find("=", engine_table_start)
    if table_start == -1:
        return None

    return table_start, engine_table_end


def scale_engine_thrust_table(lua_content: str, scales: Scales) -> str:
    """Apply scaling to Pmax and Pfor values in SFM engine.table_data.

    Each row is:
        { M, Pmax, Pfor }

    We multiply:
    - Pmax by scales.pmax
    - Pfor by scales.pfor

    NOTE: This routine rewrites numeric formatting. Call it only when you are
    actually changing something (see _should_scale_engine_thrust).
    """
    engine_start = _find_sfm_engine_start(lua_content)
    if engine_start == -1:
        LOGGER.warning("Could not find SFM engine section")
        return lua_content

    bounds = _find_engine_table_bounds(lua_content, engine_start)
    if not bounds:
        LOGGER.warning("Could not find engine.table_data")
        return lua_content

    table_start, table_end = bounds
    engine_section = lua_content[table_start:table_end]

    engine_row_pattern = re.compile(
        r"(\{\s*)"
        r"([\d.]+)(\s*,\s*)"  # M
        r"([\d.]+)(\s*,\s*)"  # Pmax
        r"([\d.]+)(\s*\})"  # Pfor
    )

    def replace_row(match: re.Match) -> str:
        brace_open = match.group(1)
        mach_txt = match.group(2)
        sep1 = match.group(3)
        pmax_txt = match.group(4)
        sep2 = match.group(5)
        pfor_txt = match.group(6)
        brace_close = match.group(7)

        pmax_val = float(pmax_txt)
        pfor_val = float(pfor_txt)

        new_pmax = pmax_val * scales.pmax
        new_pfor = pfor_val * scales.pfor

        return (
            f"{brace_open}{mach_txt}{sep1}"
            f"{_format_scaled_value(new_pmax, pmax_txt)}{sep2}"
            f"{_format_scaled_value(new_pfor, pfor_txt)}{brace_close}"
        )

    new_engine_section = engine_row_pattern.sub(replace_row, engine_section)
    return lua_content[:table_start] + new_engine_section + lua_content[table_end:]


def scale_engine_dpdh(lua_content: str, scales: Scales) -> str:
    """Scale dpdh_m and dpdh_f inside the SFM engine section.

    dpdh_m: altitude coefficient for max/mil thrust
    dpdh_f: altitude coefficient for AB thrust

    NOTE: Only call when dpdh_*_scale differs from 1.0.
    """
    engine_start = _find_sfm_engine_start(lua_content)
    if engine_start == -1:
        LOGGER.warning("Could not find SFM engine section")
        return lua_content

    engine_end = _find_sfm_engine_end(lua_content, engine_start)
    if engine_end == -1:
        return lua_content

    engine_section = lua_content[engine_start:engine_end]

    def repl_dpdh_m(match: re.Match) -> str:
        prefix = match.group(1)
        orig_txt = match.group(2)
        orig_val = float(orig_txt)
        new_val = orig_val * scales.dpdh_m_scale
        return f"{prefix}{_format_scaled_value(new_val, orig_txt)}"

    def repl_dpdh_f(match: re.Match) -> str:
        prefix = match.group(1)
        orig_txt = match.group(2)
        orig_val = float(orig_txt)
        new_val = orig_val * scales.dpdh_f_scale
        return f"{prefix}{_format_scaled_value(new_val, orig_txt)}"

    # Only patch first occurrence within engine section
    engine_section = re.sub(r"(dpdh_m\s*=\s*)([-\d.]+)", repl_dpdh_m, engine_section, count=1)
    engine_section = re.sub(r"(dpdh_f\s*=\s*)([-\d.]+)", repl_dpdh_f, engine_section, count=1)

    return lua_content[:engine_start] + engine_section + lua_content[engine_end:]


def patch_ny_max(lua_content: str, scales: Scales) -> str:
    """Patch Ny_max and Ny_max_e to absolute values if ny_max_abs is set."""
    if scales.ny_max_abs is None:
        return lua_content

    ny_max_value = scales.ny_max_abs

    ny_max_pattern = re.compile(r"(Ny_max\s*=\s*)([\d.]+)")
    lua_content = ny_max_pattern.sub(rf"\g<1>{ny_max_value}", lua_content, count=1)

    ny_max_e_pattern = re.compile(r"(Ny_max_e\s*=\s*)([\d.]+)")
    lua_content = ny_max_e_pattern.sub(rf"\g<1>{ny_max_value}", lua_content, count=1)

    return lua_content


def scale_flaps_maneuver(lua_content: str, scales: Scales) -> str:
    """Scale the flaps_maneuver value by flaps_maneuver_scale."""
    if _is_close(scales.flaps_maneuver_scale):
        return lua_content

    pattern = re.compile(r"(flaps_maneuver\s*=\s*)([\d.]+)")

    def replace_flaps_maneuver(match: re.Match) -> str:
        prefix = match.group(1)
        value = float(match.group(2))
        new_value = value * scales.flaps_maneuver_scale
        return f"{prefix}{new_value:.2f}"

    return pattern.sub(replace_flaps_maneuver, lua_content, count=1)


def patch_entry_lua(entry_content: str, variant: Variant) -> str:
    """Patch entry.lua with unique identifiers for this variant."""
    variant_suffix = variant.dcs_type_name.split("_")[-1]

    entry_content = re.sub(
        r'(self_ID\s*=\s*["\'])([^"\']+)(["\'])',
        rf'\g<1>\g<2>_{variant_suffix}\g<3>',
        entry_content,
    )

    entry_content = re.sub(
        r'(displayName\s*=\s*_\(["\'])([^"\']+)(["\'])',
        rf'\g<1>{variant.display_name}\g<3>',
        entry_content,
    )

    entry_content = re.sub(
        r'(fileMenuName\s*=\s*_\(["\'])([^"\']+)(["\'])',
        rf'\g<1>{variant.short_name} MiG-17F\g<3>',
        entry_content,
    )

    entry_content = re.sub(
        r'(update_id\s*=\s*["\'])([^"\']+)(["\'])',
        rf'\g<1>\g<2>_{variant_suffix}\g<3>',
        entry_content,
    )

    entry_content = re.sub(
        r'(LogBook\s*=\s*\{\s*\{\s*[^}]*type\s*=\s*["\'])([^"\']+)(["\'])',
        rf'\g<1>\g<2>_{variant_suffix}\g<3>',
        entry_content,
        flags=re.DOTALL,
    )

    return entry_content


def patch_identity_fields(lua_content: str, variant: Variant) -> str:
    """Patch the Name, DisplayName, and shape_table_data.username fields."""
    name_pattern = re.compile(r"(Name\s*=\s*['\"])([^'\"]+)(['\"])")
    lua_content = name_pattern.sub(rf"\g<1>{variant.dcs_type_name}\g<3>", lua_content, count=1)

    display_pattern = re.compile(r"(DisplayName\s*=\s*_\(['\"])(.+?)(['\"]\)\s*,)")
    lua_content = display_pattern.sub(rf"\g<1>{variant.display_name}\g<3>", lua_content, count=1)

    shape_start = lua_content.find("shape_table_data")
    if shape_start != -1:
        username_pattern = re.compile(r"(username\s*=\s*['\"])([^'\"]+)(['\"])")
        before_shape = lua_content[:shape_start]
        after_shape = lua_content[shape_start:]
        after_shape = username_pattern.sub(rf"\g<1>{variant.shape_username}\g<3>", after_shape, count=1)
        lua_content = before_shape + after_shape

    return lua_content


def apply_variant_modifications(lua_content: str, variant: Variant) -> str:
    """Apply all modifications for a variant to the Lua content."""
    scales = variant.scales

    # Always patch identity fields (so DCS sees distinct aircraft types)
    lua_content = patch_identity_fields(lua_content, variant)

    # Only patch numeric FM data when needed (avoid baseline rewrites)
    if _should_scale_aero(scales):
        lua_content = scale_aero_table_data(lua_content, scales)

    if _should_scale_engine_drag(scales):
        lua_content = scale_engine_dcx_eng(lua_content, scales)

    if _should_scale_engine_thrust(scales):
        lua_content = scale_engine_thrust_table(lua_content, scales)

    if _should_scale_engine_dpdh(scales):
        lua_content = scale_engine_dpdh(lua_content, scales)

    if scales.ny_max_abs is not None:
        lua_content = patch_ny_max(lua_content, scales)

    if not _is_close(scales.flaps_maneuver_scale):
        lua_content = scale_flaps_maneuver(lua_content, scales)

    return lua_content


def build_variant(base_mod_path: Path, variant: Variant, variants_root: Path) -> Path:
    """Build a single variant mod folder."""
    variant_path = variants_root / variant.mod_dir_name

    if variant_path.exists():
        LOGGER.info("Removing existing variant folder: %s", variant_path)
        shutil.rmtree(variant_path)

    LOGGER.info("Copying base mod to: %s", variant_path)
    shutil.copytree(base_mod_path, variant_path)

    lua_path = variant_path / "Database" / "mig17f.lua"
    if not lua_path.exists():
        LOGGER.error("Database/mig17f.lua not found in variant: %s", variant_path)
        return variant_path

    lua_content = lua_path.read_text(encoding="utf-8")
    modified_content = apply_variant_modifications(lua_content, variant)
    lua_path.write_text(modified_content, encoding="utf-8")

    entry_path = variant_path / "entry.lua"
    if entry_path.exists():
        entry_content = entry_path.read_text(encoding="utf-8")
        modified_entry = patch_entry_lua(entry_content, variant)
        entry_path.write_text(modified_entry, encoding="utf-8")
        LOGGER.info("Patched entry.lua with unique IDs for %s", variant.short_name)
    else:
        LOGGER.warning("entry.lua not found in variant: %s", variant_path)

    s = variant.scales
    LOGGER.info(
        "Applied scales to %s: cx0=%.3f polar=%.3f polar_high_aoa=%.3f cymax=%.3f cymax_high_aoa=%.3f aldop=%.3f "
        "engine_drag=%.3f pmax=%.3f pfor=%.3f dpdh_m_scale=%.3f dpdh_f_scale=%.3f ny_max_abs=%s flaps_maneuver_scale=%.3f",
        variant.short_name,
        s.cx0,
        s.polar,
        s.polar_high_aoa,
        s.cymax,
        s.cymax_high_aoa,
        s.aldop,
        s.engine_drag,
        s.pmax,
        s.pfor,
        s.dpdh_m_scale,
        s.dpdh_f_scale,
        s.ny_max_abs,
        s.flaps_maneuver_scale,
    )

    return variant_path


def install_to_saved_games(variant_path: Path, dcs_saved_games: Path) -> None:
    """Install a variant mod folder to DCS Saved Games."""
    mods_path = dcs_saved_games / "Mods" / "aircraft" / variant_path.name

    if mods_path.exists():
        LOGGER.info("Removing existing installation: %s", mods_path)
        shutil.rmtree(mods_path)

    LOGGER.info("Installing to: %s", mods_path)
    shutil.copytree(variant_path, mods_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MiG-17F FM variant mod folders from JSON configuration")
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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    args = parse_args()

    json_path = args.json_file.resolve()
    variants_root = args.variants_root.resolve()
    variants_root.mkdir(parents=True, exist_ok=True)

    if not json_path.exists():
        LOGGER.error("FM variants JSON not found: %s", json_path)
        return 1

    LOGGER.info("Loading variant configuration from: %s", json_path)
    config = load_variant_config(json_path)
    LOGGER.info("Found %d variants to build", len(config.variants))

    base_mod_path = args.base_mod_root
    if not base_mod_path:
        repo_root = json_path.parent.parent
        base_mod_path = repo_root / config.base_mod_dir

    base_mod_path = base_mod_path.resolve()

    if not base_mod_path.exists():
        LOGGER.error("Base mod not found: %s", base_mod_path)
        return 1

    LOGGER.info("Base mod path: %s", base_mod_path)
    LOGGER.info("Variants output: %s", variants_root)

    built_variants: list[Path] = []
    for variant in config.variants:
        LOGGER.info("Building variant: %s (%s)", variant.short_name, variant.variant_id)
        variant_path = build_variant(base_mod_path, variant, variants_root)
        built_variants.append(variant_path)
        LOGGER.info("  Created: %s", variant_path)

    if args.dcs_saved_games:
        dcs_saved_games = args.dcs_saved_games.resolve()
        if not dcs_saved_games.exists():
            LOGGER.warning("DCS Saved Games path does not exist: %s", dcs_saved_games)
        else:
            LOGGER.info("Installing variants to DCS Saved Games: %s", dcs_saved_games)
            for variant_path in built_variants:
                install_to_saved_games(variant_path, dcs_saved_games)
            LOGGER.info("Installation complete")

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
