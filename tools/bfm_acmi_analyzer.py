"""Analyze ACMI telemetry files for BFM test metrics.

This module parses TacView ACMI files and extracts BFM-relevant metrics
such as turn rates, energy management, G-loading, and engagement outcomes.

ACMI Format Reference: https://www.tacview.net/documentation/acmi/en/
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Iterator

LOGGER = logging.getLogger(__name__)

# Conversion constants
FT_PER_METER = 3.28084
KT_PER_MPS = 1.94384
FPM_PER_MPS = 196.85
RAD2DEG = 180.0 / math.pi
DEG2RAD = math.pi / 180.0
G0 = 9.80665  # m/s^2


@dataclass
class AircraftState:
    """State of an aircraft at a single time point."""

    time: float
    lon: float
    lat: float
    alt_m: float
    u: Optional[float] = None  # Native X coordinate (meters)
    v: Optional[float] = None  # Native Y coordinate (meters)
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    heading_deg: float = 0.0
    aoa_deg: Optional[float] = None
    tas_mps: Optional[float] = None
    mach: Optional[float] = None


@dataclass
class AircraftTrack:
    """Complete track of an aircraft throughout the engagement."""

    object_id: str
    name: str
    group_name: str
    aircraft_type: str
    coalition: str
    states: list[AircraftState] = field(default_factory=list)


@dataclass
class TurnMetrics:
    """Metrics related to turning performance."""

    max_turn_rate_deg_s: float = 0.0
    avg_turn_rate_deg_s: float = 0.0
    min_turn_radius_ft: float = 0.0
    time_to_360_s: Optional[float] = None


@dataclass
class EnergyMetrics:
    """Metrics related to energy management."""

    initial_speed_kt: float = 0.0
    min_speed_kt: float = 0.0
    max_speed_kt: float = 0.0
    final_speed_kt: float = 0.0
    energy_loss_per_360_kt: Optional[float] = None
    max_altitude_ft: float = 0.0
    min_altitude_ft: float = 0.0
    altitude_variation_ft: float = 0.0


@dataclass
class ManeuveringMetrics:
    """Metrics related to maneuvering."""

    max_g_loading: float = 0.0
    avg_g_loading: float = 0.0
    max_aoa_deg: float = 0.0
    max_bank_deg: float = 0.0


@dataclass
class EngagementMetrics:
    """Metrics for the overall engagement."""

    duration_s: float = 0.0
    initial_range_ft: float = 0.0
    min_range_ft: float = 0.0
    time_to_min_range_s: Optional[float] = None
    closure_achieved: bool = False


@dataclass
class BFMAnalysisResult:
    """Complete BFM analysis result for a single engagement."""

    scenario_id: str
    mig17_group: str
    opponent_group: str
    mig17_variant: str
    opponent_type: str
    turn_metrics: TurnMetrics
    energy_metrics: EnergyMetrics
    maneuvering_metrics: ManeuveringMetrics
    engagement_metrics: EngagementMetrics
    envelope_assessment: str  # "NOMINAL", "UNDER", "OVER"
    notes: list[str] = field(default_factory=list)


def iter_acmi_lines(path: Path) -> Iterator[str]:
    """Yield lines from an ACMI file (handles zip compression).

    Args:
        path: Path to .acmi or .zip.acmi file

    Yields:
        Lines from the ACMI file
    """
    with open(path, "rb") as f:
        header = f.read(4)

    if header.startswith(b"PK\x03\x04"):
        # ZIP compressed ACMI
        with zipfile.ZipFile(path, "r") as z:
            info = z.infolist()[0]
            with z.open(info) as f:
                content = f.read().decode("utf-8", errors="replace")
        for line in content.splitlines():
            yield line
    else:
        # Plain text ACMI
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                yield line.rstrip("\n")


def parse_transform(t_value: str, prev_state: Optional[AircraftState]) -> dict:
    """Parse ACMI T= transform value.

    ACMI transform formats:
    - T=Lon|Lat|Alt
    - T=Lon|Lat|Alt|U|V
    - T=Lon|Lat|Alt|Roll|Pitch|Yaw
    - T=Lon|Lat|Alt|Roll|Pitch|Yaw|U|V|Heading

    Args:
        t_value: The T property value string
        prev_state: Previous state for delta compression

    Returns:
        Dict with parsed transform values
    """
    parts = t_value.split("|")
    result = {}

    # Initialize from previous state if available
    if prev_state:
        result = {
            "lon": prev_state.lon,
            "lat": prev_state.lat,
            "alt_m": prev_state.alt_m,
            "u": prev_state.u,
            "v": prev_state.v,
            "roll_deg": prev_state.roll_deg,
            "pitch_deg": prev_state.pitch_deg,
            "yaw_deg": prev_state.yaw_deg,
        }

    # Parse lon/lat/alt (always first 3)
    if len(parts) >= 1 and parts[0]:
        result["lon"] = float(parts[0])
    if len(parts) >= 2 and parts[1]:
        result["lat"] = float(parts[1])
    if len(parts) >= 3 and parts[2]:
        result["alt_m"] = float(parts[2])

    # Determine format and parse accordingly
    if len(parts) == 5:
        # T=Lon|Lat|Alt|U|V
        if parts[3]:
            result["u"] = float(parts[3])
        if parts[4]:
            result["v"] = float(parts[4])
    elif len(parts) >= 6:
        # T=Lon|Lat|Alt|Roll|Pitch|Yaw[|U|V|Heading]
        if parts[3]:
            result["roll_deg"] = float(parts[3])
        if parts[4]:
            result["pitch_deg"] = float(parts[4])
        if parts[5]:
            result["yaw_deg"] = float(parts[5])
        if len(parts) >= 7 and parts[6]:
            result["u"] = float(parts[6])
        if len(parts) >= 8 and parts[7]:
            result["v"] = float(parts[7])
        if len(parts) >= 9 and parts[8]:
            result["heading_deg"] = float(parts[8])

    return result


def isa_speed_of_sound(alt_m: float) -> float:
    """Calculate speed of sound at altitude using ISA model.

    Args:
        alt_m: Altitude in meters

    Returns:
        Speed of sound in m/s
    """
    t0 = 288.15  # Sea level temp (K)
    lapse = -0.0065  # K/m in troposphere

    if alt_m < 11000.0:
        temp = t0 + lapse * alt_m
    else:
        temp = 216.65  # Constant in stratosphere

    return math.sqrt(1.4 * 287.05 * temp)


def parse_acmi_file(path: Path) -> dict[str, AircraftTrack]:
    """Parse an ACMI file and extract aircraft tracks.

    Args:
        path: Path to the ACMI file

    Returns:
        Dict mapping object_id to AircraftTrack
    """
    tracks: dict[str, AircraftTrack] = {}
    object_properties: dict[str, dict] = {}
    current_time = 0.0

    for line in iter_acmi_lines(path):
        if not line:
            continue

        # Remove BOM if present
        line = line.lstrip("\ufeff")

        # Skip comments and header
        if line.startswith("//") or line.startswith("FileType") or line.startswith("FileVersion"):
            continue

        # Time marker
        if line.startswith("#"):
            try:
                current_time = float(line[1:])
            except ValueError:
                pass
            continue

        # Skip lines without comma (property lines for global object)
        if "," not in line:
            continue

        # Parse object record
        obj_id, rest = line.split(",", 1)

        # Handle object removal
        if obj_id.startswith("-"):
            continue

        # Parse properties
        props = {}
        for segment in rest.split(","):
            if "=" in segment:
                key, value = segment.split("=", 1)
                props[key] = value

        # Initialize or update object properties
        if obj_id not in object_properties:
            object_properties[obj_id] = {}
        object_properties[obj_id].update(props)

        obj_props = object_properties[obj_id]

        # Only track aircraft (FixedWing type)
        obj_type = obj_props.get("Type", "")
        if "FixedWing" not in obj_type and "Air" not in obj_type:
            continue

        # Get or create track
        if obj_id not in tracks:
            tracks[obj_id] = AircraftTrack(
                object_id=obj_id,
                name=obj_props.get("Name", "Unknown"),
                group_name=obj_props.get("Group", ""),
                aircraft_type=obj_props.get("Name", "Unknown"),
                coalition=obj_props.get("Coalition", ""),
            )

        track = tracks[obj_id]

        # Update name/group if newly available
        if "Name" in props:
            track.name = props["Name"]
            track.aircraft_type = props["Name"]
        if "Group" in props:
            track.group_name = props["Group"]
        if "Coalition" in props:
            track.coalition = props["Coalition"]

        # Parse transform if present
        if "T" not in props:
            continue

        prev_state = track.states[-1] if track.states else None
        try:
            transform = parse_transform(props["T"], prev_state)
        except (ValueError, IndexError):
            continue

        # Create state
        state = AircraftState(
            time=current_time,
            lon=transform.get("lon", 0.0),
            lat=transform.get("lat", 0.0),
            alt_m=transform.get("alt_m", 0.0),
            u=transform.get("u"),
            v=transform.get("v"),
            roll_deg=transform.get("roll_deg", 0.0),
            pitch_deg=transform.get("pitch_deg", 0.0),
            yaw_deg=transform.get("yaw_deg", 0.0),
            heading_deg=transform.get("heading_deg", transform.get("yaw_deg", 0.0)),
        )

        # Parse additional properties
        if "AOA" in props:
            try:
                state.aoa_deg = float(props["AOA"])
            except ValueError:
                pass
        if "TAS" in props:
            try:
                state.tas_mps = float(props["TAS"])
            except ValueError:
                pass
        if "Mach" in props:
            try:
                state.mach = float(props["Mach"])
            except ValueError:
                pass

        track.states.append(state)

    return tracks


def calculate_derived_values(track: AircraftTrack) -> None:
    """Calculate derived values like speed from position changes.

    Updates the track states in place with calculated TAS if not present.

    Args:
        track: Aircraft track to process
    """
    for i in range(1, len(track.states)):
        curr = track.states[i]
        prev = track.states[i - 1]

        dt = curr.time - prev.time
        if dt <= 0:
            continue

        # Calculate ground speed from U/V coordinates if available
        if curr.u is not None and prev.u is not None and curr.v is not None and prev.v is not None:
            du = curr.u - prev.u
            dv = curr.v - prev.v
            ground_speed_mps = math.hypot(du, dv) / dt

            # If no TAS provided, use ground speed as approximation
            if curr.tas_mps is None:
                curr.tas_mps = ground_speed_mps


def calculate_turn_rate(track: AircraftTrack, start_idx: int, end_idx: int) -> float:
    """Calculate average turn rate over a segment.

    Args:
        track: Aircraft track
        start_idx: Start state index
        end_idx: End state index

    Returns:
        Turn rate in degrees per second
    """
    if end_idx <= start_idx or end_idx >= len(track.states):
        return 0.0

    start_state = track.states[start_idx]
    end_state = track.states[end_idx]

    dt = end_state.time - start_state.time
    if dt <= 0:
        return 0.0

    # Calculate heading change
    heading_change = end_state.heading_deg - start_state.heading_deg

    # Normalize to -180 to 180
    while heading_change > 180:
        heading_change -= 360
    while heading_change < -180:
        heading_change += 360

    return abs(heading_change) / dt


def calculate_instantaneous_turn_rate(track: AircraftTrack) -> list[float]:
    """Calculate instantaneous turn rate at each point using U/V ground track.

    Uses position changes to compute heading, then turn rate from heading
    changes. This is more reliable than using the heading field directly.

    Args:
        track: Aircraft track

    Returns:
        List of turn rates (deg/s) for each state
    """
    n = len(track.states)
    if n < 2:
        return [0.0] * n

    # First compute ground-track heading from U/V position changes
    headings_rad = [0.0] * n
    speeds_mps = [0.0] * n

    for i in range(1, n):
        curr = track.states[i]
        prev = track.states[i - 1]

        dt = curr.time - prev.time
        if dt <= 0 or dt > 5.0:
            headings_rad[i] = headings_rad[i - 1]
            speeds_mps[i] = speeds_mps[i - 1]
            continue

        # Use U/V coordinates if available
        if curr.u is not None and prev.u is not None and curr.v is not None and prev.v is not None:
            du = curr.u - prev.u
            dv = curr.v - prev.v
            vx = du / dt
            vy = dv / dt
            speed = math.hypot(vx, vy)
            heading = math.atan2(vy, vx)  # -pi..pi

            speeds_mps[i] = speed
            headings_rad[i] = heading
        else:
            # Fall back to heading field
            headings_rad[i] = curr.heading_deg * DEG2RAD
            if curr.tas_mps:
                speeds_mps[i] = curr.tas_mps
            else:
                speeds_mps[i] = speeds_mps[i - 1]

    # Copy first element
    if n >= 2:
        speeds_mps[0] = speeds_mps[1]
        headings_rad[0] = headings_rad[1]

    # Unwrap heading to get continuous curve
    unwrapped = [headings_rad[0]]
    for i in range(1, n):
        delta = headings_rad[i] - headings_rad[i - 1]
        # Wrap to [-pi, pi]
        while delta > math.pi:
            delta -= 2 * math.pi
        while delta < -math.pi:
            delta += 2 * math.pi
        unwrapped.append(unwrapped[-1] + delta)

    # Compute turn rate from heading changes
    turn_rates = [0.0] * n
    for i in range(1, n):
        dt = track.states[i].time - track.states[i - 1].time
        if dt <= 0 or dt > 5.0:
            turn_rates[i] = 0.0
            continue
        dpsi = unwrapped[i] - unwrapped[i - 1]  # rad
        turn_rates[i] = abs(dpsi / dt) * RAD2DEG

    # Apply 3-point moving average smoothing
    smoothed = turn_rates[:]
    for i in range(1, n - 1):
        smoothed[i] = (turn_rates[i - 1] + turn_rates[i] + turn_rates[i + 1]) / 3.0

    # Store computed speeds in track states for G calculation
    for i, state in enumerate(track.states):
        if state.tas_mps is None:
            state.tas_mps = speeds_mps[i]

    return smoothed


def calculate_g_loading(
    track: AircraftTrack,
    turn_rates: list[float],
    v_min_turn_kt: float = 150.0,
) -> list[float]:
    """Estimate G-loading from turn rate and speed using centripetal acceleration.

    G = v * omega / g0 (where omega is in rad/s)

    This is more accurate than the bank-angle method because it directly
    measures the actual centripetal acceleration being experienced.

    Args:
        track: Aircraft track
        turn_rates: Turn rates in deg/s for each state
        v_min_turn_kt: Minimum speed to consider for turn calculations

    Returns:
        List of estimated G values
    """
    g_values = []
    v_min_turn_mps = v_min_turn_kt / KT_PER_MPS
    omega_min_rad_s = 1.0 * DEG2RAD  # Ignore turns below 1 deg/s

    for i, state in enumerate(track.states):
        v = state.tas_mps if state.tas_mps else 0.0
        omega_deg_s = turn_rates[i] if i < len(turn_rates) else 0.0
        omega_rad_s = abs(omega_deg_s) * DEG2RAD

        if v > v_min_turn_mps and omega_rad_s > omega_min_rad_s:
            g = v * omega_rad_s / G0
        else:
            g = 0.0

        g_values.append(g)

    return g_values


def calculate_turn_radius(
    track: AircraftTrack,
    turn_rates: list[float],
    v_min_turn_kt: float = 150.0,
) -> list[Optional[float]]:
    """Calculate instantaneous turn radius at each point.

    R = V / omega (V in m/s, omega in rad/s)

    Args:
        track: Aircraft track
        turn_rates: Turn rates in deg/s for each state
        v_min_turn_kt: Minimum speed to consider for turn calculations

    Returns:
        List of turn radii in feet (None for non-turning points)
    """
    radii: list[Optional[float]] = []
    v_min_turn_mps = v_min_turn_kt / KT_PER_MPS
    omega_min_rad_s = 1.0 * DEG2RAD  # Ignore turns below 1 deg/s

    for i, state in enumerate(track.states):
        v = state.tas_mps if state.tas_mps else 0.0
        omega_deg_s = turn_rates[i] if i < len(turn_rates) else 0.0
        omega_rad_s = abs(omega_deg_s) * DEG2RAD

        if v > v_min_turn_mps and omega_rad_s > omega_min_rad_s:
            r_m = v / omega_rad_s
            radii.append(r_m * FT_PER_METER)
        else:
            radii.append(None)

    return radii


def calculate_sustained_turn_rate(
    track: AircraftTrack,
    turn_rates: list[float],
    g_values: list[float],
    v_min_turn_kt: float = 150.0,
    tr_min_for_seq_deg_s: float = 8.0,
    min_seq_duration_s: float = 1.5,
) -> dict[str, Optional[float]]:
    """Find the best sustained turn rate segment.

    A sustained turn is a continuous period where the aircraft maintains
    a meaningful turn rate (>= tr_min_for_seq_deg_s) for at least
    min_seq_duration_s seconds.

    Args:
        track: Aircraft track
        turn_rates: Turn rates in deg/s for each state
        g_values: G-loading values for each state
        v_min_turn_kt: Minimum speed to consider for turn calculations
        tr_min_for_seq_deg_s: Minimum turn rate to consider as "turning"
        min_seq_duration_s: Minimum duration of sustained turn segment

    Returns:
        Dict with best_sustained_tr_deg_s, sustained_window_s,
        sustained_speed_kt, sustained_g
    """
    n = len(track.states)
    if n < 5:
        return {
            "best_sustained_tr_deg_s": 0.0,
            "sustained_window_s": 0.0,
            "sustained_speed_kt": None,
            "sustained_g": None,
        }

    best_sust_tr = 0.0
    best_sust_speed: Optional[float] = None
    best_sust_g: Optional[float] = None
    best_sust_dur = 0.0

    in_run = False
    run_start = 0

    for i in range(1, n):
        state = track.states[i]
        speed_kt = (state.tas_mps * KT_PER_MPS) if state.tas_mps else 0.0
        tr = turn_rates[i] if i < len(turn_rates) else 0.0

        # Condition for being "in a turn"
        if abs(tr) >= tr_min_for_seq_deg_s and speed_kt >= v_min_turn_kt:
            if not in_run:
                in_run = True
                run_start = max(0, i - 1)  # Include one prior sample
        else:
            if in_run:
                # Close run at i-1
                run_end = i
                in_run = False

                # Compute duration and average metrics for this run
                result = _compute_run_metrics(
                    track, turn_rates, g_values, run_start, run_end, min_seq_duration_s
                )
                if result and result["avg_tr"] > best_sust_tr:
                    best_sust_tr = result["avg_tr"]
                    best_sust_speed = result["avg_speed"]
                    best_sust_g = result["avg_g"]
                    best_sust_dur = result["duration"]

    # Close run if it extends to the end
    if in_run:
        run_end = n
        result = _compute_run_metrics(
            track, turn_rates, g_values, run_start, run_end, min_seq_duration_s
        )
        if result and result["avg_tr"] > best_sust_tr:
            best_sust_tr = result["avg_tr"]
            best_sust_speed = result["avg_speed"]
            best_sust_g = result["avg_g"]
            best_sust_dur = result["duration"]

    return {
        "best_sustained_tr_deg_s": best_sust_tr,
        "sustained_window_s": best_sust_dur,
        "sustained_speed_kt": best_sust_speed,
        "sustained_g": best_sust_g,
    }


def _compute_run_metrics(
    track: AircraftTrack,
    turn_rates: list[float],
    g_values: list[float],
    run_start: int,
    run_end: int,
    min_seq_duration_s: float,
) -> Optional[dict[str, float]]:
    """Compute metrics for a turn run segment."""
    sum_dt = 0.0
    sum_tr_dt = 0.0
    sum_speed_dt = 0.0
    sum_g_dt = 0.0

    for j in range(run_start + 1, run_end):
        prev_state = track.states[j - 1]
        curr_state = track.states[j]
        dt = curr_state.time - prev_state.time
        if dt <= 0 or dt > 5.0:
            continue

        speed_kt = (curr_state.tas_mps * KT_PER_MPS) if curr_state.tas_mps else 0.0
        tr = turn_rates[j] if j < len(turn_rates) else 0.0
        g = g_values[j] if j < len(g_values) else 0.0

        sum_dt += dt
        sum_tr_dt += abs(tr) * dt
        sum_speed_dt += speed_kt * dt
        sum_g_dt += g * dt

    if sum_dt >= min_seq_duration_s and sum_dt > 0:
        return {
            "avg_tr": sum_tr_dt / sum_dt,
            "avg_speed": sum_speed_dt / sum_dt,
            "avg_g": sum_g_dt / sum_dt,
            "duration": sum_dt,
        }
    return None


def calculate_range(state1: AircraftState, state2: AircraftState) -> float:
    """Calculate 3D range between two aircraft states.

    Args:
        state1: First aircraft state
        state2: Second aircraft state

    Returns:
        Range in meters
    """
    if state1.u is not None and state2.u is not None:
        # Use U/V coordinates if available (more accurate)
        dx = state1.u - state2.u
        dy = state1.v - state2.v
        dz = state1.alt_m - state2.alt_m
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    # Fall back to approximate spherical calculation
    lat1 = math.radians(state1.lat)
    lat2 = math.radians(state2.lat)
    lon1 = math.radians(state1.lon)
    lon2 = math.radians(state2.lon)

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    earth_radius_m = 6371000
    horizontal_dist = earth_radius_m * c

    dalt = state1.alt_m - state2.alt_m
    return math.sqrt(horizontal_dist ** 2 + dalt ** 2)


def classify_range(value: Optional[float], vmin: float, vmax: float) -> str:
    """Classify a value against min/max thresholds."""
    if value is None:
        return "N/A"
    if value < vmin:
        return "UNDER"
    if value > vmax:
        return "OVER"
    return "WITHIN"


def classify_g(g: float, warn: float, gmax: float) -> str:
    """Classify G-loading against warning and max thresholds."""
    if g <= warn:
        return "WITHIN"
    if g <= gmax:
        return "WARNING"
    return "OVER"


def classify_radius(
    radius_ft: Optional[float],
    target_min_ft: float,
    tight_factor: float = 0.8,
    loose_factor: float = 1.25,
) -> str:
    """Classify turn radius vs target minimum radius."""
    if radius_ft is None:
        return "N/A"
    if radius_ft < target_min_ft * tight_factor:
        return "TIGHT_OVER"  # Suspiciously tight radius
    if radius_ft > target_min_ft * loose_factor:
        return "LOOSE_UNDER"  # Not using full capability
    return "WITHIN"


def overall_envelope_status(
    inst_status: str,
    sust_status: str,
    g_status: str,
    radius_status: str,
) -> str:
    """Determine combined envelope status."""
    if g_status == "OVER" or inst_status == "OVER" or radius_status == "TIGHT_OVER":
        return "OVER"
    if inst_status == "UNDER" and sust_status == "UNDER":
        return "UNDER"
    return "NOMINAL"


def analyze_engagement(
    mig17_track: AircraftTrack,
    opponent_track: Optional[AircraftTrack],
    envelope_targets: dict,
) -> BFMAnalysisResult:
    """Analyze a BFM engagement between MiG-17 and opponent.

    Args:
        mig17_track: Track of the MiG-17
        opponent_track: Track of the opponent aircraft (optional for single-aircraft analysis)
        envelope_targets: Expected performance envelope values

    Returns:
        BFMAnalysisResult with all metrics
    """
    # Calculate derived values
    calculate_derived_values(mig17_track)
    if opponent_track:
        calculate_derived_values(opponent_track)

    # Get scenario ID from group name
    scenario_id = mig17_track.group_name
    variant = ""
    if "_" in scenario_id and scenario_id.startswith("FM"):
        parts = scenario_id.split("_", 1)
        variant = parts[0]
        scenario_id = parts[1] if len(parts) > 1 else scenario_id

    # Extract envelope thresholds
    sustained_min = envelope_targets.get("sustained_min_deg_s", 12.0)
    sustained_max = envelope_targets.get("sustained_max_deg_s", 17.0)
    instant_min = envelope_targets.get("instantaneous_min_deg_s", 18.0)
    instant_max = envelope_targets.get("instantaneous_max_deg_s", 25.0)
    g_warning = envelope_targets.get("g_warning", 7.0)
    g_max = envelope_targets.get("g_max", 8.0)
    min_turn_radius_ft = envelope_targets.get("min_turn_radius_ft", 2200.0)

    # Calculate turn metrics using new ground-track based method
    turn_rates = calculate_instantaneous_turn_rate(mig17_track)

    # Calculate G-loading using physics-based formula (needs turn_rates)
    g_values = calculate_g_loading(mig17_track, turn_rates)

    # Calculate turn radii
    radii = calculate_turn_radius(mig17_track, turn_rates)

    # Calculate sustained turn rate
    sustained_result = calculate_sustained_turn_rate(
        mig17_track, turn_rates, g_values
    )

    # Find max instantaneous turn rate (with speed filter)
    max_turn_rate = 0.0
    idx_max_tr = 0
    v_min_kt = 150.0
    for i, state in enumerate(mig17_track.states):
        speed_kt = (state.tas_mps * KT_PER_MPS) if state.tas_mps else 0.0
        if speed_kt < v_min_kt:
            continue
        if turn_rates[i] > max_turn_rate:
            max_turn_rate = turn_rates[i]
            idx_max_tr = i

    # Calculate average turn rate (exclude first/last 10%)
    trim = len(turn_rates) // 10
    if len(turn_rates) > 20:
        avg_turn_rate = sum(turn_rates[trim:-trim]) / (len(turn_rates) - 2 * trim)
    else:
        avg_turn_rate = sum(turn_rates) / len(turn_rates) if turn_rates else 0.0

    # Find minimum turn radius
    valid_radii = [r for r in radii if r is not None]
    min_radius = min(valid_radii) if valid_radii else 0.0

    turn_metrics = TurnMetrics(
        max_turn_rate_deg_s=max_turn_rate,
        avg_turn_rate_deg_s=avg_turn_rate,
        min_turn_radius_ft=min_radius,
    )

    # Calculate energy metrics
    speeds_kt = [
        (s.tas_mps * KT_PER_MPS if s.tas_mps else 0.0)
        for s in mig17_track.states
    ]
    altitudes_ft = [s.alt_m * FT_PER_METER for s in mig17_track.states]

    energy_metrics = EnergyMetrics(
        initial_speed_kt=speeds_kt[0] if speeds_kt else 0.0,
        min_speed_kt=min(speeds_kt) if speeds_kt else 0.0,
        max_speed_kt=max(speeds_kt) if speeds_kt else 0.0,
        final_speed_kt=speeds_kt[-1] if speeds_kt else 0.0,
        max_altitude_ft=max(altitudes_ft) if altitudes_ft else 0.0,
        min_altitude_ft=min(altitudes_ft) if altitudes_ft else 0.0,
        altitude_variation_ft=(max(altitudes_ft) - min(altitudes_ft)) if altitudes_ft else 0.0,
    )

    # Calculate maneuvering metrics
    max_g = max(g_values) if g_values else 0.0
    avg_g = sum(g_values) / len(g_values) if g_values else 0.0
    bank_angles = [abs(s.roll_deg) for s in mig17_track.states]
    aoa_values = [s.aoa_deg for s in mig17_track.states if s.aoa_deg is not None]

    maneuvering_metrics = ManeuveringMetrics(
        max_g_loading=max_g,
        avg_g_loading=avg_g,
        max_aoa_deg=max(aoa_values) if aoa_values else 0.0,
        max_bank_deg=max(bank_angles) if bank_angles else 0.0,
    )

    # Calculate engagement metrics
    duration = 0.0
    if mig17_track.states:
        duration = mig17_track.states[-1].time - mig17_track.states[0].time

    ranges_ft: list[float] = []
    if opponent_track and opponent_track.states:
        for mig_state in mig17_track.states:
            # Find closest opponent state in time
            closest_opp = None
            min_time_diff = float("inf")
            for opp_state in opponent_track.states:
                time_diff = abs(opp_state.time - mig_state.time)
                if time_diff < min_time_diff:
                    min_time_diff = time_diff
                    closest_opp = opp_state

            if closest_opp:
                range_m = calculate_range(mig_state, closest_opp)
                ranges_ft.append(range_m * FT_PER_METER)

    engagement_metrics = EngagementMetrics(
        duration_s=duration,
        initial_range_ft=ranges_ft[0] if ranges_ft else 0.0,
        min_range_ft=min(ranges_ft) if ranges_ft else 0.0,
        time_to_min_range_s=None,
        closure_achieved=min(ranges_ft) < ranges_ft[0] if ranges_ft else False,
    )

    # Classify performance against envelope thresholds
    inst_status = classify_range(max_turn_rate, instant_min, instant_max)
    sust_status = classify_range(
        sustained_result["best_sustained_tr_deg_s"], sustained_min, sustained_max
    )
    g_status = classify_g(max_g, g_warning, g_max)
    radius_status = classify_radius(min_radius if min_radius > 0 else None, min_turn_radius_ft)

    envelope_assessment = overall_envelope_status(
        inst_status, sust_status, g_status, radius_status
    )

    # Build notes
    notes = []
    if inst_status == "OVER":
        notes.append(
            f"Max inst TR {max_turn_rate:.1f} deg/s exceeds {instant_max} deg/s [{inst_status}]"
        )
    elif inst_status == "UNDER":
        notes.append(
            f"Max inst TR {max_turn_rate:.1f} deg/s below {instant_min} deg/s [{inst_status}]"
        )

    if g_status == "OVER":
        notes.append(f"Max G {max_g:.2f} exceeds limit {g_max} [{g_status}]")
    elif g_status == "WARNING":
        notes.append(f"Max G {max_g:.2f} above warning threshold {g_warning} [{g_status}]")

    if radius_status == "TIGHT_OVER":
        notes.append(
            f"Min radius {min_radius:.0f} ft below expected {min_turn_radius_ft} ft [{radius_status}]"
        )

    if sustained_result["best_sustained_tr_deg_s"] > 0:
        notes.append(
            f"Best sustained TR: {sustained_result['best_sustained_tr_deg_s']:.1f} deg/s "
            f"over {sustained_result['sustained_window_s']:.1f}s [{sust_status}]"
        )

    return BFMAnalysisResult(
        scenario_id=scenario_id,
        mig17_group=mig17_track.group_name,
        opponent_group=opponent_track.group_name if opponent_track else "",
        mig17_variant=variant,
        opponent_type=opponent_track.aircraft_type if opponent_track else "",
        turn_metrics=turn_metrics,
        energy_metrics=energy_metrics,
        maneuvering_metrics=maneuvering_metrics,
        engagement_metrics=engagement_metrics,
        envelope_assessment=envelope_assessment,
        notes=notes,
    )


def find_engagement_pairs(tracks: dict[str, AircraftTrack]) -> list[tuple[AircraftTrack, AircraftTrack]]:
    """Find MiG-17 / opponent pairs from tracks.

    Args:
        tracks: Dict of object_id to AircraftTrack

    Returns:
        List of (mig17_track, opponent_track) tuples
    """
    pairs = []

    # Group tracks by group name
    by_group = {}
    for track in tracks.values():
        if track.group_name:
            by_group[track.group_name] = track

    # Find pairs where one group name ends with "_OPP"
    for group_name, track in by_group.items():
        if group_name.endswith("_OPP"):
            mig17_group = group_name[:-4]  # Remove "_OPP"
            if mig17_group in by_group:
                pairs.append((by_group[mig17_group], track))

    return pairs


def object_matches_filter(track: AircraftTrack, filter_str: str) -> bool:
    """Check if track matches the filter substring (case-insensitive).

    Args:
        track: Aircraft track to check
        filter_str: Substring to match against Name, Type, or Group

    Returns:
        True if any field contains the filter substring
    """
    f = filter_str.lower()
    if track.name and f in track.name.lower():
        return True
    if track.aircraft_type and f in track.aircraft_type.lower():
        return True
    if track.group_name and f in track.group_name.lower():
        return True
    return False


def load_envelope_targets(config_path: Optional[Path]) -> dict:
    """Load envelope targets from config file.

    Supports the bfm_mission_tests.json format with nested structure.

    Args:
        config_path: Path to config file

    Returns:
        Dict with envelope threshold values
    """
    # Default envelope values matching bfm_mission_tests.json
    env = {
        "sustained_min_deg_s": 12.0,
        "sustained_max_deg_s": 17.0,
        "instantaneous_min_deg_s": 18.0,
        "instantaneous_max_deg_s": 25.0,
        "corner_speed_kt": 350.0,
        "min_turn_radius_ft": 2200.0,
        "g_warning": 7.0,
        "g_max": 8.0,
    }

    if not config_path or not config_path.exists():
        return env

    try:
        with config_path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        LOGGER.warning("Failed to load envelope JSON (%s), using defaults.", e)
        return env

    # Parse nested structure from bfm_mission_tests.json
    ft = cfg.get("flight_envelope_targets", {})
    pf = cfg.get("pass_fail_criteria", {}).get("turn_rate", {})
    g_cfg = cfg.get("pass_fail_criteria", {}).get("g_loading", {})

    # Turn rate ranges
    env["sustained_min_deg_s"] = pf.get("sustained_min_deg_s", env["sustained_min_deg_s"])
    env["sustained_max_deg_s"] = pf.get("sustained_max_deg_s", env["sustained_max_deg_s"])
    env["instantaneous_min_deg_s"] = pf.get(
        "instantaneous_min_deg_s", env["instantaneous_min_deg_s"]
    )
    env["instantaneous_max_deg_s"] = pf.get(
        "instantaneous_max_deg_s", env["instantaneous_max_deg_s"]
    )

    # Corner speed & radius
    env["corner_speed_kt"] = ft.get("corner_speed_kt", env["corner_speed_kt"])
    env["min_turn_radius_ft"] = ft.get("min_turn_radius_ft", env["min_turn_radius_ft"])

    # G limits
    env["g_max"] = g_cfg.get("max_expected", env["g_max"])
    env["g_warning"] = g_cfg.get("warning_threshold", env["g_warning"])

    return env


def analyze_acmi_file(
    acmi_path: Path,
    bfm_config_path: Optional[Path] = None,
    object_filter: Optional[str] = None,
) -> list[BFMAnalysisResult]:
    """Analyze an ACMI file for BFM test results.

    Supports both paired engagement analysis (MiG-17 vs opponent) and
    single-aircraft analysis when using object_filter.

    Args:
        acmi_path: Path to the ACMI file
        bfm_config_path: Optional path to BFM config for envelope targets
        object_filter: Optional substring to filter which aircraft to analyze
            (matches against Name, Type, or Group). If not provided,
            defaults to matching 'vwv_mig17f'.

    Returns:
        List of BFMAnalysisResult for each analyzed aircraft
    """
    LOGGER.info("Parsing ACMI file: %s", acmi_path)

    # Load envelope targets
    envelope_targets = load_envelope_targets(bfm_config_path)

    # Parse ACMI
    tracks = parse_acmi_file(acmi_path)
    LOGGER.info("Found %d aircraft tracks", len(tracks))

    results = []

    # If object_filter is specified, do single-aircraft analysis
    filter_str = object_filter if object_filter else "vwv_mig17f"

    for track in tracks.values():
        if not track.states or len(track.states) < 5:
            continue

        if not object_matches_filter(track, filter_str):
            continue

        LOGGER.info("Analyzing track: %s (%s)", track.name, track.group_name)

        # For single-aircraft analysis, pass None as opponent
        result = analyze_engagement(track, None, envelope_targets)
        results.append(result)

    # If no results from filter, try engagement pairs as fallback
    if not results:
        LOGGER.info("No matching objects found, trying engagement pairs...")
        pairs = find_engagement_pairs(tracks)
        LOGGER.info("Found %d engagement pairs", len(pairs))

        for mig17_track, opponent_track in pairs:
            if len(mig17_track.states) < 10 or len(opponent_track.states) < 10:
                LOGGER.warning(
                    "Skipping %s - insufficient data points",
                    mig17_track.group_name,
                )
                continue

            result = analyze_engagement(mig17_track, opponent_track, envelope_targets)
            results.append(result)

    return results


def generate_report(results: list[BFMAnalysisResult]) -> str:
    """Generate a human-readable report from analysis results.

    Args:
        results: List of analysis results

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 70)
    lines.append("BFM TEST ANALYSIS REPORT")
    lines.append("=" * 70)
    lines.append("")

    # Group by variant
    by_variant: dict[str, list[BFMAnalysisResult]] = {}
    for r in results:
        key = r.mig17_variant or "BASE"
        by_variant.setdefault(key, []).append(r)

    for variant, variant_results in sorted(by_variant.items()):
        lines.append(f"Variant: {variant}")
        lines.append("-" * 40)

        for r in variant_results:
            lines.append(f"\n  Scenario: {r.scenario_id}")
            lines.append(f"  Opponent: {r.opponent_type}")
            lines.append(f"  Assessment: {r.envelope_assessment}")

            lines.append("  Turn Metrics:")
            lines.append(f"    Max Turn Rate: {r.turn_metrics.max_turn_rate_deg_s:.1f} deg/s")
            lines.append(f"    Avg Turn Rate: {r.turn_metrics.avg_turn_rate_deg_s:.1f} deg/s")
            lines.append(f"    Min Radius: {r.turn_metrics.min_turn_radius_ft:.0f} ft")

            lines.append("  Energy Metrics:")
            lines.append(f"    Initial Speed: {r.energy_metrics.initial_speed_kt:.0f} kt")
            lines.append(f"    Min Speed: {r.energy_metrics.min_speed_kt:.0f} kt")
            lines.append(f"    Max Speed: {r.energy_metrics.max_speed_kt:.0f} kt")
            lines.append(f"    Altitude Variation: {r.energy_metrics.altitude_variation_ft:.0f} ft")

            lines.append("  Maneuvering Metrics:")
            lines.append(f"    Max G: {r.maneuvering_metrics.max_g_loading:.1f}")
            lines.append(f"    Max Bank: {r.maneuvering_metrics.max_bank_deg:.0f} deg")

            lines.append("  Engagement Metrics:")
            lines.append(f"    Duration: {r.engagement_metrics.duration_s:.1f} s")
            lines.append(f"    Initial Range: {r.engagement_metrics.initial_range_ft:.0f} ft")
            lines.append(f"    Min Range: {r.engagement_metrics.min_range_ft:.0f} ft")

            if r.notes:
                lines.append("  Notes:")
                for note in r.notes:
                    lines.append(f"    - {note}")

        lines.append("")

    # Summary
    lines.append("=" * 70)
    lines.append("SUMMARY")
    lines.append("=" * 70)

    total = len(results)
    nominal = sum(1 for r in results if r.envelope_assessment == "NOMINAL")
    under = sum(1 for r in results if r.envelope_assessment == "UNDER")
    over = sum(1 for r in results if r.envelope_assessment == "OVER")

    lines.append(f"Total Scenarios Analyzed: {total}")
    lines.append(f"  NOMINAL (within envelope): {nominal}")
    lines.append(f"  UNDER (below expected): {under}")
    lines.append(f"  OVER (exceeds expected): {over}")

    return "\n".join(lines)


