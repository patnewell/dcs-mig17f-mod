#!/usr/bin/env python3
"""
acmi_bfm_envelope_analysis.py

Analyze TacView ACMI files for MiG-17F (or other jets) BFM performance and
compare against an expected flight envelope.

Enhancements vs original:
- Time-based metrics (how long above envelope, not just peak).
- Turn-segment breakdown (each sustained turn window).
- Percentile metrics (95th percentile TR/G during turning).
- Simple "UFO severity" classifier with reasons.
- Optional JSON output with full structured data for deeper analysis.

Default envelope thresholds are taken from bfm_mission_tests.json:
- Sustained turn rate: 12–17 deg/s
- Instantaneous turn rate: 18–25 deg/s
- Corner speed: 350 kt
- Max G: 8.0 (warning at 7.0)
- Min turn radius: 2200 ft
"""

import argparse
import csv
import json
import math
import os
import sys
import zipfile
from typing import Dict, Any, List, Optional, Tuple


# ---------------------------------------------------------------------
# Envelope thresholds
# ---------------------------------------------------------------------

def default_envelope() -> Dict[str, float]:
    """
    Default MiG-17F envelope values, matching bfm_mission_tests.json.
    """
    return {
        # Turn rate bounds (deg/s)
        "sustained_min_deg_s": 12.0,
        "sustained_max_deg_s": 17.0,
        "instantaneous_min_deg_s": 18.0,
        "instantaneous_max_deg_s": 25.0,
        # Corner speed (kt)
        "corner_speed_kt": 350.0,
        # Turn radius (ft)
        "min_turn_radius_ft": 2200.0,
        # G limits
        "g_warning": 7.0,
        "g_max": 8.0,
    }


def load_envelope(json_path: Optional[str]) -> Dict[str, float]:
    """
    Load envelope thresholds from a JSON file (bfm_mission_tests.json),
    falling back to built-in defaults if not present.
    """
    env = default_envelope()
    if not json_path:
        return env

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to load envelope JSON ({e}), using defaults.")
        return env

    # Try to pull values from the JSON structure you use
    ft = cfg.get("flight_envelope_targets", {})
    pf = cfg.get("pass_fail_criteria", {}).get("turn_rate", {})
    g_cfg = cfg.get("pass_fail_criteria", {}).get("g_loading", {})

    # Turn rate ranges
    env["sustained_min_deg_s"] = pf.get(
        "sustained_min_deg_s", env["sustained_min_deg_s"]
    )
    env["sustained_max_deg_s"] = pf.get(
        "sustained_max_deg_s", env["sustained_max_deg_s"]
    )
    env["instantaneous_min_deg_s"] = pf.get(
        "instantaneous_min_deg_s", env["instantaneous_min_deg_s"]
    )
    env["instantaneous_max_deg_s"] = pf.get(
        "instantaneous_max_deg_s", env["instantaneous_max_deg_s"]
    )

    # Corner speed & radius
    env["corner_speed_kt"] = ft.get("corner_speed_kt", env["corner_speed_kt"])
    env["min_turn_radius_ft"] = ft.get(
        "min_turn_radius_ft", env["min_turn_radius_ft"]
    )

    # G limits
    env["g_max"] = g_cfg.get("max_expected", env["g_max"])
    env["g_warning"] = g_cfg.get("warning_threshold", env["g_warning"])

    return env


# ---------------------------------------------------------------------
# ACMI parsing
# ---------------------------------------------------------------------

def _iter_acmi_lines(path: str):
    """
    Yield lines from a TacView .acmi file (plain text or zipped .zip.acmi).
    """
    with open(path, "rb") as f:
        head = f.read(4)

    # Check for ZIP magic
    if head.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(path, "r") as z:
            info = z.infolist()[0]
            with z.open(info, "r") as f:
                text = f.read().decode("utf-8", errors="replace")
        for line in text.splitlines():
            yield line
    else:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                yield line.rstrip("\n")


def parse_acmi_trajectories(
    acmi_path: str
) -> Dict[str, Dict[str, Any]]:
    """
    Parse the ACMI into per-object trajectories.

    Returns a dict:
      object_id -> {
        "meta": { "Name": ..., "Type": ..., "Group": ..., ... },
        "samples": [ (time_s, u_m, v_m, alt_m), ... ]
      }

    - u, v: TacView local flat coordinates in meters (X/Y), used for ground track.
    - alt_m: altitude in meters.
    """
    objects: Dict[str, Dict[str, Any]] = {}
    state_by_id: Dict[str, Dict[str, Optional[float]]] = {}
    current_time = 0.0

    for line in _iter_acmi_lines(acmi_path):
        if not line:
            continue
        if line.startswith("\ufeff"):
            line = line.lstrip("\ufeff")
        if line.startswith("//"):
            continue

        # Time marker
        if line.startswith("#"):
            try:
                current_time = float(line[1:])
            except ValueError:
                pass
            continue

        if "," not in line:
            continue

        obj_id, rest = line.split(",", 1)

        # Initialize object entry
        if obj_id not in objects:
            objects[obj_id] = {
                "meta": {},
                "samples": []
            }

        # Parse props: key=value
        props: Dict[str, str] = {}
        for seg in rest.split(","):
            if "=" in seg:
                k, v = seg.split("=", 1)
                props[k] = v

        meta = objects[obj_id]["meta"]

        # Capture some metadata
        for key in ("Name", "Type", "Group", "Pilot", "Country"):
            if key in props:
                meta[key] = props[key]

        if "T" not in props:
            continue

        # Maintain last-known position for this object
        st = state_by_id.get(
            obj_id,
            {"lon": None, "lat": None, "alt": None, "u": None, "v": None}
        )

        parts = props["T"].split("|")

        # Lon | Lat | Alt are first 3 when present
        if len(parts) >= 1 and parts[0] != "":
            try:
                st["lon"] = float(parts[0])
            except ValueError:
                pass
        if len(parts) >= 2 and parts[1] != "":
            try:
                st["lat"] = float(parts[1])
            except ValueError:
                pass
        if len(parts) >= 3 and parts[2] != "":
            try:
                st["alt"] = float(parts[2])
            except ValueError:
                pass

        # U/V interpretation depends on field count (TacView formats):
        #  - T=Lon|Lat|Alt|U|V                (5 fields)
        #  - T=Lon|Lat|Alt|Roll|Pitch|Yaw|U|V|Heading  (>=7 fields)
        if len(parts) == 5:
            if parts[3] != "":
                try:
                    st["u"] = float(parts[3])
                except ValueError:
                    pass
            if parts[4] != "":
                try:
                    st["v"] = float(parts[4])
                except ValueError:
                    pass
        elif len(parts) >= 7:
            if len(parts) >= 7 and parts[6] != "":
                try:
                    st["u"] = float(parts[6])
                except ValueError:
                    pass
            if len(parts) >= 8 and parts[7] != "":
                try:
                    st["v"] = float(parts[7])
                except ValueError:
                    pass

        state_by_id[obj_id] = st

        if st["alt"] is None or st["u"] is None or st["v"] is None:
            continue

        objects[obj_id]["samples"].append(
            (current_time, float(st["u"]), float(st["v"]), float(st["alt"]))
        )

    return objects


