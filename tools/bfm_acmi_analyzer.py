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
    """Calculate instantaneous turn rate at each point.

    Args:
        track: Aircraft track

    Returns:
        List of turn rates (deg/s) for each state
    """
    turn_rates = [0.0]  # First point has no rate

    for i in range(1, len(track.states)):
        curr = track.states[i]
        prev = track.states[i - 1]

        dt = curr.time - prev.time
        if dt <= 0:
            turn_rates.append(turn_rates[-1] if turn_rates else 0.0)
            continue

        # Calculate heading change
        dh = curr.heading_deg - prev.heading_deg
        while dh > 180:
            dh -= 360
        while dh < -180:
            dh += 360

        turn_rates.append(abs(dh) / dt)

    return turn_rates


def calculate_g_loading(track: AircraftTrack) -> list[float]:
    """Estimate G-loading from bank angle and speed.

    G = 1 / cos(bank) for level turn

    Args:
        track: Aircraft track

    Returns:
        List of estimated G values
    """
    g_values = []

    for state in track.states:
        bank_rad = abs(state.roll_deg) * math.pi / 180.0

        # Clamp to prevent divide by zero (max ~85 degrees)
        bank_rad = min(bank_rad, 1.48)

        g = 1.0 / math.cos(bank_rad)
        g_values.append(g)

    return g_values


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


def analyze_engagement(
    mig17_track: AircraftTrack,
    opponent_track: AircraftTrack,
    envelope_targets: dict,
) -> BFMAnalysisResult:
    """Analyze a BFM engagement between MiG-17 and opponent.

    Args:
        mig17_track: Track of the MiG-17
        opponent_track: Track of the opponent aircraft
        envelope_targets: Expected performance envelope values

    Returns:
        BFMAnalysisResult with all metrics
    """
    # Calculate derived values
    calculate_derived_values(mig17_track)
    calculate_derived_values(opponent_track)

    # Get scenario ID from group name
    scenario_id = mig17_track.group_name
    variant = ""
    if "_" in scenario_id and scenario_id.startswith("FM"):
        parts = scenario_id.split("_", 1)
        variant = parts[0]
        scenario_id = parts[1] if len(parts) > 1 else scenario_id

    # Calculate turn metrics
    turn_rates = calculate_instantaneous_turn_rate(mig17_track)
    max_turn_rate = max(turn_rates) if turn_rates else 0.0

    # Calculate average turn rate (exclude first/last 10%)
    trim = len(turn_rates) // 10
    if len(turn_rates) > 20:
        avg_turn_rate = sum(turn_rates[trim:-trim]) / (len(turn_rates) - 2 * trim)
    else:
        avg_turn_rate = sum(turn_rates) / len(turn_rates) if turn_rates else 0.0

    # Calculate minimum turn radius from speed and turn rate
    # R = V / omega (V in m/s, omega in rad/s)
    min_radius_ft = float("inf")
    for i, state in enumerate(mig17_track.states):
        if turn_rates[i] > 0 and state.tas_mps:
            omega_rad_s = turn_rates[i] * math.pi / 180.0
            radius_m = state.tas_mps / omega_rad_s
            radius_ft = radius_m * FT_PER_METER
            min_radius_ft = min(min_radius_ft, radius_ft)

    if min_radius_ft == float("inf"):
        min_radius_ft = 0.0

    turn_metrics = TurnMetrics(
        max_turn_rate_deg_s=max_turn_rate,
        avg_turn_rate_deg_s=avg_turn_rate,
        min_turn_radius_ft=min_radius_ft,
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
    g_values = calculate_g_loading(mig17_track)
    bank_angles = [abs(s.roll_deg) for s in mig17_track.states]
    aoa_values = [s.aoa_deg for s in mig17_track.states if s.aoa_deg is not None]

    maneuvering_metrics = ManeuveringMetrics(
        max_g_loading=max(g_values) if g_values else 0.0,
        avg_g_loading=sum(g_values) / len(g_values) if g_values else 0.0,
        max_aoa_deg=max(aoa_values) if aoa_values else 0.0,
        max_bank_deg=max(bank_angles) if bank_angles else 0.0,
    )

    # Calculate engagement metrics
    duration = 0.0
    if mig17_track.states:
        duration = mig17_track.states[-1].time - mig17_track.states[0].time

    ranges_ft = []
    for i, mig_state in enumerate(mig17_track.states):
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
        time_to_min_range_s=None,  # Would need more logic to calculate
        closure_achieved=min(ranges_ft) < ranges_ft[0] if ranges_ft else False,
    )

    # Assess envelope performance
    notes = []
    envelope_assessment = "NOMINAL"

    # Check turn rate
    target_sustained = envelope_targets.get("max_sustained_turn_rate_deg_s", 14.5)
    target_instant = envelope_targets.get("max_instantaneous_turn_rate_deg_s", 22.0)

    if max_turn_rate > target_instant * 1.15:
        envelope_assessment = "OVER"
        notes.append(f"Turn rate {max_turn_rate:.1f} deg/s exceeds target {target_instant} by >15%")
    elif max_turn_rate < target_instant * 0.85:
        envelope_assessment = "UNDER"
        notes.append(f"Turn rate {max_turn_rate:.1f} deg/s below target {target_instant} by >15%")

    # Check G loading
    target_g = envelope_targets.get("max_g_loading", 8.0)
    if maneuvering_metrics.max_g_loading > target_g * 1.1:
        if envelope_assessment == "NOMINAL":
            envelope_assessment = "OVER"
        notes.append(f"G-loading {maneuvering_metrics.max_g_loading:.1f}G exceeds limit {target_g}G")

    return BFMAnalysisResult(
        scenario_id=scenario_id,
        mig17_group=mig17_track.group_name,
        opponent_group=opponent_track.group_name,
        mig17_variant=variant,
        opponent_type=opponent_track.aircraft_type,
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


def analyze_acmi_file(
    acmi_path: Path,
    bfm_config_path: Optional[Path] = None,
) -> list[BFMAnalysisResult]:
    """Analyze an ACMI file for BFM test results.

    Args:
        acmi_path: Path to the ACMI file
        bfm_config_path: Optional path to BFM config for envelope targets

    Returns:
        List of BFMAnalysisResult for each engagement
    """
    LOGGER.info("Parsing ACMI file: %s", acmi_path)

    # Load envelope targets
    envelope_targets = {}
    if bfm_config_path and bfm_config_path.exists():
        with bfm_config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
            envelope_targets = config.get("flight_envelope_targets", {})

    # Parse ACMI
    tracks = parse_acmi_file(acmi_path)
    LOGGER.info("Found %d aircraft tracks", len(tracks))

    # Find engagement pairs
    pairs = find_engagement_pairs(tracks)
    LOGGER.info("Found %d engagement pairs", len(pairs))

    # Analyze each pair
    results = []
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
        "--bfm-config",
        dest="bfm_config",
        type=Path,
        help="Path to BFM test configuration JSON",
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

    results = analyze_acmi_file(args.acmi_path, args.bfm_config)

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
