"""Generate a MiG-17 flight-model test mission using pydcs.

This script builds a mission with acceleration, climb, turn, and deceleration
profiles for the VWV MiG-17F mod. It requires Python 3 and the ``dcs`` library
(pydcs). Install dependencies with ``pip install dcs``.
"""
from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from dcs import countries, mapping, mission, planes, task
from dcs import triggers, action, weather
from dcs.terrain import caucasus


# Lua script for comprehensive flight model testing
# Uses structured logging format for automated parsing
#
# Output format in dcs.log:
#   [MIG17_FM_TEST] DATA,<group>,<elapsed_s>,<alt_ft>,<spd_kt>,<vspd_fpm>,<mach>
#   [MIG17_FM_TEST] SPEED_GATE,<group>,<gate_kt>,<elapsed_s>,<alt_ft>
#   [MIG17_FM_TEST] ALT_GATE,<group>,<gate_ft>,<elapsed_s>,<climb_rate_fpm>
#   [MIG17_FM_TEST] VMAX,<group>,<speed_kt>,<alt_ft>,<mach>
#   [MIG17_FM_TEST] SUMMARY,<group>,<max_spd_kt>,<max_alt_ft>,<max_vspd_fpm>
LOGGER_LUA = r'''
do
  local MIG17_TEST = {}

  MIG17_TEST.GROUPS = {
    "ACCEL_SL", "ACCEL_10K", "ACCEL_20K",
    "CLIMB_SL", "CLIMB_10K",
    "TURN_10K_300", "TURN_10K_350", "TURN_10K_400",
    "VMAX_SL", "VMAX_10K",
    "DECEL_10K",
  }

  MIG17_TEST.samplePeriod = 0.5
  MIG17_TEST.state = {}

  -- Speed gates matching historical MiG-17F targets (knots)
  -- 593 kt = Vmax at SL, 618 kt = Vmax at 10K with afterburner
  MIG17_TEST.SPEED_GATES_KT = { 350, 400, 450, 500, 550, 593, 618 }

  -- Altitude gates for climb tests (feet)
  MIG17_TEST.ALT_GATES_FT = { 5000, 10000, 15000, 20000, 25000, 30000, 35000, 40000 }

  -- Historical targets for verification
  MIG17_TEST.TARGETS = {
    vmax_sl_kt = 593,       -- 1100 km/h at sea level
    vmax_10k_kt = 618,      -- 1145 km/h at 10,000 ft
    roc_fpm = 12800,        -- 65 m/s rate of climb
    ceiling_ft = 54500,     -- service ceiling
  }

  local function v3Len(v)
    return math.sqrt(v.x*v.x + v.y*v.y + v.z*v.z)
  end

  local function msToKt(ms) return ms * 1.943844 end
  local function mToFt(m) return m * 3.28084 end
  local function msToFpm(ms) return ms * 196.85 end

  local function machAtAlt(spd_ms, alt_m)
    local temp_k = math.max(216.65, 288.15 - alt_m * 0.0065)
    local sos = 20.05 * math.sqrt(temp_k)
    return spd_ms / sos
  end

  local function log(msg)
    env.info("[MIG17_FM_TEST] " .. msg)
  end

  -- MiG-17F weight and fuel constants
  MIG17_TEST.FUEL_MAX_KG = 1140         -- Internal fuel capacity
  MIG17_TEST.EMPTY_WEIGHT_KG = 3920     -- Empty weight with pilot
  MIG17_TEST.NOMINAL_WEIGHT_KG = 5345   -- Empty + full internal fuel

  -- Afterburner engages at full throttle (ForsRUD=1 in mig17f.lua)
  -- Military power: 2650 kgf, Afterburner: 3380 kgf (1.28x)
  -- Fuel consumption: cemax=1.24 (military), cefor=2.56 (AB ~2.06x)

  local function initState(name)
    if not MIG17_TEST.state[name] then
      MIG17_TEST.state[name] = {
        t0 = nil,
        speedGates = {},
        altGates = {},
        lastSample = nil,
        lastAlt = nil,
        lastSpd = nil,
        maxSpd = 0,
        maxAlt = 0,
        maxVspd = 0,
        vmaxReported = false,
        stableCount = 0,
        initialFuel = nil,
        lastFuel = nil,
      }
    end
    return MIG17_TEST.state[name]
  end

  local function updateGroup(name, now)
    local st = initState(name)
    local g = Group.getByName(name)
    if not g then return end

    local units = g:getUnits()
    if not units or #units == 0 then return end

    local u = units[1]
    if not (u and u:isExist()) then return end

    local pt = u:getPoint()
    local vel = u:getVelocity()
    if not (pt and vel) then return end

    local alt_m = pt.y or 0
    local alt_ft = mToFt(alt_m)
    local spd_ms = v3Len(vel)
    local spd_kt = msToKt(spd_ms)
    local mach = machAtAlt(spd_ms, alt_m)

    local vspd_fpm = 0
    if st.lastAlt and st.lastSample then
      local dt = now - st.lastSample
      if dt > 0 then
        local dalt = alt_m - st.lastAlt
        vspd_fpm = msToFpm(dalt / dt)
      end
    end

    -- Track fuel state (fuel is in kg for MiG-17F)
    local fuel_kg = 0
    local fuel_pct = 0
    if u.getFuel then
      fuel_pct = u:getFuel() * 100  -- getFuel returns 0.0-1.0
      fuel_kg = fuel_pct * MIG17_TEST.FUEL_MAX_KG / 100
    end

    if not st.t0 then
      st.t0 = now
      st.initialFuel = fuel_kg
      local weight_kg = MIG17_TEST.EMPTY_WEIGHT_KG + fuel_kg
      log(string.format("START,%s,alt=%.0f,spd=%.0f,fuel_kg=%.0f,fuel_pct=%.0f,weight_kg=%.0f",
          name, alt_ft, spd_kt, fuel_kg, fuel_pct, weight_kg))
    end

    st.lastFuel = fuel_kg

    local elapsed = now - st.t0

    if spd_kt > st.maxSpd then st.maxSpd = spd_kt end
    if alt_ft > st.maxAlt then st.maxAlt = alt_ft end
    if vspd_fpm > st.maxVspd then st.maxVspd = vspd_fpm end

    if (not st.lastSample) or (now - st.lastSample >= MIG17_TEST.samplePeriod) then
      log(string.format("DATA,%s,%.1f,%.0f,%.1f,%.0f,%.3f",
          name, elapsed, alt_ft, spd_kt, vspd_fpm, mach))
      st.lastSample = now
    end

    for i, gateKt in ipairs(MIG17_TEST.SPEED_GATES_KT) do
      if not st.speedGates[i] and spd_kt >= gateKt then
        st.speedGates[i] = elapsed
        log(string.format("SPEED_GATE,%s,%.0f,%.1f,%.0f", name, gateKt, elapsed, alt_ft))
      end
    end

    if name:find("CLIMB") then
      for i, gateFt in ipairs(MIG17_TEST.ALT_GATES_FT) do
        if not st.altGates[i] and alt_ft >= gateFt then
          st.altGates[i] = elapsed
          log(string.format("ALT_GATE,%s,%.0f,%.1f,%.0f", name, gateFt, elapsed, vspd_fpm))
        end
      end
    end

    if name:find("VMAX") and elapsed > 30 and not st.vmaxReported then
      if st.lastSpd then
        local delta = math.abs(spd_kt - st.lastSpd)
        if delta < 2 then
          st.stableCount = st.stableCount + 1
          if st.stableCount >= 10 then
            log(string.format("VMAX,%s,%.1f,%.0f,%.3f", name, spd_kt, alt_ft, mach))
            st.vmaxReported = true
          end
        else
          st.stableCount = 0
        end
      end
    end

    st.lastAlt = alt_m
    st.lastSpd = spd_kt
  end

  local function updateAll(args, time)
    local now = time or timer.getTime()
    for _, name in ipairs(MIG17_TEST.GROUPS) do
      updateGroup(name, now)
    end
    return now + MIG17_TEST.samplePeriod
  end

  local function reportSummary()
    log("=== SUMMARY ===")
    log(string.format("TARGETS: Vmax_SL=%dkt, Vmax_10K=%dkt, ROC=%dfpm, Ceiling=%dft",
        MIG17_TEST.TARGETS.vmax_sl_kt, MIG17_TEST.TARGETS.vmax_10k_kt,
        MIG17_TEST.TARGETS.roc_fpm, MIG17_TEST.TARGETS.ceiling_ft))
    log(string.format("FUEL: max=%dkg, AB_consumption_ratio=2.06x",
        MIG17_TEST.FUEL_MAX_KG))
    for _, name in ipairs(MIG17_TEST.GROUPS) do
      local st = MIG17_TEST.state[name]
      if st and st.t0 then
        local fuel_used = (st.initialFuel or 0) - (st.lastFuel or 0)
        log(string.format("SUMMARY,%s,%.1f,%.0f,%.0f,fuel_start=%.0f,fuel_end=%.0f,fuel_used=%.0f",
            name, st.maxSpd, st.maxAlt, st.maxVspd,
            st.initialFuel or 0, st.lastFuel or 0, fuel_used))
      end
    end
    log("=== END SUMMARY ===")
    return nil
  end

  log("MiG-17 FM test logger v2 initializing")
  log(string.format("Targets: Vmax_SL=%dkt Vmax_10K=%dkt ROC=%dfpm",
      MIG17_TEST.TARGETS.vmax_sl_kt, MIG17_TEST.TARGETS.vmax_10k_kt,
      MIG17_TEST.TARGETS.roc_fpm))
  timer.scheduleFunction(updateAll, {}, timer.getTime() + 1)
  timer.scheduleFunction(reportSummary, {}, timer.getTime() + 600)
end
'''