# ---------------------------------------------------------------------
# Post-death telemetry truncation
# ---------------------------------------------------------------------
#
# TacView ACMI exports from DCS often do NOT include explicit damage/kill events
# (e.g., Event=Destroyed, Health=0). When an aircraft is shot down, its track can
# continue as it tumbles / falls / impacts, or it can remain as a stationary wreck
# for the rest of the recording. Those "post-death" samples can create wildly
# non-physical turn-rate / radius / g estimates and contaminate envelope analysis.
#
# v3 adds a pragmatic, opt-out truncation pass that tries to keep only "in-flight"
# telemetry. It uses two fallbacks:
#
#   1) WRECK TAIL DETECTION (works when the destroyed aircraft remains in the file):
#      If the last few seconds are near the minimum altitude AND very low speed,
#      we treat that as a wreck-on-ground tail and truncate at its start.
#
#   2) EARLY TRACK END (works when the destroyed aircraft disappears early):
#      If the object stops updating long before the recording ends, we trim a small
#      amount off the end. If it also hit the ground (very low min altitude), we
#      optionally remove the "bottom" portion of the final descent, which is where
#      tumbling/impact artifacts are usually worst.
#
# This is intentionally heuristic: it is designed to remove obvious crash/wreck
# artifacts without discarding the pre-kill maneuvering that we care about.


def default_truncation_config() -> dict:
    """Defaults tuned for BFM test missions (air-start, no landings)."""
    return {
        "enable": True,
        # If an object stops updating this many seconds before the recording ends,
        # consider it "gone" (likely destroyed / removed).
        "death_gap_s": 10.0,

        # Wreck tail detection (stationary / very slow near the object's minimum alt)
        "wreck_alt_band_ft": 75.0,
        "wreck_speed_kt": 40.0,
        "wreck_min_tail_s": 3.0,

        # Ground impact detection
        "impact_alt_ft": 120.0,

        # If we detect a ground impact and the track ends early, we can truncate the
        # last part of the descent. We set the cut altitude to:
        #   min_alt + clamp(descent_cut_frac * alt_span, min, max)
        "descent_cut_frac": 0.50,
        "descent_cut_min_ft": 800.0,
        "descent_cut_max_ft": 5000.0,

        # Always trim at least this many seconds off the end for "early ended" tracks
        # (helps remove last-frame noise / impact spikes).
        "post_death_trim_s": 2.0,
    }


def _basic_kinematics(samples: list) -> tuple:
    """Return (times_s, alt_ft, speed_kt) for heuristic truncation."""
    n = len(samples)
    times = [s[0] for s in samples]
    alt_ft = [s[3] * M_TO_FT for s in samples]

    speed_kt = [0.0] * n
    if n >= 2:
        # Initialize with first valid dt if possible
        for i in range(1, n):
            dt = times[i] - times[i - 1]
            if dt <= 0 or dt > 5:
                continue
            du = samples[i][1] - samples[i - 1][1]
            dv = samples[i][2] - samples[i - 1][2]
            speed_kt[i] = math.hypot(du / dt, dv / dt) * MPS_TO_KT
            speed_kt[0] = speed_kt[i]
            break

        for i in range(1, n):
            dt = times[i] - times[i - 1]
            if dt <= 0 or dt > 5:
                speed_kt[i] = speed_kt[i - 1]
                continue
            du = samples[i][1] - samples[i - 1][1]
            dv = samples[i][2] - samples[i - 1][2]
            speed_kt[i] = math.hypot(du / dt, dv / dt) * MPS_TO_KT

    return times, alt_ft, speed_kt


