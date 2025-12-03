"""Generate a MiG-17 flight-model test mission using pydcs.

This script builds a mission with acceleration, climb, turn, and deceleration
profiles for the VWV MiG-17F mod. It requires Python 3 and the ``dcs`` library
(pydcs). Install dependencies with ``pip install dcs``.
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import dcs.liveries_scanner as liveries_scanner


def stub_pydcs_liveries() -> None:
    """Prevent pydcs from scanning liveries during import on fresh systems.

    On Windows without a DCS install, importing pydcs triggers a livery scan that
    assumes certain Lua variables exist, raising ``KeyError`` (e.g. ``country_list``)
    before this script can run. Pre-populating the liveries map skips that eager
    initialization so the rest of pydcs can import safely.
    """

    if liveries_scanner.Liveries.map:
        return

    liveries_scanner.Liveries.map["__stub__"] = liveries_scanner.LiverySet("__stub__")


stub_pydcs_liveries()

from dcs import countries, mapping, mission, planes, task, triggers, unit
from dcs import weather
from dcs.terrain import caucasus


LOGGER_LUA = r'''
  do
    -- MiG-17 FM test logger
    local GROUPS = {
      "ACCEL_SL", "ACCEL_10K", "ACCEL_20K",
      "CLIMB_0K_380", "CLIMB_10K_380",
      "TURN_10K_300", "TURN_10K_350", "TURN_10K_400",
      "DECEL_10K_325",
    }

    local sample_period = 1.0  -- seconds

    local SPEED_GATES_MS  = { 200, 250, 280, 300 }
    local SPEED_GATES_KT  = { 389, 486, 544, 583 }

    local state = {}

    local function v3Len(v)
      return math.sqrt(v.x*v.x + v.y*v.y + v.z*v.z)
    end

    local function msToKt(ms) return ms * 1.943844 end
    local function mToFt(m)  return m  * 3.28084  end

    local function log(msg)
      env.info("[MIG17_FM_TEST] " .. msg)
    end

    local function init_group(name)
      if not state[name] then
        state[name] = {
          t0         = nil,
          gateTimes  = {},
          lastSample = nil,
        }
      end
      return state[name]
    end

    local function update_group(name, now)
      local st = init_group(name)
      local g = Group.getByName(name)
      if not g then return end
      local u = g:getUnit(1)
      if not (u and u:isExist()) then return end

      local p = u:getPoint()
      local v = u:getVelocity()
      if not (p and v) then return end

      local alt_ft = mToFt(p.y or 0)
      local spd_ms = v3Len(v)
      local spd_kt = msToKt(spd_ms)

      if not st.t0 then
        st.t0 = now
        log(string.format("%s test started at t=%.1f", name, now))
      end

      if (not st.lastSample) or (now - st.lastSample >= sample_period) then
        st.lastSample = now
        log(string.format("%s t=%.1fs alt=%.0fft spd=%.1fkt",
                          name, now - st.t0, alt_ft, spd_kt))
      end

      for i, gateMs in ipairs(SPEED_GATES_MS) do
        if not st.gateTimes[i] and spd_ms >= gateMs then
          st.gateTimes[i] = now
          local dt     = now - st.t0
          local gateKt = SPEED_GATES_KT[i] or msToKt(gateMs)
          log(string.format(
            "%s crossed %.0f kt (%.0f m/s) at t=%.1fs from start, alt=%.0fft",
            name, gateKt, gateMs, dt, alt_ft
          ))
        end
      end
    end

    local function update_all(args, time)
      local now = time or timer.getTime()
      for _, name in ipairs(GROUPS) do
        update_group(name, now)
      end
      return now + sample_period
    end

    log("MiG-17 FM test logger initializing.")
    timer.scheduleFunction(update_all, {}, timer.getTime() + sample_period)
  end
'''


# Conversion helpers
FT_TO_METERS = 0.3048
KTS_TO_MPS = 0.514444
NM_TO_METERS = 1852.0


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


def get_or_create_custom_plane(type_name: str):
    """Register a minimal custom plane type so pydcs can serialize the mod aircraft."""

    existing = planes.plane_map.get(type_name)
    if existing:
        return existing

    class CustomPlaneType(planes.PlaneType):
        id = type_name
        name = type_name
        display_name = type_name
        task_default = task.CAP

    planes.plane_map[type_name] = CustomPlaneType
    return CustomPlaneType


def ensure_parent(path: Path) -> None:
    """Create parent directories for the output path if needed."""

    path.parent.mkdir(parents=True, exist_ok=True)


def build_mission(type_name: str):
    """Construct the mission object populated with test groups."""

    miz = mission.Mission()
    miz.terrain = caucasus.Caucasus()
    miz.start_time = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)

    # Weather: clear, no wind, standard atmosphere
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

    groups: List[str] = []
    x_origin = 300000
    y_origin = 600000

    def add_group(name: str, alt_ft: float, speed_kts: float, waypoints: List[dict]):
        altitude_m = alt_ft * FT_TO_METERS
        speed_kph = speed_kts * 1.852
        first_wp = waypoints[0]
        grp = miz.flight_group_inflight(
            country=russia,
            name=name,
            aircraft_type=custom_plane,
            position=mapping.Point(first_wp["x"], first_wp["y"], altitude_m),
            altitude=altitude_m,
            speed=speed_kph,
            maintask=task.CAP,
            group_size=1,
        )
        first_unit = grp.units[0]
        first_unit.livery_id = getattr(first_unit, "livery_id", None) or "default"
        if hasattr(first_unit, "fuel"):
            first_unit.fuel = int(first_unit.fuel * 0.5)
        start_point = grp.points[0]
        start_point.position.x = first_wp["x"]
        start_point.position.y = first_wp["y"]
        start_point.alt = altitude_m
        start_point.speed = speed_kts * KTS_TO_MPS

        for wp in waypoints[1:]:
            wp_alt_m = wp.get("alt", alt_ft) * FT_TO_METERS
            wp_speed_kts = wp.get("speed", speed_kts)
            wp_speed_kph = wp_speed_kts * 1.852
            pt = grp.add_waypoint(
                pos=mapping.Point(wp["x"], wp["y"], wp_alt_m),
                altitude=wp_alt_m,
                speed=wp_speed_kph,
            )
            pt.speed = wp_speed_kts * KTS_TO_MPS
            pt.alt = wp_alt_m
            if "tasks" in wp:
                for t in wp["tasks"]:
                    pt.tasks.append(t)
        groups.append(name)

    def orbit_task(race_track: bool, altitude_ft: float, speed_kts: float, radius_nm: float):
        alt_m = altitude_ft * FT_TO_METERS
        speed_mps = speed_kts * KTS_TO_MPS
        radius_m = radius_nm * NM_TO_METERS
        if hasattr(task, "OrbitAction"):
            pattern_enum = getattr(task.OrbitAction, "OrbitPattern", None)
            pattern = (
                pattern_enum.RaceTrack if race_track else pattern_enum.Circle
            ) if pattern_enum else None
            return task.OrbitAction(pattern=pattern or race_track, altitude=alt_m, speed=speed_mps)
        if hasattr(task, "Orbit"):
            return task.Orbit(altitude=alt_m, speed=speed_mps, pattern="Race" if race_track else "Circle", length=radius_m)
        raise RuntimeError("Orbit task is not available in the installed dcs library")

    # Level acceleration tests
    add_group(
        "ACCEL_SL",
        alt_ft=1000,
        speed_kts=230,
        waypoints=[
            {"x": x_origin + 5000, "y": y_origin},
            {"x": x_origin + 5000 + 50 * NM_TO_METERS, "y": y_origin, "speed": 800},
            {
                "x": x_origin + 5000 + 60 * NM_TO_METERS,
                "y": y_origin,
                "speed": 800,
                "tasks": [orbit_task(True, 1000, 800, radius_nm=10)],
            },
        ],
    )

    add_group(
        "ACCEL_10K",
        alt_ft=10000,
        speed_kts=300,
        waypoints=[
            {"x": x_origin, "y": y_origin + 5000},
            {"x": x_origin, "y": y_origin + 5000 + 50 * NM_TO_METERS, "speed": 800},
            {
                "x": x_origin,
                "y": y_origin + 5000 + 60 * NM_TO_METERS,
                "speed": 800,
                "tasks": [orbit_task(True, 10000, 800, radius_nm=10)],
            },
        ],
    )

    add_group(
        "ACCEL_20K",
        alt_ft=20000,
        speed_kts=300,
        waypoints=[
            {"x": x_origin - 5000, "y": y_origin},
            {"x": x_origin - 5000, "y": y_origin + 50 * NM_TO_METERS, "speed": 800},
            {
                "x": x_origin - 5000,
                "y": y_origin + 60 * NM_TO_METERS,
                "speed": 800,
                "tasks": [orbit_task(True, 20000, 800, radius_nm=10)],
            },
        ],
    )

    # Climb tests
    add_group(
        "CLIMB_0K_380",
        alt_ft=1000,
        speed_kts=380,
        waypoints=[
            {"x": x_origin + 15000, "y": y_origin + 15000, "alt": 1000, "speed": 380},
            {"x": x_origin + 15000, "y": y_origin + 15000, "alt": 33000, "speed": 380},
        ],
    )

    add_group(
        "CLIMB_10K_380",
        alt_ft=10000,
        speed_kts=380,
        waypoints=[
            {"x": x_origin + 20000, "y": y_origin - 15000, "alt": 10000, "speed": 380},
            {"x": x_origin + 20000, "y": y_origin - 15000, "alt": 33000, "speed": 380},
        ],
    )

    # Turn tests at 10k
    for speed in (300, 350, 400):
        add_group(
            f"TURN_10K_{speed}",
            alt_ft=10000,
            speed_kts=speed,
            waypoints=[
                {"x": x_origin - 15000, "y": y_origin - speed * 20, "alt": 10000, "speed": speed},
                {
                    "x": x_origin - 15000,
                    "y": y_origin - speed * 20,
                    "alt": 10000,
                    "speed": speed,
                    "tasks": [orbit_task(False, 10000, speed, radius_nm=6)],
                },
            ],
        )

    # Deceleration test
    add_group(
        "DECEL_10K_325",
        alt_ft=10000,
        speed_kts=325,
        waypoints=[
            {"x": x_origin + 30000, "y": y_origin, "alt": 10000, "speed": 325},
            {"x": x_origin + 30000 + 40 * NM_TO_METERS, "y": y_origin, "alt": 10000, "speed": 200},
        ],
    )

    miz.init_script = LOGGER_LUA

    return miz, groups


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate MiG-17 FM test mission")
    parser.add_argument(
        "--outfile",
        default=Path("build") / "MiG17F_FM_Test.miz",
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
    args = parse_args()

    type_name = args.type_name or detect_type_name(args.mod_root)
    if not type_name:
        print("Could not determine MiG-17 type name. Use --type-name to set it explicitly.")
        return 2

    ensure_parent(args.outfile)

    try:
        miz, groups = build_mission(type_name)
    except Exception as exc:  # pragma: no cover - runtime creation errors
        print(f"Failed to build mission: {exc}")
        return 4

    try:
        miz.save(args.outfile)
    except Exception as exc:  # pragma: no cover
        print(f"Failed to save mission: {exc}")
        return 5

    print("MiG-17 FM test mission generated.")
    print(f"  Output : {args.outfile}")
    print(f"  Type   : {type_name}")
    print("  Groups :")
    for name in groups:
        print(f"    - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