LOGGER = logging.getLogger(__name__)


# Conversion helpers
FT_TO_METERS = 0.3048
KTS_TO_MPS = 0.514444
NM_TO_METERS = 1852.0

# MiG-17F weight and fuel specifications (from mig17f.lua)
MIG17_EMPTY_KG = 3920       # Empty weight with pilot (M_empty)
MIG17_NOMINAL_KG = 5345     # Empty + full internal fuel (M_nominal)
MIG17_MAX_KG = 6075         # Maximum takeoff weight (M_max)
MIG17_FUEL_MAX_KG = 1140    # Internal fuel capacity (M_fuel_max)

# Fuel settings for test profiles
# Different tests use different fuel loads to simulate realistic conditions:
# - Acceleration/Vmax tests: 50% fuel for consistent mid-mission weight
# - Climb tests: Full fuel to match historical "clean config from takeoff" data
# - Turn tests: 50% fuel for typical combat maneuvering weight
MIG17_FUEL_FRACTION_DEFAULT = 0.50  # 50% internal fuel (570 kg)


@dataclass(frozen=True)
class WaypointSpec:
    """Declarative waypoint definition used to build pydcs mission points."""

    x: float
    y: float
    alt_ft: Optional[float] = None
    speed_kts: Optional[float] = None
    tasks: tuple[task.Task, ...] = ()

    def altitude_meters(self, default_alt_ft: float) -> float:
        alt_ft = self.alt_ft if self.alt_ft is not None else default_alt_ft
        return alt_ft * FT_TO_METERS

    def speed_kph(self, default_speed_kts: float) -> float:
        speed_kts = self.speed_kts if self.speed_kts is not None else default_speed_kts
        return speed_kts * 1.852

    def speed_mps(self, default_speed_kts: float) -> float:
        speed_kts = self.speed_kts if self.speed_kts is not None else default_speed_kts
        return speed_kts * KTS_TO_MPS