def infer_post_death_truncation(
    samples: list,
    global_end_time_s: float,
    cfg: dict,
) -> tuple:
    """Return (cut_time_s|None, method|None, reason|None)."""
    if not cfg.get("enable", True):
        return None, None, None

    if len(samples) < 5:
        return None, None, None

    times, alt_ft, speed_kt = _basic_kinematics(samples)
    t0 = times[0]
    t_end = times[-1]

    min_alt = min(alt_ft)
    max_alt = max(alt_ft)
    alt_span = max_alt - min_alt

    # -----------------------------------------------------------------
    # 1) Wreck tail detection (track continues, but aircraft is basically dead)
    # -----------------------------------------------------------------
    # Look for a "tail" at the end where the aircraft is near its minimum altitude
    # AND moving very slowly for at least wreck_min_tail_s.
    band = cfg.get("wreck_alt_band_ft", 75.0)
    v_wreck = cfg.get("wreck_speed_kt", 40.0)
    min_tail = cfg.get("wreck_min_tail_s", 3.0)

    def is_wreck(i: int) -> bool:
        return (alt_ft[i] <= min_alt + band) and (speed_kt[i] <= v_wreck)

    if is_wreck(len(samples) - 1):
        i = len(samples) - 1
        while i > 0 and is_wreck(i):
            i -= 1
        tail_start = i + 1
        tail_dur = t_end - times[tail_start]
        if tail_dur >= min_tail:
            cut_t = max(t0, times[tail_start])
            return (
                cut_t,
                "wreck_tail",
                (
                    f"Detected {tail_dur:.1f}s wreck tail: alt<=min+{band:.0f}ft and "
                    f"speed<={v_wreck:.0f}kt at end (min_alt {min_alt:.0f}ft)."
                ),
            )

    # -----------------------------------------------------------------
    # 2) Early track end (likely destroyed/removed)
    # -----------------------------------------------------------------
    gap = max(0.0, global_end_time_s - t_end)
    if gap <= cfg.get("death_gap_s", 10.0):
        return None, None, None

    trim_s = max(0.0, cfg.get("post_death_trim_s", 2.0))

    # If the aircraft hit the ground (min alt very low), try to remove the bottom
    # portion of the final descent as well.
    impacted = (min_alt <= cfg.get("impact_alt_ft", 120.0)) and (alt_span > 300.0)

    if impacted:
        frac = float(cfg.get("descent_cut_frac", 0.5))
        cut_min = float(cfg.get("descent_cut_min_ft", 800.0))
        cut_max = float(cfg.get("descent_cut_max_ft", 5000.0))

        cut_ft = max(cut_min, min(cut_max, frac * alt_span))
        threshold = min_alt + cut_ft

        # Find last time the aircraft was ABOVE the threshold before the impact.
        idx = None
        for i in range(len(samples) - 1, -1, -1):
            if alt_ft[i] > threshold:
                idx = i
                break

        if idx is not None and idx < len(samples) - 1:
            cut_t = max(t0, times[idx] - trim_s)
            return (
                cut_t,
                "impact_descent_cut",
                (
                    f"Track ended {gap:.1f}s early and hit ground (min_alt {min_alt:.0f}ft). "
                    f"Truncating below ~{threshold:.0f}ft (min_alt + {cut_ft:.0f}ft) and trimming {trim_s:.1f}s."
                ),
            )

    # Fallback: just trim a little off the end
    cut_t = max(t0, t_end - trim_s)
    return (
        cut_t,
        "early_end_trim",
        f"Track ended {gap:.1f}s early; trimming last {trim_s:.1f}s to avoid impact/end-frame artifacts.",
    )


def truncate_samples_at_time(samples: list, cut_time_s: float) -> list:
    if cut_time_s is None:
        return samples
    return [s for s in samples if s[0] <= cut_time_s]


# ---------------------------------------------------------------------
# Flight metrics from trajectory
# ---------------------------------------------------------------------

RAD2DEG = 180.0 / math.pi
DEG2RAD = math.pi / 180.0
MPS_TO_KT = 1.94384
M_TO_FT = 3.28084
G0 = 9.80665  # m/s^2


def compute_percentile(values: List[float], q: float) -> Optional[float]:
    """
    Simple percentile (0–1) without external deps.
    """
    if not values:
        return None
    if q <= 0.0:
        return min(values)
    if q >= 1.0:
        return max(values)
    vs = sorted(values)
    idx = (len(vs) - 1) * q
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return vs[lo]
    frac = idx - lo
    return vs[lo] + (vs[hi] - vs[lo]) * frac


