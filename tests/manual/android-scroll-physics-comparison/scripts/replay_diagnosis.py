#!/usr/bin/env python3
# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT

"""Replay free vertical flings from recorded samples and measured launch estimates."""

import argparse
import csv
import gzip
import json
import math
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("recording", type=Path)
parser.add_argument("--output", type=Path)
parser.add_argument(
    "--verify", action="store_true", help="Check the retained campaign's replay bounds"
)
args = parser.parse_args()
root = args.recording
saved = json.loads((root / "results.json").read_text())
results = saved["results"]
density = saved["density"]


def read_rows(folder):
    path = folder / "trace.csv"
    if path.exists():
        with path.open(newline="") as source:
            return list(csv.DictReader(source))
    with gzip.open(folder / "trace.csv.gz", "rt", newline="") as source:
        return list(csv.DictReader(source))


def params(v):
    rate = math.log(0.78) / math.log(0.9)
    coef = 9.80665 * 39.37 * 160 * 0.84
    friction = 0.015

    l = math.log(0.35 * v / (friction * coef))
    return {
        "distance_dp": math.trunc(friction * coef * math.exp(rate / (rate - 1) * l)),
        "duration_ms": math.trunc(1000 * math.exp(l / (rate - 1))),
    }


report = []
for result in results:
    rows = read_rows(root / f"{result['case']}-{result['trial']}")
    points = [
        (int(r["event_time_ms"]), float(r["y_px"]))
        for r in rows
        if r["kind"] in ("touch", "touch_history") and r["action"] in ("0", "2")
    ]
    points = points[-20:]
    selected = []
    for point in reversed(points):
        if selected and (
            selected[-1][0] - point[0] > 40 or selected[0][0] - point[0] > 100
        ):
            break
        if selected and selected[-1][0] == point[0]:
            continue
        selected.append(point)
    t = np.array([(p[0] - selected[0][0]) for p in selected], float)
    weight = np.power(0.5, -t / (-t[-1] / 14))
    estimates = {}
    for quantized in (False, True):
        y = (
            np.array([math.trunc(p[1]) if quantized else p[1] for p in selected], float)
            / density
        )
        y -= y[0]
        for weighted in (False, True):
            fit = np.polynomial.polynomial.polyfit(
                t, y, min(2, len(t) - 1), w=np.sqrt(weight) if weighted else None
            )
            estimates[
                f"{'int' if quantized else 'float'}_{'weighted' if weighted else 'uniform'}"
            ] = -fit[1] * 1000
    samples = [r for r in rows if r["kind"] == "slint_sample"]
    released = next(
        r for r in rows if r["kind"] == "consumed_touch" and r["action"] == "1"
    )
    baseline = [r for r in samples if int(r["time_ns"]) < int(released["time_ns"])][-1]
    frames = [r for r in rows if r["kind"] == "frame"]
    fling = next(r for r in rows if r["kind"] == "fling")
    release = next(r for r in rows if r["kind"] == "touch" and r["action"] == "1")
    native_start = float(fling["aosp_y_dp"])
    slint_start = float(baseline["slint_y_dp"])
    new = {
        **{
            k: result[k]
            for k in ("case", "trial", "native_release_dp_s", "slint_release_dp_s")
        },
        "estimator_replay": estimates,
        "slint_spline_prediction": params(result["slint_release_dp_s"]),
        "native_spline_prediction": params(result["native_release_dp_s"]),
        "slint_travel_from_last_sample_before_consumed_release": float(
            frames[-1]["slint_y_dp"]
        )
        - slint_start,
        "native_travel_from_fling_callback": float(frames[-1]["aosp_y_dp"])
        - native_start,
        "slint_last_pre_consumed_release_offset": slint_start,
        "native_fling_start_offset": native_start,
        "delivery_delay_ms": (int(released["time_ns"]) - int(release["time_ns"])) / 1e6,
        "last_samples": selected[:5],
    }
    report.append(new)

# Replay the source spline in actual seconds; only fit a single clock/start offset.
# Do not rescale time or distance, and keep original plots unchanged.
table = []
low = 0.0
for i in range(100):
    alpha = i / 100
    high = 1.0
    while True:
        x = (low + high) / 2
        c = 3 * x * (1 - x)
        tx = c * ((1 - x) * 0.175 + x * 0.35) + x**3
        if abs(tx - alpha) < 0.00001:
            table.append(c * ((1 - x) * 0.5 + x) + x**3)
            break
        if tx > alpha:
            high = x
        else:
            low = x
    table.append(1.0) if i == 99 else None