def detect_type_name(mod_root: Path) -> Optional[str]:
    """Read the MiG-17 database Lua to determine the DCS unit type name."""

    db_file = mod_root / "Database" / "mig17f.lua"
    if not db_file.exists():
        return None

    content = db_file.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"Name\s*=\s*['\"]([^'\"]+)", content)
    if match:
        return match.group(1).strip()
    return None


def get_or_create_custom_plane(type_name: str) -> planes.PlaneType:
    """Register a minimal custom plane type so pydcs can serialize the mod aircraft.

    The MiG-17F has the following fuel characteristics:
    - Internal fuel capacity: 1140 kg (M_fuel_max in mig17f.lua)
    - Empty weight: 3920 kg (with pilot)
    - Nominal weight: 5345 kg (empty + full internal fuel)
    - Max takeoff weight: 6075 kg

    Engine fuel consumption (VK-1F turbojet with afterburner):
    - Military power: cemax = 1.24 (reference multiplier)
    - Afterburner: cefor = 2.56 (approximately 2.06x military power)

    Afterburner behavior:
    - has_afteburner = true
    - ForsRUD = 1 (afterburner engages at full throttle)
    - Military thrust: 2650 kgf (26.5 kN)
    - Afterburner thrust: 3380 kgf (33.8 kN) - 1.28x multiplier
    """
    existing = planes.plane_map.get(type_name)
    if existing:
        return existing

    class CustomPlaneType(planes.PlaneType):
        id = type_name
        name = type_name
        display_name = type_name
        task_default = task.CAP
        # MiG-17F internal fuel capacity in kg
        fuel_max = MIG17_FUEL_MAX_KG

    planes.plane_map[type_name] = CustomPlaneType
    return CustomPlaneType


