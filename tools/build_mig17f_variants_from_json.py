#!/usr/bin/env python3
"""
build_mig17f_variants_from_json.py (v2 - schema_version 2)

Build MiG-17F (or similar SFM-based) flight model variant mod folders from a JSON
configuration.

Why v2:
- Fixes missing/partial application of engine knobs (Pmax + dpdh_m/dpdh_f were
  present in JSON but not actually patched in older versions).
- Expands the sweep surface area without requiring future code changes:
  - Separate scaling for Cx0 / Cya / B2 / B4 / Omxmax / Aldop / Cymax.
  - Extra Mach-window multipliers for B4:
      * polar_high_aoa   for 0.20 <= M <= 0.80
      * polar_transonic  for M >= 0.85
  - Engine table scaling for BOTH Pmax and Pfor.
  - Engine scalar parameters: dcx_eng, cemax, cefor, dpdh_m, dpdh_f.
  - Optional top-level mass + AI limiter scaling (M_empty, Vy_max, Mach_max, etc).

JSON schema:
- Supports the legacy "schema_version 1" flat scales (cx0, polar, engine_drag, ...)
- Supports "schema_version 2" expanded flat scales:
    cx0, cya, polar_b2, polar_b4, polar_high_aoa, polar_transonic,
    cymax, cymax_high_aoa, aldop, omxmax,
    engine_drag, cemax, cefor,
    pmax, pfor, dpdh_m_scale, dpdh_f_scale,
    ny_max_abs, flaps_maneuver_scale, vy_max_scale, mach_max_scale,
    thrust_sum_max_scale, thrust_sum_ab_scale,
    m_empty_scale, m_nominal_scale, m_max_scale, m_fuel_max_scale

Usage:
  python build_mig17f_variants_from_json.py --json-file flight_models.json

Optional installation:
  python build_mig17f_variants_from_json.py --dcs-saved-games "C:/Users/.../Saved Games/DCS"
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)

# Robust float/int matcher (supports scientific notation too)
NUM_RE = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

# Default Mach windows for special scaling
HIGH_AOA_MACH_MIN = 0.20
HIGH_AOA_MACH_MAX = 0.80
TRANSONIC_MACH_MIN = 0.85
CYMAX_LOW_MACH_THRESHOLD = 0.50


# ---------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Scales:
    # Aerodynamics.table_data columns:
    cx0: float = 1.0
    cya: float = 1.0
    polar_b2: float = 1.0
    polar_b4: float = 1.0
    omxmax: float = 1.0
    aldop: float = 1.0
    cymax: float = 1.0

    # Mach-window extras:
    polar_high_aoa: float = 1.0
    polar_transonic: float = 1.0
    cymax_high_aoa: float = 1.0

    # Engine scalars:
    engine_drag: float = 1.0  # dcx_eng
    cemax: float = 1.0
    cefor: float = 1.0
    dpdh_m_scale: float = 1.0
    dpdh_f_scale: float = 1.0

    # Engine thrust table:
    pmax: float = 1.0
    pfor: float = 1.0

    # Top-level AI/limits:
    ny_max_abs: Optional[float] = None
    flaps_maneuver_scale: float = 1.0
    vy_max_scale: float = 1.0
    mach_max_scale: float = 1.0
    thrust_sum_max_scale: float = 1.0
    thrust_sum_ab_scale: float = 1.0

    # Top-level weights:
    m_empty_scale: float = 1.0
    m_nominal_scale: float = 1.0
    m_max_scale: float = 1.0
    m_fuel_max_scale: float = 1.0

    # -----------------------------------------------------------------
    # Additional SFM scalar knobs found in the baseline mig17f.lua
    # -----------------------------------------------------------------
    # SFM_Data.aerodynamics scalars:
    cy0_scale: float = 1.0
    mzalfa_scale: float = 1.0
    mzalfadt_scale: float = 1.0
    czbe_scale: float = 1.0
    kjx_scale: float = 1.0
    kjz_scale: float = 1.0
    cx_gear_scale: float = 1.0
    cx_flap_scale: float = 1.0
    cy_flap_scale: float = 1.0
    cx_brk_scale: float = 1.0

    # SFM_Data.engine scalars:
    hmaxeng_scale: float = 1.0
    nominal_rpm_scale: float = 1.0
    nmg_scale: float = 1.0
    startup_prework_scale: float = 1.0
    startup_duration_scale: float = 1.0
    shutdown_duration_scale: float = 1.0

    # Rudder limits (inside SFM_Data.engine):
    minrud_scale: float = 1.0
    maxrud_scale: float = 1.0
    maksrud_scale: float = 1.0
    forsrud_scale: float = 1.0

    # Top-level AI/perf knobs:
    ny_min_abs: Optional[float] = None
    aoa_take_off_scale: float = 1.0
    bank_angle_max_scale: float = 1.0
    cas_min_scale: float = 1.0
    v_opt_kmh_scale: float = 1.0
    vmax_sea_level_kmh_scale: float = 1.0
    vmax_h_kmh_scale: float = 1.0
    v_take_off_scale: float = 1.0
    v_land_scale: float = 1.0
    range_scale: float = 1.0
    avg_fuel_consumption_scale: float = 1.0
    wing_area_scale: float = 1.0
    wing_span_scale: float = 1.0
    wing_type_abs: Optional[int] = None
    h_max_scale: float = 1.0


@dataclass(frozen=True)
class Variant:
    variant_id: str
    short_name: str
    mod_dir_name: str
    dcs_type_name: str
    shape_username: str
    display_name: str
    scales: Scales
    notes: str = ""


@dataclass(frozen=True)
class VariantConfig:
    version: int
    schema_version: int
    description: str
    aircraft_id: str
    base_mod_dir: str
    base_display_name: str
    flight_model_lua: str
    entry_lua: str
    variants: list[Variant]


# ---------------------------------------------------------------------
# JSON loading (backwards compatible)
# ---------------------------------------------------------------------

def _get(d: Dict[str, Any], key: str, default: Any) -> Any:
    v = d.get(key, default)
    return default if v is None else v


def load_variant_config(json_path: Path) -> VariantConfig:
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    schema_version = int(data.get("schema_version", 1))
    aircraft = data["aircraft"]

    base_mod_dir = aircraft["base_mod_dir"]
    flight_model_lua = aircraft.get("flight_model_lua", "Database/mig17f.lua")
    entry_lua = aircraft.get("entry_lua", "entry.lua")

    variants: list[Variant] = []
    for v in data["variants"]:
        s = v.get("scales", {})

        # Legacy compatibility:
        # - "polar" -> polar_b2 & polar_b4
        # - "engine_drag" -> engine_drag
        # - "pfor" -> pfor
        polar_legacy = s.get("polar")
        polar_b2 = _get(s, "polar_b2", polar_legacy if polar_legacy is not None else 1.0)
        polar_b4 = _get(s, "polar_b4", polar_legacy if polar_legacy is not None else 1.0)

        scales = Scales(
            cx0=float(_get(s, "cx0", 1.0)),
            cya=float(_get(s, "cya", 1.0)),
            polar_b2=float(polar_b2),
            polar_b4=float(polar_b4),
            omxmax=float(_get(s, "omxmax", 1.0)),
            aldop=float(_get(s, "aldop", 1.0)),
            cymax=float(_get(s, "cymax", 1.0)),
            polar_high_aoa=float(_get(s, "polar_high_aoa", 1.0)),
            polar_transonic=float(_get(s, "polar_transonic", 1.0)),
            cymax_high_aoa=float(_get(s, "cymax_high_aoa", 1.0)),
            engine_drag=float(_get(s, "engine_drag", 1.0)),
            cemax=float(_get(s, "cemax", 1.0)),
            cefor=float(_get(s, "cefor", 1.0)),
            dpdh_m_scale=float(_get(s, "dpdh_m_scale", 1.0)),
            dpdh_f_scale=float(_get(s, "dpdh_f_scale", 1.0)),
            pmax=float(_get(s, "pmax", 1.0)),
            pfor=float(_get(s, "pfor", _get(s, "pfor", 1.0))),  # tolerate old "pfor"
            ny_max_abs=s.get("ny_max_abs", None),
            flaps_maneuver_scale=float(_get(s, "flaps_maneuver_scale", 1.0)),
            vy_max_scale=float(_get(s, "vy_max_scale", 1.0)),
            mach_max_scale=float(_get(s, "mach_max_scale", 1.0)),
            thrust_sum_max_scale=float(_get(s, "thrust_sum_max_scale", 1.0)),
            thrust_sum_ab_scale=float(_get(s, "thrust_sum_ab_scale", 1.0)),
            m_empty_scale=float(_get(s, "m_empty_scale", 1.0)),
            m_nominal_scale=float(_get(s, "m_nominal_scale", 1.0)),
            m_max_scale=float(_get(s, "m_max_scale", 1.0)),
            m_fuel_max_scale=float(_get(s, "m_fuel_max_scale", 1.0)),
            cy0_scale=float(_get(s, "cy0_scale", 1.0)),
            mzalfa_scale=float(_get(s, "mzalfa_scale", 1.0)),
            mzalfadt_scale=float(_get(s, "mzalfadt_scale", 1.0)),
            czbe_scale=float(_get(s, "czbe_scale", 1.0)),
            kjx_scale=float(_get(s, "kjx_scale", 1.0)),
            kjz_scale=float(_get(s, "kjz_scale", 1.0)),
            cx_gear_scale=float(_get(s, "cx_gear_scale", 1.0)),
            cx_flap_scale=float(_get(s, "cx_flap_scale", 1.0)),
            cy_flap_scale=float(_get(s, "cy_flap_scale", 1.0)),
            cx_brk_scale=float(_get(s, "cx_brk_scale", 1.0)),
            hmaxeng_scale=float(_get(s, "hmaxeng_scale", 1.0)),
            nominal_rpm_scale=float(_get(s, "nominal_rpm_scale", 1.0)),
            nmg_scale=float(_get(s, "nmg_scale", 1.0)),
            startup_prework_scale=float(_get(s, "startup_prework_scale", 1.0)),
            startup_duration_scale=float(_get(s, "startup_duration_scale", 1.0)),
            shutdown_duration_scale=float(_get(s, "shutdown_duration_scale", 1.0)),
            minrud_scale=float(_get(s, "minrud_scale", 1.0)),
            maxrud_scale=float(_get(s, "maxrud_scale", 1.0)),
            maksrud_scale=float(_get(s, "maksrud_scale", 1.0)),
            forsrud_scale=float(_get(s, "forsrud_scale", 1.0)),
            ny_min_abs=s.get("ny_min_abs", None),
            aoa_take_off_scale=float(_get(s, "aoa_take_off_scale", 1.0)),
            bank_angle_max_scale=float(_get(s, "bank_angle_max_scale", 1.0)),
            cas_min_scale=float(_get(s, "cas_min_scale", 1.0)),
            v_opt_kmh_scale=float(_get(s, "v_opt_kmh_scale", 1.0)),
            vmax_sea_level_kmh_scale=float(_get(s, "vmax_sea_level_kmh_scale", 1.0)),
            vmax_h_kmh_scale=float(_get(s, "vmax_h_kmh_scale", 1.0)),
            v_take_off_scale=float(_get(s, "v_take_off_scale", 1.0)),
            v_land_scale=float(_get(s, "v_land_scale", 1.0)),
            range_scale=float(_get(s, "range_scale", 1.0)),
            avg_fuel_consumption_scale=float(_get(s, "avg_fuel_consumption_scale", 1.0)),
            wing_area_scale=float(_get(s, "wing_area_scale", 1.0)),
            wing_span_scale=float(_get(s, "wing_span_scale", 1.0)),
            wing_type_abs=s.get("wing_type_abs", None),
            h_max_scale=float(_get(s, "h_max_scale", 1.0)),
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
        version=int(data["version"]),
        schema_version=schema_version,
        description=data.get("description", ""),
        aircraft_id=aircraft["id"],
        base_mod_dir=base_mod_dir,
        base_display_name=aircraft.get("base_display_name", ""),
        flight_model_lua=flight_model_lua,
        entry_lua=entry_lua,
        variants=variants,
    )


# ---------------------------------------------------------------------
# Lua patch helpers
# ---------------------------------------------------------------------

def _format_like(value: float, template: str, decimals: int) -> str:
    # Preserve "integer-like" formatting where appropriate
    if abs(value - round(value)) < 1e-9 and decimals == 0:
        return str(int(round(value)))
    fmt = f"{{:.{decimals}f}}"
    return fmt.format(value)


def _find_section(lua: str, start_pat: str, end_pat: str, start_from: int = 0) -> Optional[tuple[int, int]]:
    s = lua.find(start_pat, start_from)
    if s == -1:
        return None
    e = lua.find(end_pat, s)
    if e == -1:
        return None
    return (s, e)


def _scale_first_kv(lua: str, key: str, scale: float, decimals: int = 2, *, count: int = 1) -> str:
    if scale == 1.0:
        return lua
    pat = re.compile(rf"(\b{re.escape(key)}\s*=\s*)({NUM_RE})")
    def repl(m: re.Match) -> str:
        prefix = m.group(1)
        val = float(m.group(2))
        new_val = val * scale
        return f"{prefix}{_format_like(new_val, m.group(2), decimals)}"
    return pat.sub(repl, lua, count=count)



def _scale_first_kv_kmh_div(src: str, key: str, scale: float) -> str:
    """
    Scale a key written in km/h-as-m/s style: `key = <kmh> / 3.6`.

    DCS aircraft lua files frequently store some speed limits in this form. Our
    normal `_scale_first_kv()` only matches numeric literals, so it will NOT
    touch expressions like `1115 / 3.6`.

    This helper scales only the numerator and preserves the `/ 3.6` structure.
    """
    if abs(scale - 1.0) < 1e-12:
        return src

    pat = re.compile(rf"(\b{re.escape(key)}\s*=\s*)([-+]?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)")

    def repl(m: re.Match[str]) -> str:
        prefix, num_s, den_s = m.group(1), m.group(2), m.group(3)
        old_num = float(num_s)
        new_num = old_num * float(scale)
        if re.fullmatch(r"[-+]?\d+", num_s):
            out_num = str(int(round(new_num)))
        else:
            # Preserve approximate formatting (e.g. '850.0')
            out_num = _format_like(num_s, new_num, decimals=0)
        return f"{prefix}{out_num} / {den_s}"

    return pat.sub(repl, src, count=1)
def _set_first_kv(lua: str, key: str, value: float, decimals: int = 2, *, count: int = 1) -> str:
    pat = re.compile(rf"(\b{re.escape(key)}\s*=\s*)({NUM_RE})")
    def repl(m: re.Match) -> str:
        prefix = m.group(1)
        return f"{prefix}{_format_like(float(value), m.group(2), decimals)}"
    return pat.sub(repl, lua, count=count)


def patch_identity_fields(lua_content: str, variant: Variant) -> str:
    """Patch Name, DisplayName, and shape_table_data.username to make DCS treat each variant as unique."""
    # Name = '...'
    name_pattern = re.compile(r"(Name\s*=\s*['\"])([^'\"]+)(['\"])")
    lua_content = name_pattern.sub(rf"\g<1>{variant.dcs_type_name}\g<3>", lua_content, count=1)

    # DisplayName = _('...')
    display_pattern = re.compile(r"(DisplayName\s*=\s*_\(['\"])(.+?)(['\"])\)")
    lua_content = display_pattern.sub(rf"\g<1>{variant.display_name}\g<3>)", lua_content, count=1)

    # shape_table_data username = '...'
    shape_start = lua_content.find("shape_table_data")
    if shape_start != -1:
        before = lua_content[:shape_start]
        after = lua_content[shape_start:]
        username_pattern = re.compile(r"(username\s*=\s*['\"])([^'\"]+)(['\"])")
        after = username_pattern.sub(rf"\g<1>{variant.shape_username}\g<3>", after, count=1)
        lua_content = before + after

    return lua_content


def patch_entry_lua(entry_content: str, variant: Variant) -> str:
    """Patch entry.lua with unique plugin identifiers so multiple variants can be installed simultaneously."""
    suffix = variant.dcs_type_name.split("_")[-1]

    entry_content = re.sub(
        r'(self_ID\s*=\s*["\'])([^"\']+)(["\'])',
        rf'\g<1>\g<2>_{suffix}\g<3>',
        entry_content,
        count=1,
    )
    entry_content = re.sub(
        r'(displayName\s*=\s*_\(["\'])([^"\']+)(["\'])',
        rf'\g<1>{variant.display_name}\g<3>',
        entry_content,
        count=1,
    )
    entry_content = re.sub(
        r'(fileMenuName\s*=\s*_\(["\'])([^"\']+)(["\'])',
        rf'\g<1>{variant.short_name} MiG-17F\g<3>',
        entry_content,
        count=1,
    )
    entry_content = re.sub(
        r'(update_id\s*=\s*["\'])([^"\']+)(["\'])',
        rf'\g<1>\g<2>_{suffix}\g<3>',
        entry_content,
        count=1,
    )
    entry_content = re.sub(
        r'(type\s*=\s*["\'])([^"\']+)(["\'])',
        rf'\g<1>\g<2>_{suffix}\g<3>',
        entry_content,
        count=1,
    )
    return entry_content


# ---------------------------------------------------------------------
# Aerodynamics patches
# ---------------------------------------------------------------------

def scale_aero_table_data(lua_content: str, scales: Scales) -> str:
    """
    table_data rows are:
      { M, Cx0, Cya, B2, B4, Omxmax, Aldop, Cymax }
    """
    # Find aerodynamics.table_data
    aer_start = lua_content.find("aerodynamics")
    if aer_start == -1:
        LOGGER.warning("Could not find aerodynamics section")
        return lua_content

    table_start = lua_content.find("table_data", aer_start)
    if table_start == -1:
        LOGGER.warning("Could not find aerodynamics.table_data")
        return lua_content

    eq = lua_content.find("=", table_start)
    if eq == -1:
        return lua_content

    end_marker = lua_content.find("}, -- end of table_data", eq)
    if end_marker == -1:
        end_marker = lua_content.find("end of table_data", eq)
        if end_marker == -1:
            LOGGER.warning("Could not find end of aerodynamics.table_data block; skipping")
            return lua_content

    section = lua_content[eq:end_marker]

    row_pat = re.compile(
        rf"(\{{\s*)({NUM_RE})(\s*,\s*)"      # 2 M
        rf"({NUM_RE})(\s*,\s*)"             # 4 Cx0
        rf"({NUM_RE})(\s*,\s*)"             # 6 Cya
        rf"({NUM_RE})(\s*,\s*)"             # 8 B2
        rf"({NUM_RE})(\s*,\s*)"             # 10 B4
        rf"({NUM_RE})(\s*,\s*)"             # 12 Omxmax
        rf"({NUM_RE})(\s*,\s*)"             # 14 Aldop
        rf"({NUM_RE})(\s*\}})"              # 16 Cymax
    )

    def repl(m: re.Match) -> str:
        mach = float(m.group(2))
        cx0 = float(m.group(4)) * scales.cx0
        cya = float(m.group(6)) * scales.cya
        b2 = float(m.group(8)) * scales.polar_b2
        b4 = float(m.group(10)) * scales.polar_b4
        omx = float(m.group(12)) * scales.omxmax
        ald = float(m.group(14)) * scales.aldop
        cym = float(m.group(16)) * scales.cymax

        # Windowed extras
        if HIGH_AOA_MACH_MIN <= mach <= HIGH_AOA_MACH_MAX:
            b4 *= scales.polar_high_aoa
        if mach >= TRANSONIC_MACH_MIN:
            b4 *= scales.polar_transonic
        if mach < CYMAX_LOW_MACH_THRESHOLD:
            cym *= scales.cymax_high_aoa

        return (
            f"{m.group(1)}{mach}{m.group(3)}"
            f"{cx0:.4f}{m.group(5)}"
            f"{cya:.4f}{m.group(7)}"
            f"{b2:.3f}{m.group(9)}"
            f"{b4:.3f}{m.group(11)}"
            f"{omx:.3f}{m.group(13)}"
            f"{ald:.2f}{m.group(15)}"
            f"{cym:.2f}{m.group(17)}"
        )

    new_section = row_pat.sub(repl, section)
    return lua_content[:eq] + new_section + lua_content[end_marker:]


# ---------------------------------------------------------------------
# Engine patches (SFM_Data.engine)
# ---------------------------------------------------------------------


def scale_aero_extra_scalars(src: str, scales: Scales) -> str:
    """
    Scale additional scalar knobs inside `SFM_Data.aerodynamics` (outside `table_data`).

    These are easy to miss, but they *do* exist in the baseline MiG-17F mod and can
    affect handling / stability in edge cases.
    """
    if (
        abs(scales.cy0_scale - 1.0) < 1e-12
        and abs(scales.mzalfa_scale - 1.0) < 1e-12
        and abs(scales.mzalfadt_scale - 1.0) < 1e-12
        and abs(scales.czbe_scale - 1.0) < 1e-12
        and abs(scales.kjx_scale - 1.0) < 1e-12
        and abs(scales.kjz_scale - 1.0) < 1e-12
        and abs(scales.cx_gear_scale - 1.0) < 1e-12
        and abs(scales.cx_flap_scale - 1.0) < 1e-12
        and abs(scales.cy_flap_scale - 1.0) < 1e-12
        and abs(scales.cx_brk_scale - 1.0) < 1e-12
    ):
        return src

    start, end, aero = _aero_block(src)
    patched = aero
    patched = _scale_first_kv(patched, "Cy0", scales.cy0_scale, decimals=4)
    patched = _scale_first_kv(patched, "Mzalfa", scales.mzalfa_scale, decimals=4)
    patched = _scale_first_kv(patched, "Mzalfadt", scales.mzalfadt_scale, decimals=4)
    patched = _scale_first_kv(patched, "Czbe", scales.czbe_scale, decimals=4)
    patched = _scale_first_kv(patched, "kjx", scales.kjx_scale, decimals=4)
    patched = _scale_first_kv(patched, "kjz", scales.kjz_scale, decimals=6)
    patched = _scale_first_kv(patched, "cx_gear", scales.cx_gear_scale, decimals=4)
    patched = _scale_first_kv(patched, "cx_flap", scales.cx_flap_scale, decimals=4)
    patched = _scale_first_kv(patched, "cy_flap", scales.cy_flap_scale, decimals=4)
    patched = _scale_first_kv(patched, "cx_brk", scales.cx_brk_scale, decimals=4)
    return src[:start] + patched + src[end:]
def _engine_block(lua_content: str) -> Optional[tuple[int, int, str]]:
    """
    Return (start_idx, end_idx, engine_text) for the SFM engine block.
    Relies on '-- end of engine' marker in your files.
    """
    sfm = lua_content.find("SFM_Data")
    if sfm == -1:
        return None
    m = re.search(r"engine\s*=\s*\{", lua_content[sfm:])
    if not m:
        return None
    start = sfm + m.start()
    end = lua_content.find("}, -- end of engine", start)
    if end == -1:
        end = lua_content.find("end of engine", start)
        if end == -1:
            return None
    return start, end, lua_content[start:end]



def _aero_block(lua_content: str) -> tuple[int, int, str]:
    """Return `(start, end, aero_block)` for the `aerodynamics` section inside `SFM_Data`."""
    # In our mig17f.lua, the opening brace is typically on the next line (often after an inline comment), e.g.:
    #   aerodynamics = -- Cx = ...
    #       {
    m = re.search(
        r"aerodynamics\s*=\s*(?:--[^\r\n]*\s*)?\{",
        lua_content,
        flags=re.MULTILINE,
    )
    if not m:
        raise ValueError("Could not find aerodynamics block (aerodynamics = {) in mig17f.lua")

    start = m.start()
    end = lua_content.find("}, -- end of aerodynamics", start)
    if end == -1:
        raise ValueError("Could not find end of aerodynamics marker in mig17f.lua")

    aero = lua_content[start:end]
    return start, end, aero

def scale_engine_scalars(lua_content: str, scales: Scales) -> str:
    blk = _engine_block(lua_content)
    if not blk:
        LOGGER.warning("Could not find SFM engine block")
        return lua_content
    start, end, eng = blk

    # dcx_eng / cemax / cefor
    eng2 = eng
    eng2 = _scale_first_kv(eng2, "dcx_eng", scales.engine_drag, decimals=4)
    eng2 = _scale_first_kv(eng2, "cemax", scales.cemax, decimals=2)
    eng2 = _scale_first_kv(eng2, "cefor", scales.cefor, decimals=2)
    eng2 = _scale_first_kv(eng2, "dpdh_m", scales.dpdh_m_scale, decimals=0)
    eng2 = _scale_first_kv(eng2, "dpdh_f", scales.dpdh_f_scale, decimals=0)

    return lua_content[:start] + eng2 + lua_content[end:]



def scale_engine_misc_scalars(lua_content: str, scales: Scales) -> str:
    """
    Scale *additional* scalar knobs inside `SFM_Data.engine` that were not covered
    by the original Stage9/Stage10 sweeps.

    Notes:
    - `hMaxEng` is a key suspect for the 'vertical UFO' behavior (engine still strong
      at very high altitude).
    - Startup/shutdown scalars are mostly irrelevant for airborne spawns, but included
      for completeness so the schema is exhaustive vs the lua file.
    """
    if (
        abs(scales.hmaxeng_scale - 1.0) < 1e-12
        and abs(scales.nominal_rpm_scale - 1.0) < 1e-12
        and abs(scales.nmg_scale - 1.0) < 1e-12
        and abs(scales.startup_prework_scale - 1.0) < 1e-12
        and abs(scales.startup_duration_scale - 1.0) < 1e-12
        and abs(scales.shutdown_duration_scale - 1.0) < 1e-12
        and abs(scales.minrud_scale - 1.0) < 1e-12
        and abs(scales.maxrud_scale - 1.0) < 1e-12
        and abs(scales.maksrud_scale - 1.0) < 1e-12
        and abs(scales.forsrud_scale - 1.0) < 1e-12
    ):
        return lua_content

    start, end, engine = _engine_block(lua_content)
    patched = engine
    patched = _scale_first_kv(patched, "hMaxEng", scales.hmaxeng_scale, decimals=3)
    patched = _scale_first_kv(patched, "Nominal_RPM", scales.nominal_rpm_scale, decimals=3)
    patched = _scale_first_kv(patched, "Nmg", scales.nmg_scale, decimals=3)
    patched = _scale_first_kv(patched, "Startup_Prework", scales.startup_prework_scale, decimals=3)
    patched = _scale_first_kv(patched, "Startup_Duration", scales.startup_duration_scale, decimals=3)
    patched = _scale_first_kv(patched, "Shutdown_Duration", scales.shutdown_duration_scale, decimals=3)
    patched = _scale_first_kv(patched, "MinRUD", scales.minrud_scale, decimals=3)
    patched = _scale_first_kv(patched, "MaxRUD", scales.maxrud_scale, decimals=3)
    patched = _scale_first_kv(patched, "MaksRUD", scales.maksrud_scale, decimals=3)
    patched = _scale_first_kv(patched, "ForsRUD", scales.forsrud_scale, decimals=3)
    return lua_content[:start] + patched + lua_content[end:]
def scale_engine_thrust_table(lua_content: str, scales: Scales) -> str:
    """
    Engine table_data rows:
      { M, Pmax, Pfor }
    """
    blk = _engine_block(lua_content)
    if not blk:
        return lua_content
    start, end, eng = blk

    t_start = eng.find("table_data")
    if t_start == -1:
        LOGGER.warning("Could not find engine.table_data")
        return lua_content

    eq = eng.find("=", t_start)
    if eq == -1:
        return lua_content

    t_end = eng.find("}, -- end of table_data", eq)
    if t_end == -1:
        t_end = eng.find("end of table_data", eq)
        if t_end == -1:
            LOGGER.warning("Could not find end of engine.table_data")
            return lua_content

    table = eng[eq:t_end]

    row_pat = re.compile(
        rf"(\{{\s*)({NUM_RE})(\s*,\s*)({NUM_RE})(\s*,\s*)({NUM_RE})(\s*\}})"
    )

    def repl(m: re.Match) -> str:
        mach = float(m.group(2))
        pmax = float(m.group(4)) * scales.pmax
        pfor = float(m.group(6)) * scales.pfor
        # Keep integers (these are N in your files)
        return f"{m.group(1)}{mach}{m.group(3)}{int(round(pmax))}{m.group(5)}{int(round(pfor))}{m.group(7)}"

    new_table = row_pat.sub(repl, table)
    eng2 = eng[:eq] + new_table + eng[t_end:]
    return lua_content[:start] + eng2 + lua_content[end:]


# ---------------------------------------------------------------------
# Top-level AI / mass knobs
# ---------------------------------------------------------------------

def apply_top_level_scalars(lua_content: str, scales: Scales) -> str:
    # Masses
    lua_content = _scale_first_kv(lua_content, "M_empty", scales.m_empty_scale, decimals=0)
    lua_content = _scale_first_kv(lua_content, "M_nominal", scales.m_nominal_scale, decimals=0)
    lua_content = _scale_first_kv(lua_content, "M_max", scales.m_max_scale, decimals=0)
    lua_content = _scale_first_kv(lua_content, "M_fuel_max", scales.m_fuel_max_scale, decimals=0)

    # AI/scheduling scalars
    lua_content = _scale_first_kv(lua_content, "Vy_max", scales.vy_max_scale, decimals=2)
    lua_content = _scale_first_kv(lua_content, "Mach_max", scales.mach_max_scale, decimals=2)

    # AI bookkeeping thrust sums (kgf in your file)
    lua_content = _scale_first_kv(lua_content, "thrust_sum_max", scales.thrust_sum_max_scale, decimals=0)
    lua_content = _scale_first_kv(lua_content, "thrust_sum_ab", scales.thrust_sum_ab_scale, decimals=0)

    # flaps_maneuver
    lua_content = _scale_first_kv(lua_content, "flaps_maneuver", scales.flaps_maneuver_scale, decimals=2)

    return lua_content



def apply_top_level_misc_scalars(lua_content: str, scales: Scales) -> str:
    """
    Apply additional top-level (aircraft table) scalar adjustments.

    These values influence AI scheduling / limits more than the pure SFM physics, but
    they *do* matter if you are trying to reproduce behavior consistently between
    AI-vs-AI and human-vs-AI tests.

    We keep them separate from `apply_top_level_scalars()` to avoid quietly changing
    legacy behavior for older JSON configs.
    """
    if (
        scales.ny_min_abs is None
        and abs(scales.aoa_take_off_scale - 1.0) < 1e-12
        and abs(scales.bank_angle_max_scale - 1.0) < 1e-12
        and abs(scales.cas_min_scale - 1.0) < 1e-12
        and abs(scales.v_opt_kmh_scale - 1.0) < 1e-12
        and abs(scales.vmax_sea_level_kmh_scale - 1.0) < 1e-12
        and abs(scales.vmax_h_kmh_scale - 1.0) < 1e-12
        and abs(scales.v_take_off_scale - 1.0) < 1e-12
        and abs(scales.v_land_scale - 1.0) < 1e-12
        and abs(scales.range_scale - 1.0) < 1e-12
        and abs(scales.avg_fuel_consumption_scale - 1.0) < 1e-12
        and abs(scales.wing_area_scale - 1.0) < 1e-12
        and abs(scales.wing_span_scale - 1.0) < 1e-12
        and scales.wing_type_abs is None
        and abs(scales.h_max_scale - 1.0) < 1e-12
    ):
        return lua_content

    out = lua_content
    if scales.ny_min_abs is not None:
        out = _set_first_kv(out, "Ny_min", float(scales.ny_min_abs), decimals=3)

    out = _scale_first_kv(out, "AOA_take_off", scales.aoa_take_off_scale, decimals=3)
    out = _scale_first_kv(out, "bank_angle_max", scales.bank_angle_max_scale, decimals=3)
    out = _scale_first_kv(out, "CAS_min", scales.cas_min_scale, decimals=3)

    out = _scale_first_kv_kmh_div(out, "V_opt", scales.v_opt_kmh_scale)
    out = _scale_first_kv_kmh_div(out, "V_max_sea_level", scales.vmax_sea_level_kmh_scale)
    out = _scale_first_kv_kmh_div(out, "V_max_h", scales.vmax_h_kmh_scale)

    out = _scale_first_kv(out, "V_take_off", scales.v_take_off_scale, decimals=3)
    out = _scale_first_kv(out, "V_land", scales.v_land_scale, decimals=3)
    out = _scale_first_kv(out, "range", scales.range_scale, decimals=3)
    out = _scale_first_kv(out, "average_fuel_consumption", scales.avg_fuel_consumption_scale, decimals=6)

    out = _scale_first_kv(out, "wing_area", scales.wing_area_scale, decimals=6)
    out = _scale_first_kv(out, "wing_span", scales.wing_span_scale, decimals=6)
    if scales.wing_type_abs is not None:
        out = _set_first_kv(out, "wing_type", float(scales.wing_type_abs), decimals=0)

    out = _scale_first_kv(out, "H_max", scales.h_max_scale, decimals=0)
    return out
def patch_ny_max(lua_content: str, ny: Optional[float]) -> str:
    if ny is None:
        return lua_content
    lua_content = _set_first_kv(lua_content, "Ny_max", float(ny), decimals=2)
    lua_content = _set_first_kv(lua_content, "Ny_max_e", float(ny), decimals=2)
    return lua_content


# ---------------------------------------------------------------------
# Variant application
# ---------------------------------------------------------------------

def apply_variant_modifications(lua_content: str, variant: Variant) -> str:
    lua_content = patch_identity_fields(lua_content, variant)

    # Aerodynamics
    lua_content = scale_aero_table_data(lua_content, variant.scales)
    lua_content = scale_aero_extra_scalars(lua_content, variant.scales)

    # Engine
    lua_content = scale_engine_scalars(lua_content, variant.scales)
    lua_content = scale_engine_misc_scalars(lua_content, variant.scales)
    lua_content = scale_engine_thrust_table(lua_content, variant.scales)

    # Top-level / AI scheduling knobs
    lua_content = apply_top_level_scalars(lua_content, variant.scales)
    lua_content = apply_top_level_misc_scalars(lua_content, variant.scales)
    lua_content = patch_ny_max(lua_content, variant.scales.ny_max_abs)

    return lua_content


# ---------------------------------------------------------------------
# Build / install
# ---------------------------------------------------------------------

def build_variant(base_mod_path: Path, variant: Variant, variants_root: Path, *, flight_model_lua: str, entry_lua: str) -> Path:
    variant_path = variants_root / variant.mod_dir_name
    if variant_path.exists():
        LOGGER.info("Removing existing variant folder: %s", variant_path)
        shutil.rmtree(variant_path)

    LOGGER.info("Copying base mod to: %s", variant_path)
    shutil.copytree(base_mod_path, variant_path)

    lua_path = variant_path / flight_model_lua
    if not lua_path.exists():
        raise FileNotFoundError(f"Flight model lua not found: {lua_path}")

    lua_content = lua_path.read_text(encoding="utf-8", errors="replace")
    lua_path.write_text(apply_variant_modifications(lua_content, variant), encoding="utf-8")

    entry_path = variant_path / entry_lua
    if entry_path.exists():
        entry_content = entry_path.read_text(encoding="utf-8", errors="replace")
        entry_path.write_text(patch_entry_lua(entry_content, variant), encoding="utf-8")
    else:
        LOGGER.warning("entry.lua not found at %s", entry_path)

    return variant_path


def install_to_saved_games(variant_path: Path, dcs_saved_games: Path) -> None:
    mods_path = dcs_saved_games / "Mods" / "aircraft" / variant_path.name
    if mods_path.exists():
        shutil.rmtree(mods_path)
    shutil.copytree(variant_path, mods_path)


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build MiG-17F SFM variants from a JSON file (v2).")
    p.add_argument("--base-mod-root", type=Path, help="Path to base mod folder (overrides JSON base_mod_dir).")
    p.add_argument("--variants-root", type=Path, default=Path("./fm_variants/mods"), help="Output directory for variants.")
    p.add_argument("--dcs-saved-games", type=Path, help="Optional Saved Games/DCS path to install variants.")
    p.add_argument("--json-file", type=Path, default=Path("./fm_variants/flight_models.json"), help="Path to flight models JSON.")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    json_path = args.json_file.resolve()
    if not json_path.exists():
        LOGGER.error("JSON not found: %s", json_path)
        return 1

    cfg = load_variant_config(json_path)
    LOGGER.info("Loaded JSON v%s (schema_version %s): %s", cfg.version, cfg.schema_version, cfg.description)
    LOGGER.info("Variants: %d", len(cfg.variants))

    variants_root = args.variants_root.resolve()
    variants_root.mkdir(parents=True, exist_ok=True)

    if args.base_mod_root:
        base_mod_path = args.base_mod_root.resolve()
    else:
        # repo root heuristic: json is usually ./fm_variants/*.json
        repo_root = json_path.parent.parent
        base_mod_path = (repo_root / cfg.base_mod_dir).resolve()

    if not base_mod_path.exists():
        LOGGER.error("Base mod not found: %s", base_mod_path)
        return 1

    built = []
    for v in cfg.variants:
        LOGGER.info("Building %s (%s)", v.short_name, v.variant_id)
        vp = build_variant(base_mod_path, v, variants_root, flight_model_lua=cfg.flight_model_lua, entry_lua=cfg.entry_lua)
        built.append(vp)

    if args.dcs_saved_games:
        sg = args.dcs_saved_games.resolve()
        if not sg.exists():
            LOGGER.warning("Saved Games path does not exist: %s", sg)
        else:
            for vp in built:
                install_to_saved_games(vp, sg)
            LOGGER.info("Installed %d variants to %s", len(built), sg)

    LOGGER.info("Done. Built variants:")
    for vp in built:
        LOGGER.info("  - %s", vp)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())