for d in report:
    rows = read_rows(root / f"{d['case']}-{d['trial']}")
    release = int(
        next(r["time_ns"] for r in rows if r["kind"] == "touch" and r["action"] == "1")
    )
    consumed = int(
        next(
            r["time_ns"]
            for r in rows
            if r["kind"] == "consumed_touch" and r["action"] == "1"
        )
    )
    final = float([r for r in rows if r["kind"] == "frame"][-1]["slint_y_dp"])
    distance = d["slint_spline_prediction"]["distance_dp"]
    duration = d["slint_spline_prediction"]["duration_ms"] / 1000
    start = final - distance
    samples = [
        r
        for r in rows
        if r["kind"] == "slint_sample"
        and 5e6 < int(r["time_ns"]) - consumed < (duration + 0.03) * 1e9
    ]
    t = np.array([(int(r["time_ns"]) - consumed) / 1e9 for r in samples])
    y = np.array([float(r["slint_y_dp"]) for r in samples])
    best = None
    for shift in np.arange(-0.030, 0.0301, 0.0001):
        q = np.clip((t - shift) / duration, 0, 1)
        pred = start + distance * np.interp(q, np.linspace(0, 1, 101), table)
        error = y - pred
        rmse = float(np.sqrt(np.mean(error**2)))
        if best is None or rmse < best["rmse_dp"]:
            best = {
                "start_offset_relative_to_consumed_release_ms": round(shift * 1000, 3),
                "rmse_dp": rmse,
                "max_error_dp": float(np.max(np.abs(error))),
            }
    d["spline_curve_replay"] = best
    d["slint_start_inferred_from_final_and_source_distance"] = start
    d["inferred_start_minus_native_fling_start_dp"] = (
        start - d["native_fling_start_offset"]
    )


for d in report:
    rows = read_rows(root / f"{d['case']}-{d['trial']}")
    touches = [r for r in rows if r["kind"] == "touch"]
    consumed = [r for r in rows if r["kind"] == "consumed_touch"]
    delays = [
        (int(b["time_ns"]) - int(a["time_ns"])) / 1e6 for a, b in zip(touches, consumed)
    ]
    samples = [r for r in rows if r["kind"] == "slint_sample"]
    native = [
        r
        for r in rows
        if r["kind"] == "aosp_offset"
        and int(touches[0]["time_ns"])
        <= int(r["time_ns"])
        <= int(touches[-1]["time_ns"])
    ]
    matches = []
    for r in native:
        valid = [
            s
            for s in samples
            if 0 <= int(s["time_ns"]) - int(r["time_ns"]) < 40e6
            and abs(float(s["slint_y_dp"]) - float(r["aosp_y_dp"]))
            < 1 / density + 0.001
        ]
        if valid:
            matches.append((int(valid[0]["time_ns"]) - int(r["time_ns"])) / 1e6)
    d["observation_latency"] = {
        "median_bridge_queue_ms": float(np.median(delays)),
        "max_bridge_queue_ms": max(delays),
        "native_contact_offset_changes": len(native),
        "matched_within_one_physical_pixel": len(matches),
        "median_matched_observation_delay_ms": float(np.median(matches)),
        "max_matched_observation_delay_ms": max(matches),
        "method": "First later Slint timer sample within one physical pixel of each native contact offset; search at most 40 ms.",
    }

failures = []
for result in report:
    if (
        abs(result["estimator_replay"]["int_weighted"] - result["slint_release_dp_s"])
        >= 0.01
    ):
        failures.append(f"{result['case']}-{result['trial']}: estimator replay")
    if abs(result["inferred_start_minus_native_fling_start_dp"]) >= 0.02:
        failures.append(f"{result['case']}-{result['trial']}: inferred start alignment")
    if result["spline_curve_replay"]["rmse_dp"] >= 0.06:
        failures.append(f"{result['case']}-{result['trial']}: spline replay")
    print(
        f"{result['case']}-{result['trial']}: estimated {result['slint_release_dp_s']:.3f} dp/s, "
        f"replayed {result['estimator_replay']['int_weighted']:.3f} dp/s, "
        f"spline RMS {result['spline_curve_replay']['rmse_dp']:.4f} dp"
    )
output = args.output or root / "diagnosis.json"
output.write_text(json.dumps(report, indent=2) + "\n")
if args.verify and failures:
    raise SystemExit("\n".join(failures))
