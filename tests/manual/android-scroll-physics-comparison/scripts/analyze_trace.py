#!/usr/bin/env python3
# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT

"""Check input delivery before evaluating scrolling parity."""

import csv
import math
import re
import statistics


def read_trace(path):
    with open(path, newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows or any(None in row for row in rows):
        raise ValueError("Missing or malformed CSV rows")
    for row in rows:
        int(row["time_ns"])
        for key in ("aosp_y_dp", "slint_y_dp", "x_px", "y_px"):
            if row[key] and not math.isfinite(float(row[key])):
                raise ValueError(f"Non-finite {key}")
    return rows


def check_delivery(rows):
    touches = [row for row in rows if row["kind"] == "touch"]
    consumed = [row for row in rows if row["kind"] == "consumed_touch"]
    history = [row for row in rows if row["kind"] == "touch_history"]
    received_history = [row for row in rows if row["kind"] == "consumed_history"]
    if not touches or touches[0]["action"] != "0" or touches[-1]["action"] != "1":
        raise ValueError("Incomplete down/move/up sequence")
    if len(touches) != len(consumed) or len(history) != len(received_history):
        raise ValueError("Lost current or historical samples")
    if any(row["pointer_id"] != "0" for row in touches):
        raise ValueError("This campaign requires one finger")
    coordinate_offsets = []
    for original, received in zip(touches + history, consumed + received_history):
        if original["event_time_ms"] != received["event_time_ms"]:
            raise ValueError("Changed native event timestamp")
        if original["action"] != received["action"]:
            raise ValueError("Changed touch action")
        coordinate_offsets.append((
            float(received["x_px"]) - float(original["x_px"]),
            float(received["y_px"]) - float(original["y_px"]),
        ))
    for axis in range(2):
        values = [offset[axis] for offset in coordinate_offsets]
        if max(values) - min(values) > 1.0:
            raise ValueError("Coordinate translation varies by more than one physical pixel")
    frames = [row for row in rows if row["kind"] == "frame"]
    if len(frames) < 20:
        raise ValueError("Insufficient frame samples")
    initial = frames[0]
    if abs(float(initial["aosp_y_dp"]) - float(initial["slint_y_dp"])) > 1.0:
        raise ValueError("Lists are not initially aligned")
    if not all(any(abs(float(row[key]) - float(initial[key])) > 2 for row in frames)
               for key in ("aosp_y_dp", "slint_y_dp")):
        raise ValueError("Both lists must visibly move")
    return {"touch_samples": len(touches), "historical_samples": len(history),
            "history_exercised": bool(history), "frames": len(frames)}


def evaluate(rows, log_text, density):
    delivery = check_delivery(rows)
    touches = [row for row in rows if row["kind"] == "touch"]
    release_ns = int(touches[-1]["time_ns"])
    frames = sorted((row for row in rows if row["kind"] == "frame"),
                    key=lambda row: int(row["time_ns"]))
    before = [row for row in frames if int(row["time_ns"]) <= release_ns]
    after = [row for row in frames if int(row["time_ns"]) >= release_ns]
    if not before or len(after) < 20:
        raise ValueError("Missing release or tail coverage")
    if (int(after[-1]["time_ns"]) - release_ns) / 1e9 < 2.0:
        raise ValueError("Less than two seconds recorded after release")
    baseline = before[-1]
    travel = {}
    stop = {}
    for key, name in (("aosp_y_dp", "aosp"), ("slint_y_dp", "slint")):
        travel[name] = abs(float(after[-1][key]) - float(baseline[key]))
        changes = [int(right["time_ns"]) for left, right in zip(after, after[1:])
                   if abs(float(right[key]) - float(left[key])) > 0.001]
        stop[name] = (changes[-1] - release_ns) / 1e9 if changes else 0.0
        if any(abs(float(row[key]) - float(after[-1][key])) > 0.01 for row in after[-10:]):
            raise ValueError("Animation did not settle before recording ended")
    flings = [row for row in rows if row["kind"] == "fling"]
    estimates = re.findall(r"SCROLL_ESTIMATE,([-+\d.eE]+),([-+\d.eE]+),([-+\d.eE]+)", log_text)
    if len(flings) != 1 or len(estimates) != 1:
        raise ValueError("Expected exactly one native fling and one Slint release estimate")
    native_velocity = abs(float(flings[0]["aosp_velocity_px_s"])) / density
    slint_velocity = abs(float(estimates[0][1]))
    velocity_error = abs(slint_velocity - native_velocity) / max(native_velocity, 1)
    curve_error = max(abs(
        (float(row["slint_y_dp"]) - float(baseline["slint_y_dp"]))
        - (float(row["aosp_y_dp"]) - float(baseline["aosp_y_dp"]))
    ) for row in after)
    # These tolerances define the desired comparison, not a universal Android specification.
    parity = {
        "release_velocity": velocity_error <= 0.10,
        "post_release_travel": abs(travel["slint"] - travel["aosp"]) <= max(5, travel["aosp"] * 0.10),
        "stop_time": abs(stop["slint"] - stop["aosp"]) <= 0.05,
        "position_curve": curve_error <= max(5, travel["aosp"] * 0.10),
    }
    intervals = [(int(b["time_ns"]) - int(a["time_ns"])) / 1e6
                 for a, b in zip(frames, frames[1:])]
    return {"delivery": delivery, "contact_ms": int(touches[-1]["event_time_ms"]) - int(touches[0]["event_time_ms"]),
            "native_release_dp_s": native_velocity, "slint_release_dp_s": slint_velocity,
            "velocity_relative_error": velocity_error, "post_release_travel_dp": travel,
            "max_post_release_curve_error_dp": curve_error,
            "last_movement_after_release_s": stop, "median_frame_interval_ms": statistics.median(intervals),
            "parity": parity}
