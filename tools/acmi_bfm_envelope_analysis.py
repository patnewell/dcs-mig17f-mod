#!/usr/bin/env python3
"""
acmi_bfm_envelope_analysis.py

Analyze TacView ACMI files for MiG-17F BFM performance and compare
against expected Vietnam-era envelope.

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
# Flight metrics from trajectory
# ---------------------------------------------------------------------

RAD2DEG = 180.0 / math.pi
DEG2RAD = math.pi / 180.0
MPS_TO_KT = 1.94384
M_TO_FT = 3.28084
G0 = 9.80665  # m/s^2


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
      - time_start, time_end, duration_s
      - min_speed_kt, max_speed_kt
      - min_alt_ft, max_alt_ft, alt_span_ft
      - max_inst_tr_deg_s, speed_at_max_tr_kt, alt_at_max_tr_ft, g_at_max_tr
      - best_sustained_tr_deg_s, sustained_window_s, sustained_speed_kt, sustained_g
      - min_turn_radius_ft
      - max_g
      - classification_* fields
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

    # Compute ground-track speed and heading from U/V differences
    for i in range(1, n):
        dt = times[i] - times[i - 1]
        if dt <= 0 or dt > 5.0:
            # Skip pathological dt; copy previous values
            speeds_mps[i] = speeds_mps[i - 1]
            headings_rad[i] = headings_rad[i - 1]
            continue

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
        dt = times[i] - times[i - 1]
        if dt <= 0 or dt > 5.0:
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

    for i in range(n):
        v = speeds_mps[i]
        omega_deg_s = tr_smooth[i]
        omega_rad_s = abs(omega_deg_s) * DEG2RAD

        if v > v_min_turn_mps and omega_rad_s > omega_min_rad_s:
            r_m = v / omega_rad_s
            radius_ft[i] = r_m * M_TO_FT
            g_load[i] = v * omega_rad_s / G0
        else:
            radius_ft[i] = None
            g_load[i] = 0.0

    # Basic ranges
    min_speed_kt = min(speed_kt)
    max_speed_kt = max(speed_kt)
    min_alt_ft = min(alt_ft)
    max_alt_ft = max(alt_ft)
    alt_span_ft = max_alt_ft - min_alt_ft

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

    # Best sustained high-turn segment
    best_sust_tr = 0.0
    best_sust_speed = None
    best_sust_g = None
    best_sust_dur = 0.0

    in_run = False
    run_start = 0

    for i in range(1, n):
        # Condition for being "in a turn"
        if (
            abs(tr_smooth[i]) >= tr_min_for_seq_deg_s
            and speed_kt[i] >= v_min_turn_kt
        ):
            if not in_run:
                in_run = True
                run_start = max(0, i - 1)  # include one prior sample
        else:
            if in_run:
                # Close run at i-1
                run_end = i
                in_run = False

                # Compute duration and average metrics for this run
                sum_dt = 0.0
                sum_tr_dt = 0.0
                sum_speed_dt = 0.0
                sum_g_dt = 0.0

                for j in range(run_start + 1, run_end):
                    dt = times[j] - times[j - 1]
                    if dt <= 0 or dt > 5.0:
                        continue
                    sum_dt += dt
                    sum_tr_dt += abs(tr_smooth[j]) * dt
                    sum_speed_dt += speed_kt[j] * dt
                    sum_g_dt += g_load[j] * dt

                if sum_dt >= min_seq_duration_s and sum_dt > 0:
                    avg_tr = sum_tr_dt / sum_dt
                    avg_speed = sum_speed_dt / sum_dt
                    avg_g = sum_g_dt / sum_dt

                    if avg_tr > best_sust_tr:
                        best_sust_tr = avg_tr
                        best_sust_speed = avg_speed
                        best_sust_g = avg_g
                        best_sust_dur = sum_dt

    # Close run if it extends to the end
    if in_run:
        run_end = n
        sum_dt = 0.0
        sum_tr_dt = 0.0
        sum_speed_dt = 0.0
        sum_g_dt = 0.0

        for j in range(run_start + 1, run_end):
            dt = times[j] - times[j - 1]
            if dt <= 0 or dt > 5.0:
                continue
            sum_dt += dt
            sum_tr_dt += abs(tr_smooth[j]) * dt
            sum_speed_dt += speed_kt[j] * dt
            sum_g_dt += g_load[j] * dt

        if sum_dt >= min_seq_duration_s and sum_dt > 0:
            avg_tr = sum_tr_dt / sum_dt
            avg_speed = sum_speed_dt / sum_dt
            avg_g = sum_g_dt / sum_dt

            if avg_tr > best_sust_tr:
                best_sust_tr = avg_tr
                best_sust_speed = avg_speed
                best_sust_g = avg_g
                best_sust_dur = sum_dt

    # Minimum turn radius during meaningful turns
    valid_radii = [r for r in radius_ft if r is not None]
    min_radius_ft = min(valid_radii) if valid_radii else None

    # Max G
    max_g = max(g_load) if g_load else 0.0

    # Classifications vs envelope
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

    return {
        "time_start": times[0],
        "time_end": times[-1],
        "duration_s": times[-1] - times[0],
        "min_speed_kt": min_speed_kt,
        "max_speed_kt": max_speed_kt,
        "min_alt_ft": min_alt_ft,
        "max_alt_ft": max_alt_ft,
        "alt_span_ft": alt_span_ft,
        "max_inst_tr_deg_s": max_inst_tr,
        "speed_at_max_tr_kt": speed_at_max_tr,
        "alt_at_max_tr_ft": alt_at_max_tr,
        "g_at_max_tr": g_at_max_tr,
        "best_sustained_tr_deg_s": best_sust_tr,
        "sustained_window_s": best_sust_dur,
        "sustained_speed_kt": best_sust_speed,
        "sustained_g": best_sust_g,
        "min_turn_radius_ft": min_radius_ft,
        "max_g": max_g,
        "inst_status": inst_status,
        "sust_status": sust_status,
        "g_status": g_status,
        "radius_status": radius_status,
        "overall_status": overall,
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
) -> List[Dict[str, Any]]:
    """
    Parse ACMI and compute metrics for all objects that match the filter.
    """
    objects = parse_acmi_trajectories(acmi_path)
    results: List[Dict[str, Any]] = []

    for obj_id, data in objects.items():
        meta = data["meta"]
        samples = data["samples"]

        if not samples:
            continue

        if object_filter:
            if not object_matches_filter(meta, object_filter):
                continue
        else:
            # Default: look for your MiG-17 mod types
            if not object_matches_filter(meta, "vwv_mig17f"):
                continue

        metrics = compute_flight_metrics(samples, env)
        if metrics is None:
            continue

        record = {
            "object_id": obj_id,
            "name": meta.get("Name", ""),
            "type": meta.get("Type", ""),
            "group": meta.get("Group", ""),
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
            "Analyze TacView ACMI for MiG-17F BFM performance "
            "and compare against expected envelope."
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
        help="Optional path to write results as CSV",
        default=None,
    )

    args = parser.parse_args()

    if not os.path.isfile(args.acmi_path):
        print(f"[ERROR] ACMI file not found: {args.acmi_path}")
        sys.exit(1)

    env = load_envelope(args.envelope_json)
    obj_filter = args.object_filter

    results = analyze_acmi(args.acmi_path, env, obj_filter)

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
        print(f"  Overall envelope assessment: {rec['overall_status']}")
        print()

    # CSV output
    if args.csv_out:
        fieldnames = [
            "object_id",
            "name",
            "type",
            "group",
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
            "inst_status",
            "sust_status",
            "g_status",
            "radius_status",
            "overall_status",
        ]
        with open(args.csv_out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for rec in results:
                writer.writerow(rec)
        print(f"[INFO] CSV written to: {args.csv_out}")


if __name__ == "__main__":
    main()