def write_csv(results: list[BFMAnalysisResult], output_path: Path) -> None:
    """Write analysis results to CSV file.

    Args:
        results: List of analysis results
        output_path: Path to output CSV file
    """
    fieldnames = [
        "variant",
        "scenario_id",
        "opponent_type",
        "envelope_assessment",
        "max_turn_rate_deg_s",
        "avg_turn_rate_deg_s",
        "min_turn_radius_ft",
        "initial_speed_kt",
        "min_speed_kt",
        "max_speed_kt",
        "altitude_variation_ft",
        "max_g",
        "max_bank_deg",
        "duration_s",
        "initial_range_ft",
        "min_range_ft",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            writer.writerow({
                "variant": r.mig17_variant,
                "scenario_id": r.scenario_id,
                "opponent_type": r.opponent_type,
                "envelope_assessment": r.envelope_assessment,
                "max_turn_rate_deg_s": f"{r.turn_metrics.max_turn_rate_deg_s:.1f}",
                "avg_turn_rate_deg_s": f"{r.turn_metrics.avg_turn_rate_deg_s:.1f}",
                "min_turn_radius_ft": f"{r.turn_metrics.min_turn_radius_ft:.0f}",
                "initial_speed_kt": f"{r.energy_metrics.initial_speed_kt:.0f}",
                "min_speed_kt": f"{r.energy_metrics.min_speed_kt:.0f}",
                "max_speed_kt": f"{r.energy_metrics.max_speed_kt:.0f}",
                "altitude_variation_ft": f"{r.energy_metrics.altitude_variation_ft:.0f}",
                "max_g": f"{r.maneuvering_metrics.max_g_loading:.1f}",
                "max_bank_deg": f"{r.maneuvering_metrics.max_bank_deg:.0f}",
                "duration_s": f"{r.engagement_metrics.duration_s:.1f}",
                "initial_range_ft": f"{r.engagement_metrics.initial_range_ft:.0f}",
                "min_range_ft": f"{r.engagement_metrics.min_range_ft:.0f}",
            })


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze ACMI files for BFM test metrics"
    )
    parser.add_argument(
        "acmi_path",
        type=Path,
        help="Path to TacView ACMI file",
    )
    parser.add_argument(
        "--object-filter",
        dest="object_filter",
        help=(
            "Substring to select which aircraft to analyze "
            "(matches Name/Type/Group). Default: 'vwv_mig17f'"
        ),
        default=None,
    )
    parser.add_argument(
        "--bfm-config",
        dest="bfm_config",
        type=Path,
        help="Path to BFM test configuration JSON (envelope thresholds)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to write report (prints to stdout if not specified)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Path to write CSV output",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    args = parse_args()

    if not args.acmi_path.exists():
        LOGGER.error("ACMI file not found: %s", args.acmi_path)
        return 1

    results = analyze_acmi_file(args.acmi_path, args.bfm_config, args.object_filter)

    if not results:
        LOGGER.warning("No BFM engagement data found in ACMI file")
        return 2

    report = generate_report(results)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
        LOGGER.info("Report written to: %s", args.output)
    else:
        print(report)

    if args.csv:
        write_csv(results, args.csv)
        LOGGER.info("CSV written to: %s", args.csv)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