def ensure_parent(path: Path) -> None:
    """Create parent directories for the output path if needed."""

    path.parent.mkdir(parents=True, exist_ok=True)


def build_mission(type_name: str) -> tuple[mission.Mission, list[str]]:
    """Construct the mission object populated with test groups."""

    miz = mission.Mission()
    miz.terrain = caucasus.Caucasus()
    miz.start_time = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)

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

    red = miz.coalition["red"]
    russia = red.add_country(countries.Russia())
    custom_plane = get_or_create_custom_plane(type_name)

    groups: list[str] = []
    # Black Sea, grid CH area (over ocean)
    x_origin = -275000
    y_origin = 200000

    def add_group(
        name: str,
        alt_ft: float,
        speed_kts: float,
        waypoints: Iterable[WaypointSpec],
        fuel_fraction: float = MIG17_FUEL_FRACTION_DEFAULT,
    ) -> None:
        """Add a flight group to the mission.

        Args:
            name: Group name (used for logging and identification)
            alt_ft: Initial altitude in feet
            speed_kts: Initial speed in knots
            waypoints: Iterable of WaypointSpec defining the flight path
            fuel_fraction: Fuel load as fraction of max (0.0-1.0), default 50%

        Note on fuel and weight:
            The MiG-17F's performance varies significantly with fuel load:
            - Empty weight: 3920 kg
            - Full fuel (+1140 kg): 5060 kg clean, 5345 kg nominal
            - Historical Vmax/ROC data typically at nominal weight (full fuel)

            The AI will use afterburner (ForsRUD=1) when throttle is at maximum.
            Afterburner increases fuel consumption by ~2.06x (cefor/cemax ratio).
        """
        waypoint_list = list(waypoints)
        if not waypoint_list:
            msg = f"Group {name} has no waypoints defined"
            raise ValueError(msg)

        altitude_m = alt_ft * FT_TO_METERS
        first_wp = waypoint_list[0]
        grp = miz.flight_group_inflight(
            country=russia,
            name=name,
            aircraft_type=custom_plane,
            position=mapping.Point(first_wp.x, first_wp.y, altitude_m),
            altitude=altitude_m,
            speed=speed_kts * 1.852,
            maintask=task.CAP,
            group_size=1,
        )
        if grp not in russia.plane_group:
            russia.add_aircraft_group(grp)

        first_unit = grp.units[0]
        first_unit.livery_id = getattr(first_unit, "livery_id", None) or "default"

        # Set fuel explicitly using the MiG-17F's known fuel capacity
        # Do NOT rely on first_unit.fuel having a valid initial value
        fuel_kg = int(MIG17_FUEL_MAX_KG * max(0.0, min(1.0, fuel_fraction)))
        first_unit.fuel = fuel_kg

        start_point = grp.points[0]
        start_point.position.x = first_wp.x
        start_point.position.y = first_wp.y
        start_point.alt = altitude_m
        start_point.speed = speed_kts * KTS_TO_MPS

        for wp in waypoint_list[1:]:
            wp_alt_m = wp.altitude_meters(alt_ft)
            pt = grp.add_waypoint(
                pos=mapping.Point(wp.x, wp.y, wp_alt_m),
                altitude=wp_alt_m,
                speed=wp.speed_kph(speed_kts),
            )
            pt.speed = wp.speed_mps(speed_kts)
            pt.alt = wp_alt_m
            for wp_task in wp.tasks:
                pt.tasks.append(wp_task)
        groups.append(name)

    def orbit_task(
        *, race_track: bool, altitude_ft: float, speed_kts: float, radius_nm: float
    ) -> task.Task:
        alt_m = altitude_ft * FT_TO_METERS
        speed_mps = speed_kts * KTS_TO_MPS
        radius_m = radius_nm * NM_TO_METERS
        if hasattr(task, "OrbitAction"):
            pattern_enum = getattr(task.OrbitAction, "OrbitPattern", None)
            pattern = (
                pattern_enum.RaceTrack if race_track else pattern_enum.Circle
            ) if pattern_enum else None
            return task.OrbitAction(
                pattern=pattern or race_track, altitude=alt_m, speed=speed_mps
            )
        if hasattr(task, "Orbit"):
            return task.Orbit(
                altitude=alt_m,
                speed=speed_mps,
                pattern="Race" if race_track else "Circle",
                length=radius_m,
            )
        msg = "Orbit task is not available in the installed dcs library"
        raise RuntimeError(msg)

    add_group(
        "ACCEL_SL",
        alt_ft=1000,
        speed_kts=230,
        waypoints=[
            WaypointSpec(x=x_origin + 5000, y=y_origin),
            WaypointSpec(
                x=x_origin + 5000 + 50 * NM_TO_METERS, y=y_origin, speed_kts=800
            ),
            WaypointSpec(
                x=x_origin + 5000 + 60 * NM_TO_METERS,
                y=y_origin,
                speed_kts=800,
                tasks=(
                    orbit_task(
                        race_track=True, altitude_ft=1000, speed_kts=800, radius_nm=10
                    ),
                ),
            ),
        ],
    )

    add_group(
        "ACCEL_10K",
        alt_ft=10000,
        speed_kts=300,
        waypoints=[
            WaypointSpec(x=x_origin, y=y_origin + 5000),
            WaypointSpec(
                x=x_origin, y=y_origin + 5000 + 50 * NM_TO_METERS, speed_kts=800
            ),
            WaypointSpec(
                x=x_origin,
                y=y_origin + 5000 + 60 * NM_TO_METERS,
                speed_kts=800,
                tasks=(
                    orbit_task(
                        race_track=True,
                        altitude_ft=10000,
                        speed_kts=800,
                        radius_nm=10,
                    ),
                ),
            ),
        ],
    )

    add_group(
        "ACCEL_20K",
        alt_ft=20000,
        speed_kts=300,
        waypoints=[
            WaypointSpec(x=x_origin - 5000, y=y_origin),
            WaypointSpec(
                x=x_origin - 5000, y=y_origin + 50 * NM_TO_METERS, speed_kts=800
            ),
            WaypointSpec(
                x=x_origin - 5000,
                y=y_origin + 60 * NM_TO_METERS,
                speed_kts=800,
                tasks=(
                    orbit_task(
                        race_track=True,
                        altitude_ft=20000,
                        speed_kts=800,
                        radius_nm=10,
                    ),
                ),
            ),
        ],
    )

    # Climb tests - starting from low altitude, climbing to high altitude
    # Target: 65 m/s (12,800 fpm) rate of climb
    # Historical ROC data is at nominal weight (full internal fuel)
    # Afterburner engages at full throttle (ForsRUD=1) providing 3380 kgf thrust
    add_group(
        "CLIMB_SL",
        alt_ft=1000,
        speed_kts=380,
        waypoints=[
            WaypointSpec(
                x=x_origin + 15000,
                y=y_origin + 15000,
                alt_ft=1000,
                speed_kts=380,
            ),
            WaypointSpec(
                x=x_origin + 15000,
                y=y_origin + 15000 + 30 * NM_TO_METERS,
                alt_ft=40000,
                speed_kts=380,
            ),
        ],
        fuel_fraction=1.0,  # Full fuel for historical ROC comparison
    )

    add_group(
        "CLIMB_10K",
        alt_ft=10000,
        speed_kts=380,
        waypoints=[
            WaypointSpec(
                x=x_origin + 20000,
                y=y_origin - 15000,
                alt_ft=10000,
                speed_kts=380,
            ),
            WaypointSpec(
                x=x_origin + 20000,
                y=y_origin - 15000 + 30 * NM_TO_METERS,
                alt_ft=40000,
                speed_kts=380,
            ),
        ],
        fuel_fraction=1.0,  # Full fuel for historical ROC comparison
    )

    for speed in (300, 350, 400):
        add_group(
            f"TURN_10K_{speed}",
            alt_ft=10000,
            speed_kts=speed,
            waypoints=[
                WaypointSpec(
                    x=x_origin - 15000,
                    y=y_origin - speed * 20,
                    alt_ft=10000,
                    speed_kts=speed,
                ),
                WaypointSpec(
                    x=x_origin - 15000,
                    y=y_origin - speed * 20,
                    alt_ft=10000,
                    speed_kts=speed,
                    tasks=(
                        orbit_task(
                            race_track=False,
                            altitude_ft=10000,
                            speed_kts=speed,
                            radius_nm=6,
                        ),
                    ),
                ),
            ],
        )

    add_group(
        "DECEL_10K",
        alt_ft=10000,
        speed_kts=400,
        waypoints=[
            WaypointSpec(
                x=x_origin + 30000,
                y=y_origin,
                alt_ft=10000,
                speed_kts=400,
            ),
            WaypointSpec(
                x=x_origin + 30000 + 40 * NM_TO_METERS,
                y=y_origin,
                alt_ft=10000,
                speed_kts=200,
            ),
        ],
    )

    # Max speed tests - level flight to determine Vmax
    # Target: 593 kt at SL, 618 kt at 10,000 ft
    add_group(
        "VMAX_SL",
        alt_ft=1000,
        speed_kts=400,
        waypoints=[
            WaypointSpec(
                x=x_origin - 30000,
                y=y_origin + 30000,
                alt_ft=1000,
                speed_kts=400,
            ),
            WaypointSpec(
                x=x_origin - 30000 + 80 * NM_TO_METERS,
                y=y_origin + 30000,
                alt_ft=1000,
                speed_kts=700,
            ),
        ],
    )

    add_group(
        "VMAX_10K",
        alt_ft=10000,
        speed_kts=400,
        waypoints=[
            WaypointSpec(
                x=x_origin - 30000,
                y=y_origin - 30000,
                alt_ft=10000,
                speed_kts=400,
            ),
            WaypointSpec(
                x=x_origin - 30000 + 80 * NM_TO_METERS,
                y=y_origin - 30000,
                alt_ft=10000,
                speed_kts=700,
            ),
        ],
    )

    # Add mission start trigger with the logging script
    # Using TriggerStart with DoScript is more reliable than init_script
    trig = triggers.TriggerStart(comment="MiG-17 FM Test Logger")
    trig.add_action(action.DoScript(action.String(LOGGER_LUA)))
    miz.triggerrules.triggers.append(trig)

    return miz, groups


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate MiG-17 FM test mission")
    parser.add_argument(
        "--outfile",
        default=Path.home() / "Saved Games" / "DCS" / "Missions" / "MiG17F_FM_Test.miz",
        type=Path,
        help="Path to output .miz file (directories will be created)",
    )
    parser.add_argument(
        "--type-name",
        dest="type_name",
        help="Override the aircraft type name (defaults to value from Database/mig17f.lua)",
    )
    parser.add_argument(
        "--mod-root",
        default=Path.cwd() / "[VWV] MiG-17",
        type=Path,
        help="Path to the MiG-17 mod folder containing Database/mig17f.lua",
    )
    return parser.parse_args()


def main() -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s"
        )

    args = parse_args()

    type_name = args.type_name or detect_type_name(args.mod_root)
    if not type_name:
        LOGGER.error(
            "Could not determine MiG-17 type name. Use --type-name to set it explicitly."
        )
        return 2

    ensure_parent(args.outfile)

    try:
        miz, groups = build_mission(type_name)
    except Exception as exc:  # pragma: no cover - runtime creation errors
        LOGGER.exception("Failed to build mission: %s", exc)
        return 4

    try:
        miz.save(args.outfile)
    except Exception as exc:  # pragma: no cover
        LOGGER.exception("Failed to save mission: %s", exc)
        return 5

    LOGGER.info("MiG-17 FM test mission generated.")
    LOGGER.info("Output : %s", args.outfile)
    LOGGER.info("Type   : %s", type_name)
    LOGGER.info("Groups :")
    for name in groups:
        LOGGER.info("  - %s", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