def compute_flight_metrics(
    samples: List[Tuple[float, float, float, float]],
    env: Dict[str, float],
    v_min_turn_kt: float = 150.0,
    tr_min_for_seq_deg_s: float = 8.0,
    min_seq_duration_s: float = 1.5
) -> Optional[Dict[str, Any]]:
    """
    Given a list of (time_s, u_m, v_m, alt_m) samples, compute BFM metrics.

    Returns a dict with:
      - core flight summary metrics (min/max speed, alt, etc.)
      - peak and sustained turn metrics
      - time-based envelope excursion metrics
      - 95th percentile TR/G for turning
      - list of turn segments
      - UFO severity classification
    """
    n = len(samples)
    if n < 5:
        return None

    times = [s[0] for s in samples]
    us = [s[1] for s in samples]
    vs = [s[2] for s in samples]
    alts_m = [s[3] for s in samples]

    # Basic arrays
    speeds_mps = [0.0] * n
    headings_rad = [0.0] * n
    dt_array = [0.0] * n

    # Compute ground-track speed and heading from U/V differences
    for i in range(1, n):
        dt = times[i] - times[i - 1]
        if dt <= 0 or dt > 5.0:
            dt_array[i] = 0.0
            speeds_mps[i] = speeds_mps[i - 1]
            headings_rad[i] = headings_rad[i - 1]
            continue

        dt_array[i] = dt
        du = us[i] - us[i - 1]
        dv = vs[i] - vs[i - 1]
        vx = du / dt
        vy = dv / dt
        speed = math.hypot(vx, vy)
        heading = math.atan2(vy, vx)  # -pi..pi

        speeds_mps[i] = speed
        headings_rad[i] = heading

    # Copy first element forward
    if n >= 2:
        speeds_mps[0] = speeds_mps[1]
        headings_rad[0] = headings_rad[1]

    # Unwrap heading to get a continuous heading curve
    unwrapped = [headings_rad[0]]
    for i in range(1, n):
        prev = headings_rad[i - 1]
        cur = headings_rad[i]
        delta = cur - prev
        # Wrap to [-pi, pi]
        while delta > math.pi:
            delta -= 2 * math.pi
        while delta < -math.pi:
            delta += 2 * math.pi
        unwrapped.append(unwrapped[-1] + delta)

    # Turn rate (deg/s)
    tr_deg_s = [0.0] * n
    for i in range(1, n):
        dt = dt_array[i]
        if dt <= 0.0:
            tr_deg_s[i] = 0.0
            continue
        dpsi = unwrapped[i] - unwrapped[i - 1]  # rad
        tr_deg_s[i] = (dpsi / dt) * RAD2DEG

    # Smooth turn rate (simple 3-point moving average)
    tr_smooth = tr_deg_s[:]
    for i in range(1, n - 1):
        tr_smooth[i] = (
            tr_deg_s[i - 1] + tr_deg_s[i] + tr_deg_s[i + 1]
        ) / 3.0

    speed_kt = [s * MPS_TO_KT for s in speeds_mps]
    alt_ft = [a * M_TO_FT for a in alts_m]

    # Radius and G-load estimate
    v_min_turn_mps = v_min_turn_kt / MPS_TO_KT
    omega_min_rad_s = 1.0 * DEG2RAD  # ignore "turns" below 1 deg/s

    radius_ft: List[Optional[float]] = [None] * n
    g_load = [0.0] * n
    turn_tr_values: List[float] = []
    turn_g_values: List[float] = []

    for i in range(n):
        v = speeds_mps[i]
        omega_deg_s = tr_smooth[i]
        omega_rad_s = abs(omega_deg_s) * DEG2RAD

        if v > v_min_turn_mps and omega_rad_s > omega_min_rad_s:
            r_m = v / omega_rad_s
            r_ft = r_m * M_TO_FT
            radius_ft[i] = r_ft
            g_val = v * omega_rad_s / G0
            g_load[i] = g_val
            # Only count TR/G values during meaningful turning
            turn_tr_values.append(abs(omega_deg_s))
            turn_g_values.append(g_val)
        else:
            radius_ft[i] = None
            g_load[i] = 0.0

    # Basic ranges
    min_speed_kt = min(speed_kt)
    max_speed_kt = max(speed_kt)
    min_alt_ft = min(alt_ft)
    max_alt_ft = max(alt_ft)
    alt_span_ft = max_alt_ft - min_alt_ft
    duration_s = times[-1] - times[0]

    # Max instantaneous turn rate
    max_inst_tr = 0.0
    idx_max_tr = 0
    for i in range(n):
        if speed_kt[i] < v_min_turn_kt:
            continue
        val = abs(tr_smooth[i])
        if val > max_inst_tr:
            max_inst_tr = val
            idx_max_tr = i

    speed_at_max_tr = speed_kt[idx_max_tr]
    alt_at_max_tr = alt_ft[idx_max_tr]
    g_at_max_tr = g_load[idx_max_tr]

    # Detect sustained turn segments (runs where TR and speed exceed thresholds)
    best_sust_tr = 0.0
    best_sust_speed = None
    best_sust_g = None
    best_sust_dur = 0.0

    turn_segments: List[Dict[str, Any]] = []
    total_turn_time = 0.0

    in_run = False
    run_start = 0

    def finalize_run(start_idx: int, end_idx: int):
        nonlocal best_sust_tr, best_sust_speed, best_sust_g, best_sust_dur
        nonlocal total_turn_time, turn_segments

        if end_idx <= start_idx + 1:
            return

        sum_dt = 0.0
        sum_tr_dt = 0.0
        sum_speed_dt = 0.0
        sum_g_dt = 0.0
        min_speed = float("inf")
        max_speed = 0.0
        max_tr_seg = 0.0
        min_radius = float("inf")
        max_g_seg = 0.0

        for j in range(start_idx + 1, end_idx):
            dt = dt_array[j]
            if dt <= 0.0:
                continue
            sum_dt += dt
            tr_val = abs(tr_smooth[j])
            spd = speed_kt[j]
            g_val = g_load[j]
            r_val = radius_ft[j]

            sum_tr_dt += tr_val * dt
            sum_speed_dt += spd * dt
            sum_g_dt += g_val * dt

            if spd < min_speed:
                min_speed = spd
            if spd > max_speed:
                max_speed = spd
            if tr_val > max_tr_seg:
                max_tr_seg = tr_val
            if g_val > max_g_seg:
                max_g_seg = g_val
            if r_val is not None and r_val < min_radius:
                min_radius = r_val

        if sum_dt < min_seq_duration_s or sum_dt <= 0.0:
            return

        avg_tr = sum_tr_dt / sum_dt
        avg_speed = sum_speed_dt / sum_dt if sum_speed_dt > 0 else None
        avg_g = sum_g_dt / sum_dt if sum_g_dt > 0 else None

        seg_start_t = times[start_idx]
        seg_end_t = times[end_idx - 1]

        # Classify the segment against the envelope
        inst_status_seg = classify_range(
            max_tr_seg,
            env["instantaneous_min_deg_s"],
            env["instantaneous_max_deg_s"],
        )
        sust_status_seg = classify_range(
            avg_tr,
            env["sustained_min_deg_s"],
            env["sustained_max_deg_s"],
        )
        g_status_seg = classify_g(max_g_seg, env["g_warning"], env["g_max"])
        radius_status_seg = classify_radius(min_radius if min_radius != float("inf") else None,
                                            env["min_turn_radius_ft"])
        overall_seg = overall_status(
            inst_status_seg, sust_status_seg, g_status_seg, radius_status_seg
        )

        turn_segments.append(
            {
                "time_start": seg_start_t,
                "time_end": seg_end_t,
                "duration_s": sum_dt,
                "avg_tr_deg_s": avg_tr,
                "max_tr_deg_s": max_tr_seg,
                "avg_speed_kt": avg_speed,
                "min_speed_kt": None if min_speed == float("inf") else min_speed,
                "max_speed_kt": max_speed,
                "avg_g": avg_g,
                "max_g": max_g_seg,
                "min_turn_radius_ft": None if min_radius == float("inf") else min_radius,
                "inst_status": inst_status_seg,
                "sust_status": sust_status_seg,
                "g_status": g_status_seg,
                "radius_status": radius_status_seg,
                "overall_status": overall_seg,
            }
        )

        total_turn_time += sum_dt

        # Track best sustained turn (by average TR)
        if avg_tr > best_sust_tr:
            best_sust_tr = avg_tr
            best_sust_speed = avg_speed
            best_sust_g = avg_g
            best_sust_dur = sum_dt

    # Scan for runs
    for i in range(1, n):
        turning_now = (
            abs(tr_smooth[i]) >= tr_min_for_seq_deg_s
            and speed_kt[i] >= v_min_turn_kt
        )
        if turning_now and not in_run:
            in_run = True
            run_start = max(0, i - 1)
        elif not turning_now and in_run:
            in_run = False
            run_end = i
            finalize_run(run_start, run_end)

    # Close run if it extends to the end
    if in_run:
        finalize_run(run_start, n)

    # Minimum turn radius during meaningful turns
    valid_radii = [r for r in radius_ft if r is not None]
    min_radius_ft = min(valid_radii) if valid_radii else None

    # Max G
    max_g = max(g_load) if g_load else 0.0

    # Classifications vs envelope (overall flight)
    inst_status = classify_range(
        max_inst_tr,
        env["instantaneous_min_deg_s"],
        env["instantaneous_max_deg_s"],
    )
    sust_status = classify_range(
        best_sust_tr,
        env["sustained_min_deg_s"],
        env["sustained_max_deg_s"],
    )
    g_status = classify_g(max_g, env["g_warning"], env["g_max"])
    radius_status = classify_radius(min_radius_ft, env["min_turn_radius_ft"])

    overall = overall_status(inst_status, sust_status, g_status, radius_status)

    # Percentiles of TR and G during turning
    tr_p95 = compute_percentile(turn_tr_values, 0.95)
    g_p95 = compute_percentile(turn_g_values, 0.95)

    # Time-based envelope excursions
    inst_max = env["instantaneous_max_deg_s"]
    g_max = env["g_max"]
    tight_radius_thr = env["min_turn_radius_ft"] * 0.8

    time_over_inst = 0.0
    time_over_gmax = 0.0
    time_radius_tight = 0.0

    max_run_over_inst = 0.0
    max_run_over_gmax = 0.0
    max_run_radius_tight = 0.0

    cur_run_inst = 0.0
    cur_run_g = 0.0
    cur_run_rad = 0.0

    for i in range(1, n):
        dt = dt_array[i]
        if dt <= 0.0:
            continue

        # > instantaneous max TR
        cond_inst = (
            abs(tr_smooth[i]) > inst_max
            and speed_kt[i] >= v_min_turn_kt
        )
        if cond_inst:
            time_over_inst += dt
            cur_run_inst += dt
        else:
            if cur_run_inst > max_run_over_inst:
                max_run_over_inst = cur_run_inst
            cur_run_inst = 0.0

        # > G max
        cond_g = g_load[i] > g_max
        if cond_g:
            time_over_gmax += dt
            cur_run_g += dt
        else:
            if cur_run_g > max_run_over_gmax:
                max_run_over_gmax = cur_run_g
            cur_run_g = 0.0

        # radius below tight threshold
        r_val = radius_ft[i]
        cond_rad = r_val is not None and r_val < tight_radius_thr
        if cond_rad:
            time_radius_tight += dt
            cur_run_rad += dt
        else:
            if cur_run_rad > max_run_radius_tight:
                max_run_radius_tight = cur_run_rad
            cur_run_rad = 0.0

    # finalize current runs
    if cur_run_inst > max_run_over_inst:
        max_run_over_inst = cur_run_inst
    if cur_run_g > max_run_over_gmax:
        max_run_over_gmax = cur_run_g
    if cur_run_rad > max_run_radius_tight:
        max_run_radius_tight = cur_run_rad

    # Fractions
    turn_time_s = total_turn_time
    turn_time_frac = (turn_time_s / duration_s) if duration_s > 0 else 0.0

    def frac_of_turn(t: float) -> float:
        return (t / turn_time_s) if turn_time_s > 0 else 0.0

    time_over_inst_frac_turn = frac_of_turn(time_over_inst)
    time_over_gmax_frac_turn = frac_of_turn(time_over_gmax)
    time_radius_tight_frac_turn = frac_of_turn(time_radius_tight)

    # UFO severity classification
    ufo_severity, ufo_reasons = classify_ufo(
        max_inst_tr=max_inst_tr,
        best_sust_tr=best_sust_tr,
        min_radius_ft=min_radius_ft,
        max_g=max_g,
        tr_p95=tr_p95,
        g_p95=g_p95,
        time_over_inst_frac_turn=time_over_inst_frac_turn,
        time_over_gmax_frac_turn=time_over_gmax_frac_turn,
        time_radius_tight_frac_turn=time_radius_tight_frac_turn,
        env=env,
    )

    return {
        # Flight bounds
        "time_start": times[0],
        "time_end": times[-1],
        "duration_s": duration_s,
        "min_speed_kt": min_speed_kt,
        "max_speed_kt": max_speed_kt,
        "min_alt_ft": min_alt_ft,
        "max_alt_ft": max_alt_ft,
        "alt_span_ft": alt_span_ft,
        # Peak turn metrics
        "max_inst_tr_deg_s": max_inst_tr,
        "speed_at_max_tr_kt": speed_at_max_tr,
        "alt_at_max_tr_ft": alt_at_max_tr,
        "g_at_max_tr": g_at_max_tr,
        # Best sustained segment (flight-level summary)
        "best_sustained_tr_deg_s": best_sust_tr,
        "sustained_window_s": best_sust_dur,
        "sustained_speed_kt": best_sust_speed,
        "sustained_g": best_sust_g,
        # Global turn geometry
        "min_turn_radius_ft": min_radius_ft,
        "max_g": max_g,
        # Percentiles during turning
        "tr_p95_deg_s": tr_p95,
        "g_p95": g_p95,
        # Time breakdown
        "turn_time_s": turn_time_s,
        "turn_time_frac": turn_time_frac,
        "time_over_inst_s": time_over_inst,
        "time_over_inst_frac_turn": time_over_inst_frac_turn,
        "max_run_over_inst_s": max_run_over_inst,
        "time_over_gmax_s": time_over_gmax,
        "time_over_gmax_frac_turn": time_over_gmax_frac_turn,
        "max_run_over_gmax_s": max_run_over_gmax,
        "time_radius_tight_s": time_radius_tight,
        "time_radius_tight_frac_turn": time_radius_tight_frac_turn,
        "max_run_radius_tight_s": max_run_radius_tight,
        "n_turn_segments": len(turn_segments),
        # Classifications (flight-level)
        "inst_status": inst_status,
        "sust_status": sust_status,
        "g_status": g_status,
        "radius_status": radius_status,
        "overall_status": overall,
        # UFO classification
        "ufo_severity": ufo_severity,
        "ufo_reasons": ufo_reasons,
        # Detailed segments for JSON output
        "turn_segments": turn_segments,
    }


