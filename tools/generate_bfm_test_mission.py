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

from dcs import countries, mapping, mission, planes, task, unit
from dcs import triggers, action, weather
from dcs.task import SetImmortalCommand, SetUnlimitedFuelCommand, Targets
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
    instances: int = 1  # Number of copies of this scenario to create per variant


@dataclass
class PlacementZone:
    """A polygon defining an eligible flight placement area over water.

    Uses DCS Caucasus coordinates (meters):
    - X axis = North-South (positive = North)
    - Y axis = East-West (positive = East)

    Vertices define a closed polygon (first and last are connected).
    """

    name: str
    vertices: list[tuple[float, float]]  # List of (x, y) points

    def contains(self, x: float, y: float) -> bool:
        """Check if point is inside polygon using ray casting algorithm."""
        n = len(self.vertices)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = self.vertices[i]
            xj, yj = self.vertices[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    def bounding_box(self) -> tuple[float, float, float, float]:
        """Return (min_x, max_x, min_y, max_y) bounding box."""
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        return (min(xs), max(xs), min(ys), max(ys))


@dataclass
class ReferenceAirfield:
    """An airfield used for distance-based placement priority."""

    name: str
    x: float
    y: float

    def distance_to(self, x: float, y: float) -> float:
        """Calculate distance in meters to a point."""
        return math.sqrt((self.x - x) ** 2 + (self.y - y) ** 2)


@dataclass
class ValidPosition:
    """A pre-validated position for flight placement."""

    x: float
    y: float
    nearest_airfield: str
    distance_nm: float  # Distance to nearest airfield in nm


@dataclass
class PlacementConfig:
    """Configuration for flight placement over water.

    Manages multiple polygon zones and computes optimal placement positions
    sorted by proximity to reference airfields.
    """

    zones: list[PlacementZone]
    airfields: list[ReferenceAirfield]
    spacing_nm: float
    margin_nm: float  # Safety margin for engagement geometry

    def compute_valid_positions(self) -> list[ValidPosition]:
        """Compute all valid positions at the configured spacing.

        Returns positions sorted by distance to nearest airfield (closest first).
        """
        spacing_m = self.spacing_nm * NM_TO_METERS
        margin_m = self.margin_nm * NM_TO_METERS
        positions: list[ValidPosition] = []

        for zone in self.zones:
            min_x, max_x, min_y, max_y = zone.bounding_box()
            # Shrink by margin to account for engagement geometry
            min_x += margin_m
            max_x -= margin_m
            min_y += margin_m
            max_y -= margin_m

            # Generate grid of candidate positions
            x = min_x
            while x <= max_x:
                y = min_y
                while y <= max_y:
                    if zone.contains(x, y):
                        # Find nearest airfield
                        nearest = min(
                            self.airfields,
                            key=lambda a: a.distance_to(x, y)
                        )
                        dist_nm = nearest.distance_to(x, y) / NM_TO_METERS
                        positions.append(ValidPosition(
                            x=x, y=y,
                            nearest_airfield=nearest.name,
                            distance_nm=dist_nm
                        ))
                    y += spacing_m
                x += spacing_m

        # Sort by distance to airfield (closest first)
        positions.sort(key=lambda p: p.distance_nm)
        return positions

    def max_flights(self) -> int:
        """Return maximum number of flights that can be placed."""
        return len(self.compute_valid_positions())


@dataclass
class BFMConfig:
    """Complete BFM test configuration loaded from JSON."""

    duration_seconds: int
    test_group_spacing_nm: float
    placement: PlacementConfig
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
                instances=scen.get("instances", 1),
            )
        )

    settings = data["mission_settings"]

    # Parse placement configuration
    placement_data = settings.get("placement", {})

    # Parse placement zones (polygons over water)
    zones: list[PlacementZone] = []
    zones_data = placement_data.get("zones", [])
    if zones_data:
        for z in zones_data:
            vertices = [(v["x"], v["y"]) for v in z["vertices"]]
            zones.append(PlacementZone(name=z["name"], vertices=vertices))
    else:
        # Default: Black Sea zones west of Georgian/Russian coast
        # Coastline reference points (from airfields):
        #   Batumi:   x=-355811, y=617386 (south)
        #   Sukhumi:  x=-220592, y=564392
        #   Gudauta:  x=-196605, y=516568
        #   Sochi:    x=-164496, y=462219 (north)
        # Keep ~50nm (93km) buffer west of coast for safety
        #
        # Zone 1: Main southern/central Black Sea (expanded west)
        zones.append(PlacementZone(
            name="black_sea_main",
            vertices=[
                (-500000, -200000),  # SW corner (far west, open sea)
                (-500000, 480000),   # SE corner (50nm west of Batumi coast)
                (-350000, 520000),   # East (following coast curve, 50nm offshore)
                (-250000, 450000),   # East (Sukhumi area, 50nm offshore)
                (-180000, 380000),   # NE (Sochi area, 50nm offshore)
                (-180000, -200000),  # NW corner (far west)
            ]
        ))
        # Zone 2: Northern Black Sea (north of Sochi)
        # Coast curves west here - Novorossiysk is at ~(x=-42000, y=285000)
        zones.append(PlacementZone(
            name="black_sea_north",
            vertices=[
                (-180000, -200000),  # SW corner
                (-180000, 350000),   # SE corner (west of Sochi)
                (50000, 200000),     # NE corner (50nm offshore Russian coast)
                (50000, -200000),    # NW corner
            ]
        ))

    # Parse reference airfields
    airfields: list[ReferenceAirfield] = []
    airfields_data = placement_data.get("reference_airfields", [])
    if airfields_data:
        for a in airfields_data:
            airfields.append(ReferenceAirfield(name=a["name"], x=a["x"], y=a["y"]))
    else:
        # Default: Key Caucasus coastal airfields
        airfields = [
            ReferenceAirfield(name="Sochi-Adler", x=-164496, y=462219),
            ReferenceAirfield(name="Sukhumi-Babushara", x=-220592, y=564392),
            ReferenceAirfield(name="Batumi", x=-355811, y=617386),
            ReferenceAirfield(name="Gudauta", x=-196605, y=516568),
        ]

    # Calculate margin from engagement geometries (half the max initial range + waypoint offset)
    max_range_nm = max(
        (geometries[s.geometry].initial_range_nm
         for s in scenarios if s.geometry in geometries),
        default=6.0
    )
    margin_nm = (max_range_nm / 2) + (10000 / NM_TO_METERS)  # Half range + 10km waypoint

    placement = PlacementConfig(
        zones=zones,
        airfields=airfields,
        spacing_nm=settings["test_group_spacing_nm"],
        margin_nm=margin_nm,
    )

    return BFMConfig(
        duration_seconds=settings["duration_seconds"],
        test_group_spacing_nm=settings["test_group_spacing_nm"],
        placement=placement,
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

    # Filter scenarios by priority
    active_scenarios = [s for s in bfm_config.scenarios if s.priority <= max_priority]

    # Determine MiG-17 types to use
    if variants:
        mig17_types = [(v["short_name"], v["dcs_type_name"]) for v in variants]
    else:
        mig17_types = [("", mig17_type_name)]

    # Calculate total groups needed
    num_variants = len(mig17_types)
    total_scenario_instances = sum(s.instances for s in active_scenarios)
    total_groups = num_variants * total_scenario_instances

    # Compute valid positions (sorted by proximity to airfields)
    valid_positions = bfm_config.placement.compute_valid_positions()
    max_flights = len(valid_positions)

    LOGGER.info(
        "Placement zones: %d, Reference airfields: %d",
        len(bfm_config.placement.zones),
        len(bfm_config.placement.airfields)
    )
    LOGGER.info(
        "Valid positions at %.0fnm spacing: %d (margin: %.1fnm)",
        bfm_config.placement.spacing_nm,
        max_flights,
        bfm_config.placement.margin_nm
    )

    # Check if we have enough positions
    if total_groups > max_flights:
        raise ValueError(
            f"Requested {total_groups} flight groups but only {max_flights} "
            f"valid positions available at {bfm_config.placement.spacing_nm}nm spacing. "
            f"Reduce instances or variants, or expand placement zones."
        )

    LOGGER.info(
        "Placing %d groups (closest to airfields first), max capacity: %d",
        total_groups, max_flights
    )

    # Show first few positions for debugging
    if valid_positions:
        for i, pos in enumerate(valid_positions[:3]):
            LOGGER.info(
                "  Position %d: (%.0f, %.0f) - %.1fnm from %s",
                i, pos.x, pos.y, pos.distance_nm, pos.nearest_airfield
            )
        if len(valid_positions) > 3:
            LOGGER.info("  ... and %d more positions", len(valid_positions) - 3)

    group_index = 0
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

            # Create multiple instances of this scenario if requested
            for instance_idx in range(scen.instances):
                # Get next valid position (sorted by airfield proximity)
                pos = valid_positions[group_index]
                center_x = pos.x
                center_y = pos.y
                group_index += 1

                # Calculate initial positions
                mig17_pos, opp_pos = calculate_engagement_positions(
                    geometry, altitude.altitude_ft, center_x, center_y
                )

                # Create group names (include instance number if multiple instances)
                instance_suffix = f"_{instance_idx + 1}" if scen.instances > 1 else ""
                if variant_prefix:
                    mig17_group_name = f"{variant_prefix}_{scen.id}{instance_suffix}"
                else:
                    mig17_group_name = f"{scen.id}{instance_suffix}"
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
                mig17_unit.skill = unit.Skill.Excellent

                # Set initial waypoint speed
                mig_start = mig17_grp.points[0]
                mig_start.speed = speed.speed_kt * KTS_TO_MPS

                # Make aircraft invulnerable with unlimited fuel for flight model testing
                mig_start.tasks.append(SetImmortalCommand(value=True))
                mig_start.tasks.append(SetUnlimitedFuelCommand(value=True))

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
                opp_unit.skill = unit.Skill.Excellent
                opp_unit.fuel = int(opp_plane.fuel_max * MIG17_FUEL_FRACTION_BFM)

                opp_start = opp_grp.points[0]
                opp_start.speed = opp_speed.speed_kt * KTS_TO_MPS

                # Make aircraft invulnerable with unlimited fuel for flight model testing
                opp_start.tasks.append(SetImmortalCommand(value=True))
                opp_start.tasks.append(SetUnlimitedFuelCommand(value=True))

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
