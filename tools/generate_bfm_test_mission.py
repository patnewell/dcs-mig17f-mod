"""Generate BFM (Basic Fighter Maneuvering) test missions for MiG-17F.

This script creates DCS missions with various BFM engagement scenarios
to test the MiG-17F flight model at the edge of its performance envelope.
It reads scenario configurations from a JSON file (e.g. flight_profiles.json).

The mission uses TacView for telemetry capture - no embedded Lua logging
since ACMI provides comprehensive flight data.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dcs import countries, mapping, mission, planes, task
from dcs import triggers, action, weather
from dcs.task import Targets
from dcs.terrain import caucasus

LOGGER = logging.getLogger(__name__)

# Conversion constants
FT_TO_METERS = 0.3048
KTS_TO_MPS = 0.514444
NM_TO_METERS = 1852.0
DEG_TO_RAD = math.pi / 180.0

# MiG-17F specifications (used as defaults for custom plane types)
MIG17_FUEL_MAX_KG = 1140
MIG17_FUEL_FRACTION_BFM = 0.50  # 50% fuel for BFM tests


@dataclass
class OpponentAircraft:
    """Configuration for an opponent aircraft type."""

    id: str
    dcs_type_name: str
    display_name: str
    group_prefix: str


@dataclass
class EngagementGeometry:
    """Configuration for an engagement starting geometry.

    Semantics:

    - initial_range_nm: distance between MiG and opponent.
    - opponent_heading_deg: opponent's initial heading (0° = east, 90° = north).
    - mig17_offset_deg: MiG's position around the opponent, relative to the
      opponent's nose:
        * 0   = in front of opponent (along its heading vector)
        * 180 = behind opponent
        * 90  = left beam
        * 270 = right beam
    - mig17_heading_deg: MiG's own heading at start (may differ from opponent).
    """

    id: str
    name: str
    description: str
    mig17_heading_deg: float
    opponent_heading_deg: float
    initial_range_nm: float
    mig17_offset_deg: float
    mig17_altitude_offset_ft: float = 0.0


@dataclass
class AltitudeBand:
    """Configuration for an altitude band."""

    id: str
    name: str
    altitude_ft: float


@dataclass
class InitialSpeed:
    """Configuration for initial engagement speed."""

    id: str
    name: str
    speed_kt: float


@dataclass
class BFMScenario:
    """Complete BFM test scenario configuration."""

    id: str
    opponent: str
    geometry: str
    altitude: str
    speed: str
    priority: int
    opponent_speed: Optional[str] = None  # Override opponent speed (uses 'speed' if None)


@dataclass
class BFMConfig:
    """Complete BFM test configuration loaded from JSON."""

    duration_seconds: int
    test_group_spacing_nm: float
    origin_x: float
    origin_y: float
    opponents: dict[str, OpponentAircraft]
    geometries: dict[str, EngagementGeometry]
    altitudes: dict[str, AltitudeBand]
    speeds: dict[str, InitialSpeed]
    scenarios: list[BFMScenario]
    envelope_targets: dict


def load_bfm_config(json_path: Path) -> BFMConfig:
    """Load BFM test configuration from JSON file."""
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Parse opponent aircraft
    opponents: dict[str, OpponentAircraft] = {}
    for opp in data["opponent_aircraft"]:
        opponents[opp["id"]] = OpponentAircraft(
            id=opp["id"],
            dcs_type_name=opp["dcs_type_name"],
            display_name=opp["display_name"],
            group_prefix=opp["group_prefix"],
        )

    # Parse engagement geometries
    geometries: dict[str, EngagementGeometry] = {}
    for geom in data["engagement_geometries"]:
        geometries[geom["id"]] = EngagementGeometry(
            id=geom["id"],
            name=geom["name"],
            description=geom["description"],
            mig17_heading_deg=geom["mig17_heading_deg"],
            opponent_heading_deg=geom["opponent_heading_deg"],
            initial_range_nm=geom["initial_range_nm"],
            mig17_offset_deg=geom["mig17_offset_deg"],
            mig17_altitude_offset_ft=geom.get("mig17_altitude_offset_ft", 0.0),
        )

    # Parse altitude bands
    altitudes: dict[str, AltitudeBand] = {}
    for alt in data["altitude_bands"]:
        altitudes[alt["id"]] = AltitudeBand(
            id=alt["id"],
            name=alt["name"],
            altitude_ft=alt["altitude_ft"],
        )

    # Parse initial speeds
    speeds: dict[str, InitialSpeed] = {}
    for spd in data["initial_speeds"]:
        speeds[spd["id"]] = InitialSpeed(
            id=spd["id"],
            name=spd["name"],
            speed_kt=spd["speed_kt"],
        )

    # Parse scenarios
    scenarios: list[BFMScenario] = []
    for scen in data["test_scenarios"]:
        scenarios.append(
            BFMScenario(
                id=scen["id"],
                opponent=scen["opponent"],
                geometry=scen["geometry"],
                altitude=scen["altitude"],
                speed=scen["speed"],
                priority=scen["priority"],
                opponent_speed=scen.get("opponent_speed"),
            )
        )

    settings = data["mission_settings"]
    return BFMConfig(
        duration_seconds=settings["duration_seconds"],
        test_group_spacing_nm=settings["test_group_spacing_nm"],
        origin_x=settings["origin"]["x"],
        origin_y=settings["origin"]["y"],
        opponents=opponents,
        geometries=geometries,
        altitudes=altitudes,
        speeds=speeds,
        scenarios=scenarios,
        envelope_targets=data.get("flight_envelope_targets", {}),
    )


def get_or_create_plane_type(type_name: str) -> planes.PlaneType:
    """Register or retrieve a custom plane type for DCS."""
    existing = planes.plane_map.get(type_name)
    if existing:
        return existing

    class CustomPlaneType(planes.PlaneType):
        id = type_name
        name = type_name
        display_name = type_name
        task_default = task.CAP
        fuel_max = MIG17_FUEL_MAX_KG

    planes.plane_map[type_name] = CustomPlaneType
    return CustomPlaneType


def calculate_engagement_positions(
    geometry: EngagementGeometry,
    base_altitude_ft: float,
    center_x: float,
    center_y: float,
) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    """Calculate starting positions for MiG-17 and opponent.

    We treat (center_x, center_y) as the **midpoint** of the initial
    separation. The vector from opponent to MiG is defined by:

        theta = opponent_heading_deg + mig17_offset_deg

    where mig17_offset_deg is measured from the opponent's nose
    (see EngagementGeometry docstring).

    Positions:

        opp = center - 0.5 * R
        mig = center + 0.5 * R

    where |R| = initial_range_nm.
    """
    range_m = geometry.initial_range_nm * NM_TO_METERS

    # Direction from opponent to MiG, in math-style heading (0° = +X/east)
    theta_rad = (geometry.opponent_heading_deg + geometry.mig17_offset_deg) * DEG_TO_RAD
    dx = range_m * math.cos(theta_rad)
    dy = range_m * math.sin(theta_rad)

    # Opponent and MiG positions are symmetric about the center
    opp_x = center_x - dx / 2.0
    opp_y = center_y - dy / 2.0
    mig_x = center_x + dx / 2.0
    mig_y = center_y + dy / 2.0

    opp_alt_m = base_altitude_ft * FT_TO_METERS
    mig_alt_m = (base_altitude_ft + geometry.mig17_altitude_offset_ft) * FT_TO_METERS

    mig_hdg = geometry.mig17_heading_deg
    opp_hdg = geometry.opponent_heading_deg

    return (
        (mig_x, mig_y, mig_alt_m, mig_hdg),
        (opp_x, opp_y, opp_alt_m, opp_hdg),
    )


def load_variant_descriptors(json_path: Path) -> list[dict]:
    """Load FM variant descriptors for multi-FM mode."""
    if not json_path.exists():
        return []

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return [
        {
            "short_name": v["short_name"],
            "dcs_type_name": v["dcs_type_name"],
        }
        for v in data["variants"]
    ]


def build_bfm_mission(
    bfm_config: BFMConfig,
    mig17_type_name: str,
    variants: Optional[list[dict]] = None,
    run_id: Optional[str] = None,
    max_priority: int = 3,
) -> tuple[mission.Mission, list[str], str]:
    """Build the BFM test mission."""
    if run_id is None:
        run_id = uuid.uuid4().hex[:12]

    miz = mission.Mission()
    miz.terrain = caucasus.Caucasus()
    miz.start_time = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)

    # Configure weather - clear conditions for consistent testing
    weather_settings = weather.Weather(miz.terrain)
    weather_settings.wind_at_ground = weather.Wind(0, 0)
    weather_settings.wind_at_2000 = weather.Wind(0, 0)
    weather_settings.wind_at_8000 = weather.Wind(0, 0)
    weather_settings.turbulence_at_ground = 0
    weather_settings.season_temperature = 15
    weather_settings.qnh = 759.0
    weather_settings.clouds_density = 0
    weather_settings.clouds_thickness = 0
    weather_settings.clouds_base = 0
    weather_settings.clouds_iprecptns = weather.Weather.Preceptions.None_
    miz.weather = weather_settings

    # Set up coalitions
    red = miz.coalition["red"]
    blue = miz.coalition["blue"]
    russia = red.add_country(countries.Russia())
    usa = blue.add_country(countries.USA())

    groups: list[str] = []
    spacing_m = bfm_config.test_group_spacing_nm * NM_TO_METERS

    # Filter scenarios by priority
    active_scenarios = [s for s in bfm_config.scenarios if s.priority <= max_priority]

    # Determine MiG-17 types to use
    if variants:
        mig17_types = [(v["short_name"], v["dcs_type_name"]) for v in variants]
    else:
        mig17_types = [("", mig17_type_name)]

    for variant_idx, (variant_prefix, mig17_dcs_type) in enumerate(mig17_types):
        mig17_plane = get_or_create_plane_type(mig17_dcs_type)

        for scen_idx, scen in enumerate(active_scenarios):
            opponent = bfm_config.opponents.get(scen.opponent)
            geometry = bfm_config.geometries.get(scen.geometry)
            altitude = bfm_config.altitudes.get(scen.altitude)
            speed = bfm_config.speeds.get(scen.speed)

            # Get opponent speed (defaults to same as MiG-17 if not specified)
            opp_speed = speed
            if scen.opponent_speed:
                opp_speed = bfm_config.speeds.get(scen.opponent_speed)
                if not opp_speed:
                    LOGGER.warning(
                        "Unknown opponent_speed '%s' in %s, using default",
                        scen.opponent_speed, scen.id
                    )
                    opp_speed = speed

            if not all([opponent, geometry, altitude, speed]):
                LOGGER.warning("Incomplete scenario config for %s, skipping", scen.id)
                continue

            # Grid layout: variants along rows (Y/N-S), scenarios along columns (X/E-W)
            row = variant_idx
            col = scen_idx
            center_x = bfm_config.origin_x + col * spacing_m
            center_y = bfm_config.origin_y + row * spacing_m

            # Calculate initial positions
            mig17_pos, opp_pos = calculate_engagement_positions(
                geometry, altitude.altitude_ft, center_x, center_y
            )

            # Create group names
            if variant_prefix:
                mig17_group_name = f"{variant_prefix}_{scen.id}"
            else:
                mig17_group_name = scen.id
            opp_group_name = f"{mig17_group_name}_OPP"

            # === MiG-17 group ===
            mig17_alt_m = mig17_pos[2]
            mig17_grp = miz.flight_group_inflight(
                country=russia,
                name=mig17_group_name,
                aircraft_type=mig17_plane,
                position=mapping.Point(mig17_pos[0], mig17_pos[1], mig17_alt_m),
                altitude=mig17_alt_m,
                speed=speed.speed_kt * 1.852,  # kph
                maintask=task.CAP,
                group_size=1,
            )
            if mig17_grp not in russia.plane_group:
                russia.add_aircraft_group(mig17_grp)

            mig17_unit = mig17_grp.units[0]
            mig17_unit.heading = math.radians(mig17_pos[3])
            mig17_unit.fuel = int(MIG17_FUEL_MAX_KG * MIG17_FUEL_FRACTION_BFM)

            # Set initial waypoint speed
            mig_start = mig17_grp.points[0]
            mig_start.speed = speed.speed_kt * KTS_TO_MPS

            # Aggressive engage task – 20 km range, still < 30 nm grid spacing
            mig_start.tasks.append(
                task.EngageTargets(
                    max_distance=20000,  # 20 km
                    targets=[Targets.All.Air.Planes],
                )
            )

            # Waypoint: fly forward along current heading (preserve geometry)
            mig_hdg_rad = math.radians(mig17_pos[3])
            mig_wp_x = mig17_pos[0] + 10000 * math.cos(mig_hdg_rad)
            mig_wp_y = mig17_pos[1] + 10000 * math.sin(mig_hdg_rad)
            mig17_grp.add_waypoint(
                pos=mapping.Point(mig_wp_x, mig_wp_y, mig17_alt_m),
                altitude=mig17_alt_m,
                speed=speed.speed_kt * 1.852,
            )

            # === Opponent group ===
            opp_plane = get_or_create_plane_type(opponent.dcs_type_name)
            opp_alt_m = opp_pos[2]
            opp_grp = miz.flight_group_inflight(
                country=usa,
                name=opp_group_name,
                aircraft_type=opp_plane,
                position=mapping.Point(opp_pos[0], opp_pos[1], opp_alt_m),
                altitude=opp_alt_m,
                speed=opp_speed.speed_kt * 1.852,
                maintask=task.CAP,
                group_size=1,
            )
            if opp_grp not in usa.plane_group:
                usa.add_aircraft_group(opp_grp)

            opp_unit = opp_grp.units[0]
            opp_unit.heading = math.radians(opp_pos[3])

            opp_start = opp_grp.points[0]
            opp_start.speed = opp_speed.speed_kt * KTS_TO_MPS
            opp_start.tasks.append(
                task.EngageTargets(
                    max_distance=20000,
                    targets=[Targets.All.Air.Planes],
                )
            )

            opp_hdg_rad = math.radians(opp_pos[3])
            opp_wp_x = opp_pos[0] + 10000 * math.cos(opp_hdg_rad)
            opp_wp_y = opp_pos[1] + 10000 * math.sin(opp_hdg_rad)
            opp_grp.add_waypoint(
                pos=mapping.Point(opp_wp_x, opp_wp_y, opp_alt_m),
                altitude=opp_alt_m,
                speed=opp_speed.speed_kt * 1.852,
            )

            groups.append(mig17_group_name)
            groups.append(opp_group_name)

    # Add mission start trigger with run ID marker
    marker_lua = f'''
do
    env.info("[BFM_TEST] RUN_START,{run_id}")
    env.info("[BFM_TEST] BFM test mission initialized")
    env.info("[BFM_TEST] Groups: {len(groups)}")
    timer.scheduleFunction(function()
        env.info("[BFM_TEST] RUN_END,{run_id}")
    end, nil, timer.getTime() + {bfm_config.duration_seconds})
end
'''
    trig = triggers.TriggerStart(comment="BFM Test Marker")
    trig.add_action(action.DoScript(action.String(marker_lua)))
    miz.triggerrules.triggers.append(trig)

    return miz, groups, run_id


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate BFM test mission for MiG-17F"
    )
    parser.add_argument(
        "--outfile",
        default=Path.home()
        / "Saved Games"
        / "DCS"
        / "Missions"
        / "MiG17F_BFM_Test.miz",
        type=Path,
        help="Path to output .miz file",
    )
    parser.add_argument(
        "--bfm-config",
        dest="bfm_config",
        default=Path.cwd() / "bfm_mission_tests.json",
        type=Path,
        help="Path to BFM test configuration JSON (e.g. flight_profiles.json)",
    )
    parser.add_argument(
        "--variant-json",
        dest="variant_json",
        default=Path.cwd() / "fm_variants" / "mig17f_fm_variants.json",
        type=Path,
        help="Path to FM variants JSON (enables multi-FM mode)",
    )
    parser.add_argument(
        "--type-name",
        dest="type_name",
        default="vwv_mig17f",
        help="MiG-17 DCS type name for single-FM mode",
    )
    parser.add_argument(
        "--max-priority",
        dest="max_priority",
        type=int,
        default=2,
        choices=[1, 2, 3],
        help="Maximum scenario priority to include (1=core, 2=standard, 3=all)",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    args = parse_args()

    # Load BFM configuration
    if not args.bfm_config.exists():
        LOGGER.error("BFM config not found: %s", args.bfm_config)
        return 1

    LOGGER.info("Loading BFM configuration from: %s", args.bfm_config)
    bfm_config = load_bfm_config(args.bfm_config)
    LOGGER.info("Loaded %d scenarios", len(bfm_config.scenarios))

    # Check for multi-FM mode
    variants = None
    if args.variant_json.exists():
        LOGGER.info("Found variant JSON: %s", args.variant_json)
        variants = load_variant_descriptors(args.variant_json)
        LOGGER.info("Multi-FM mode: %d variants", len(variants))
        mig17_type = "multi_fm_mode"
    else:
        LOGGER.info("Single-FM mode: %s", args.type_name)
        mig17_type = args.type_name

    # Build mission
    try:
        miz, groups, run_id = build_bfm_mission(
            bfm_config,
            mig17_type,
            variants,
            max_priority=args.max_priority,
        )
    except Exception as exc:
        LOGGER.exception("Failed to build mission: %s", exc)
        return 2

    # Ensure output directory exists
    args.outfile.parent.mkdir(parents=True, exist_ok=True)

    # Save mission
    try:
        miz.save(args.outfile)
    except Exception as exc:
        LOGGER.exception("Failed to save mission: %s", exc)
        return 3

    LOGGER.info("BFM test mission generated successfully")
    LOGGER.info("Output : %s", args.outfile)
    LOGGER.info("Run ID : %s", run_id)
    LOGGER.info("Groups : %d", len(groups))

    for name in groups[:10]:
        LOGGER.info("  - %s", name)
    if len(groups) > 10:
        LOGGER.info("  ... and %d more", len(groups) - 10)

    print(f"RUN_ID={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