def classify_range(value: Optional[float], vmin: float, vmax: float) -> str:
    if value is None:
        return "N/A"
    if value < vmin:
        return "UNDER"
    if value > vmax:
        return "OVER"
    return "WITHIN"


def classify_g(g: float, warn: float, gmax: float) -> str:
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
    """
    Classify turn radius roughly vs target minimum radius.
    """
    if radius_ft is None:
        return "N/A"
    if radius_ft < target_min_ft * tight_factor:
        return "TIGHT_OVER"  # suspiciously tight radius
    if radius_ft > target_min_ft * loose_factor:
        return "LOOSE_UNDER"  # not using full capability
    return "WITHIN"


def overall_status(
    inst_status: str, sust_status: str, g_status: str, radius_status: str
) -> str:
    """
    Crude combined status.
    """
    if g_status == "OVER" or inst_status == "OVER" or radius_status == "TIGHT_OVER":
        return "OVER_ENVELOPE"
    if inst_status == "UNDER" and sust_status == "UNDER":
        return "UNDER_ENVELOPE"
    return "WITHIN_OR_MIXED"


def classify_ufo(
    *,
    max_inst_tr: float,
    best_sust_tr: float,
    min_radius_ft: Optional[float],
    max_g: float,
    tr_p95: Optional[float],
    g_p95: Optional[float],
    time_over_inst_frac_turn: float,
    time_over_gmax_frac_turn: float,
    time_radius_tight_frac_turn: float,
    env: Dict[str, float],
) -> Tuple[str, List[str]]:
    """
    Heuristic "UFO severity" classifier for quick FM triage.
    Returns (severity, reasons[]).

    Severity:
      - "OK"
      - "MODERATE_UFO"
      - "HIGH_UFO"
    """
    reasons: List[str] = []
    severe = False
    moderate = False

    inst_max = env["instantaneous_max_deg_s"]
    sust_max = env["sustained_max_deg_s"]
    g_max = env["g_max"]
    radius_min = env["min_turn_radius_ft"]

    # Peaks
    if max_inst_tr > inst_max + 8.0:
        severe = True
        reasons.append("max_inst_tr >> envelope")
    elif max_inst_tr > inst_max + 3.0:
        moderate = True
        reasons.append("max_inst_tr > envelope")

    if best_sust_tr > sust_max + 5.0:
        severe = True
        reasons.append("sustained_tr >> envelope")
    elif best_sust_tr > sust_max + 2.0:
        moderate = True
        reasons.append("sustained_tr > envelope")

    if min_radius_ft is not None:
        if min_radius_ft < radius_min * 0.6:
            severe = True
            reasons.append("turn_radius << envelope")
        elif min_radius_ft < radius_min * 0.8:
            moderate = True
            reasons.append("turn_radius < envelope")

    if max_g > g_max + 2.0:
        severe = True
        reasons.append("max_g >> structural_limit")
    elif max_g > g_max + 0.5:
        moderate = True
        reasons.append("max_g > structural_limit")

    # Percentiles
    if tr_p95 is not None and tr_p95 > inst_max + 4.0:
        severe = True
        reasons.append("p95_turn_rate >> envelope")
    elif tr_p95 is not None and tr_p95 > inst_max + 1.5:
        moderate = True
        reasons.append("p95_turn_rate > envelope")

    if g_p95 is not None and g_p95 > g_max + 1.5:
        severe = True
        reasons.append("p95_g >> structural_limit")
    elif g_p95 is not None and g_p95 > g_max + 0.5:
        moderate = True
        reasons.append("p95_g > structural_limit")

    # Time fractions
    if time_over_inst_frac_turn > 0.3:
        severe = True
        reasons.append(">30% of turning above inst_max")
    elif time_over_inst_frac_turn > 0.1:
        moderate = True
        reasons.append(">10% of turning above inst_max")

    if time_over_gmax_frac_turn > 0.15:
        severe = True
        reasons.append(">15% of turning above g_max")
    elif time_over_gmax_frac_turn > 0.05:
        moderate = True
        reasons.append(">5% of turning above g_max")

    if time_radius_tight_frac_turn > 0.2:
        severe = True
        reasons.append(">20% of turning below tight_radius")
    elif time_radius_tight_frac_turn > 0.05:
        moderate = True
        reasons.append(">5% of turning below tight_radius")

    if severe:
        return "HIGH_UFO", reasons
    if moderate:
        return "MODERATE_UFO", reasons
    return "OK", reasons


# ---------------------------------------------------------------------
# Object filtering & analysis driver
# ---------------------------------------------------------------------

def object_matches_filter(meta: Dict[str, Any], filter_str: str) -> bool:
    """
    Returns True if any of the metadata fields contains the filter substring
    (case-insensitive).
    """
    f = filter_str.lower()
    for key in ("Name", "Type", "Group", "Pilot"):
        val = meta.get(key)
        if val and f in str(val).lower():
            return True
    return False


def analyze_acmi(
    acmi_path: str,
    env: Dict[str, float],
    object_filter: Optional[str] = None,
    truncation_cfg: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Parse ACMI and compute metrics for all objects that match the filter.

    v3: optionally truncates each object's samples to remove likely post-death
        telemetry (wreck/crash artifacts).
    """
    objects = parse_acmi_trajectories(acmi_path)

    # Global end time (used to detect early-ending tracks)
    global_end_time = 0.0
    for _oid, _data in objects.items():
        s = _data.get("samples") or []
        if s:
            global_end_time = max(global_end_time, s[-1][0])

    cfg = default_truncation_config()
    if truncation_cfg:
        cfg.update({k: v for k, v in truncation_cfg.items() if v is not None})

    results: List[Dict[str, Any]] = []

    for obj_id, data in objects.items():
        meta = data.get("meta", {})
        samples = data.get("samples", [])

        if not samples:
            continue

        if object_filter:
            if not object_matches_filter(meta, object_filter):
                continue
        else:
            # Default: look for MiG-17 mod types if no explicit filter provided
            if not object_matches_filter(meta, "vwv_mig17f"):
                continue

        cut_t, cut_method, cut_reason = infer_post_death_truncation(samples, global_end_time, cfg)
        used_samples = samples
        truncated = False
        if cut_t is not None:
            used_samples = truncate_samples_at_time(samples, cut_t)
            truncated = len(used_samples) < len(samples)

        metrics = compute_flight_metrics(used_samples, env)
        if metrics is None:
            continue

        record = {
            "object_id": obj_id,
            "name": meta.get("Name", ""),
            "type": meta.get("Type", ""),
            "group": meta.get("Group", ""),
            # Truncation metadata
            "samples_raw": len(samples),
            "samples_used": len(used_samples),
            "post_death_truncated": bool(truncated),
            "post_death_cut_time_s": cut_t,
            "post_death_method": cut_method,
            "post_death_reason": cut_reason,
        }
        record.update(metrics)
        results.append(record)

    return results


# ---------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Analyze TacView ACMI for BFM performance and compare against an "
            "expected envelope (MiG-17F by default)."
        )
    )
    parser.add_argument("acmi_path", help="Path to TacView .acmi or .zip.acmi file")
    parser.add_argument(
        "--object-filter",
        help=(
            "Substring to select the aircraft to analyze "
            "(matches Name/Type/Group). Default: 'vwv_mig17f'"
        ),
        default=None,
    )
    parser.add_argument(
        "--envelope-json",
        help="Path to bfm_mission_tests.json (optional; overrides defaults)",
        default=None,
    )
    parser.add_argument(
        "--csv-out",
        help="Optional path to write summary results as CSV",
        default=None,
    )
    parser.add_argument(
        "--json-out",
        help="Optional path to write detailed results (including segments) as JSON",
        default=None,
    )

    # v3: Post-death truncation controls
    parser.add_argument(
        "--no-truncate-after-death",
        action="store_true",
        help=(
            "Disable heuristic truncation of post-death telemetry (wreck/crash artifacts). "
            "By default this is ON, because DCS TacView exports often lack explicit kill events."
        ),
    )
    parser.add_argument(
        "--death-gap-s",
        type=float,
        default=default_truncation_config()["death_gap_s"],
        help="If an object track ends this many seconds before recording end, treat it as destroyed/removed (default: %(default)s).",
    )
    parser.add_argument(
        "--wreck-speed-kt",
        type=float,
        default=default_truncation_config()["wreck_speed_kt"],
        help="Wreck tail speed threshold in knots (default: %(default)s).",
    )
    parser.add_argument(
        "--wreck-alt-band-ft",
        type=float,
        default=default_truncation_config()["wreck_alt_band_ft"],
        help="Wreck tail altitude band above min altitude in feet (default: %(default)s).",
    )
    parser.add_argument(
        "--wreck-min-tail-s",
        type=float,
        default=default_truncation_config()["wreck_min_tail_s"],
        help="Minimum duration for wreck tail detection in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--impact-alt-ft",
        type=float,
        default=default_truncation_config()["impact_alt_ft"],
        help="Treat min altitude <= this as a ground impact (default: %(default)s).",
    )
    parser.add_argument(
        "--descent-cut-frac",
        type=float,
        default=default_truncation_config()["descent_cut_frac"],
        help="Fraction of altitude span to remove from the bottom of a final descent (default: %(default)s).",
    )
    parser.add_argument(
        "--descent-cut-min-ft",
        type=float,
        default=default_truncation_config()["descent_cut_min_ft"],
        help="Minimum feet to cut from bottom of final descent (default: %(default)s).",
    )
    parser.add_argument(
        "--descent-cut-max-ft",
        type=float,
        default=default_truncation_config()["descent_cut_max_ft"],
        help="Maximum feet to cut from bottom of final descent (default: %(default)s).",
    )
    parser.add_argument(
        "--post-death-trim-s",
        type=float,
        default=default_truncation_config()["post_death_trim_s"],
        help="Always trim this many seconds from the end of early-ending tracks (default: %(default)s).",
    )


    args = parser.parse_args()

    if not os.path.isfile(args.acmi_path):
        print(f"[ERROR] ACMI file not found: {args.acmi_path}")
        sys.exit(1)

    env = load_envelope(args.envelope_json)
    obj_filter = args.object_filter

    trunc_cfg = {
        'enable': (not args.no_truncate_after_death),
        'death_gap_s': args.death_gap_s,
        'wreck_speed_kt': args.wreck_speed_kt,
        'wreck_alt_band_ft': args.wreck_alt_band_ft,
        'wreck_min_tail_s': args.wreck_min_tail_s,
        'impact_alt_ft': args.impact_alt_ft,
        'descent_cut_frac': args.descent_cut_frac,
        'descent_cut_min_ft': args.descent_cut_min_ft,
        'descent_cut_max_ft': args.descent_cut_max_ft,
        'post_death_trim_s': args.post_death_trim_s,
    }
    results = analyze_acmi(args.acmi_path, env, obj_filter, trunc_cfg)

    if not results:
        print("[INFO] No matching objects or no usable data found.")
        sys.exit(0)

    print(f"[INFO] Analyzed {len(results)} object(s).")
    print("Envelope thresholds:")
    print(
        f"  Sustained TR: {env['sustained_min_deg_s']:.1f}–{env['sustained_max_deg_s']:.1f} deg/s"
    )
    print(
        f"  Instantaneous TR: {env['instantaneous_min_deg_s']:.1f}–{env['instantaneous_max_deg_s']:.1f} deg/s"
    )
    print(f"  Corner speed: {env['corner_speed_kt']:.0f} kt")
    print(f"  Min turn radius: {env['min_turn_radius_ft']:.0f} ft")
    print(f"  Max G: {env['g_max']:.1f} (warning at {env['g_warning']:.1f})")
    print()

    # Text summary
    for rec in results:
        print("=" * 72)
        print(
            f"Object {rec['object_id']}: "
            f"name='{rec['name']}', type='{rec['type']}', group='{rec['group']}'"
        )
        print(
            f"  Time: {rec['time_start']:.1f}–{rec['time_end']:.1f} s "
            f"(duration {rec['duration_s']:.1f} s)"
        )
        print(
            f"  Speed: {rec['min_speed_kt']:.1f}–{rec['max_speed_kt']:.1f} kt, "
            f"Alt: {rec['min_alt_ft']:.0f}–{rec['max_alt_ft']:.0f} ft "
            f"(Δ {rec['alt_span_ft']:.0f} ft)"
        )
        if rec.get('post_death_truncated'):
            ct = rec.get('post_death_cut_time_s')
            print(f"  Post-death truncation: cut at {ct:.1f}s ({rec.get('post_death_method')})")
            if rec.get('post_death_reason'):
                print(f"    Reason: {rec.get('post_death_reason')}")
            print(f"    Samples: {rec.get('samples_used')}/{rec.get('samples_raw')} used")

        print(
            f"  Max inst TR: {rec['max_inst_tr_deg_s']:.2f} deg/s "
            f"@ {rec['speed_at_max_tr_kt']:.1f} kt, "
            f"{rec['alt_at_max_tr_ft']:.0f} ft, "
            f"{rec['g_at_max_tr']:.2f} g "
            f"[{rec['inst_status']}]"
        )
        if rec["best_sustained_tr_deg_s"] > 0:
            print(
                f"  Best sustained TR: {rec['best_sustained_tr_deg_s']:.2f} deg/s "
                f"over {rec['sustained_window_s']:.2f} s "
                f"@ ~{(rec['sustained_speed_kt'] or 0):.1f} kt, "
                f"~{(rec['sustained_g'] or 0):.2f} g "
                f"[{rec['sust_status']}]"
            )
        else:
            print("  Best sustained TR: N/A [no qualifying turn segments]")

        if rec["min_turn_radius_ft"] is not None:
            print(
                f"  Min turn radius: {rec['min_turn_radius_ft']:.0f} ft "
                f"[{rec['radius_status']}]"
            )
        else:
            print("  Min turn radius: N/A")

        print(
            f"  Max G: {rec['max_g']:.2f} g "
            f"[{rec['g_status']}]"
        )
        print(
            f"  TR p95 (turning): "
            f"{(rec['tr_p95_deg_s'] or 0):.2f} deg/s, "
            f"G p95 (turning): {(rec['g_p95'] or 0):.2f} g"
        )
        print(
            f"  Turning time: {rec['turn_time_s']:.1f} s "
            f"({rec['turn_time_frac']*100:.1f}% of flight)"
        )
        print(
            f"  Time > inst_max: {rec['time_over_inst_s']:.2f} s "
            f"({rec['time_over_inst_frac_turn']*100:.1f}% of turning), "
            f"max continuous: {rec['max_run_over_inst_s']:.2f} s"
        )
        print(
            f"  Time > g_max: {rec['time_over_gmax_s']:.2f} s "
            f"({rec['time_over_gmax_frac_turn']*100:.1f}% of turning), "
            f"max continuous: {rec['max_run_over_gmax_s']:.2f} s"
        )
        print(
            f"  Time radius < 0.8*min: {rec['time_radius_tight_s']:.2f} s "
            f"({rec['time_radius_tight_frac_turn']*100:.1f}% of turning), "
            f"max continuous: {rec['max_run_radius_tight_s']:.2f} s"
        )
        print(
            f"  Turn segments: {rec['n_turn_segments']} "
            f"(see JSON output for full details)"
        )
        print(
            f"  UFO severity: {rec['ufo_severity']} "
            f"reasons={'; '.join(rec['ufo_reasons']) if rec['ufo_reasons'] else '[]'}"
        )
        print(f"  Overall envelope assessment: {rec['overall_status']}")
        print()

    # CSV output (summary only; no turn_segments list)
    if args.csv_out:
        fieldnames = [
            "object_id",
            "name",
            "type",
            "group",
            "samples_raw",
            "samples_used",
            "post_death_truncated",
            "post_death_cut_time_s",
            "post_death_method",
            "post_death_reason",
            "time_start",
            "time_end",
            "duration_s",
            "min_speed_kt",
            "max_speed_kt",
            "min_alt_ft",
            "max_alt_ft",
            "alt_span_ft",
            "max_inst_tr_deg_s",
            "speed_at_max_tr_kt",
            "alt_at_max_tr_ft",
            "g_at_max_tr",
            "best_sustained_tr_deg_s",
            "sustained_window_s",
            "sustained_speed_kt",
            "sustained_g",
            "min_turn_radius_ft",
            "max_g",
            "tr_p95_deg_s",
            "g_p95",
            "turn_time_s",
            "turn_time_frac",
            "time_over_inst_s",
            "time_over_inst_frac_turn",
            "max_run_over_inst_s",
            "time_over_gmax_s",
            "time_over_gmax_frac_turn",
            "max_run_over_gmax_s",
            "time_radius_tight_s",
            "time_radius_tight_frac_turn",
            "max_run_radius_tight_s",
            "n_turn_segments",
            "inst_status",
            "sust_status",
            "g_status",
            "radius_status",
            "overall_status",
            "ufo_severity",
            "ufo_reasons",
        ]
        with open(args.csv_out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for rec in results:
                # Flatten ufo_reasons for CSV
                row = rec.copy()
                row["ufo_reasons"] = ";".join(rec.get("ufo_reasons", []))
                # Remove turn_segments (not representable in a flat CSV row)
                row.pop("turn_segments", None)
                writer.writerow(row)
        print(f"[INFO] CSV written to: {args.csv_out}")

    # JSON output (full structure including segments)
    if args.json_out:
        payload = {
            "acmi_path": args.acmi_path,
            "object_filter": obj_filter or "vwv_mig17f (default)",
            "envelope": env,
            "results": results,
        }
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"[INFO] JSON written to: {args.json_out}")


if __name__ == "__main__":
    main()
