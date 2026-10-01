# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT
# cspell:ignore axvline flatnonzero fontsize interp polyfit suptitle xlabel xlim ylabel

import argparse
import csv
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser()
parser.add_argument("--raw", type=Path, required=True)
parser.add_argument("--platform", choices=["phone", "simulator"], required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--prefix", default="release-public")
parser.add_argument("--distances", type=int, nargs="+", default=[100, 600])
parser.add_argument("--repeats", type=int, default=2)
parser.add_argument("--speeds", type=int, nargs="+", default=[400, 1600])
parser.add_argument("--holds", type=int, nargs="+", default=[0, 400])
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
summaries = []
traces = {}

for distance in args.distances:
    fig, axes = plt.subplots(
        len(args.holds),
        len(args.speeds),
        squeeze=False,
        figsize=(12, 8 if len(args.holds) > 1 else 5),
        constrained_layout=True,
    )
    for column, requested_speed in enumerate(args.speeds):
        for row_index, requested_stop in enumerate(args.holds):
            ax = axes[row_index, column]
            for trial in range(1, args.repeats + 1):
                name = f"{args.prefix}-d{distance}-v{requested_speed}-hold{requested_stop}-trial{trial}"
                with (args.raw / f"input-{name}.csv").open() as source:
                    events = list(csv.DictReader(source))
                callbacks = [r for r in events if r["event_type"] == "touch_callback"]
                press = next(r for r in callbacks if r["touch_phase"] == "0")
                release = next(
                    r for r in reversed(callbacks) if r["touch_phase"] == "3"
                )
                release_time = float(release["callback_time"])
                release_stamp = float(release["touch_timestamp"])
                samples = {
                    float(r["touch_timestamp"]): float(r["y"])
                    for r in events
                    if r["event_type"] == "touch_callback"
                }
                sample_time = np.array(sorted(samples))
                finger_y = np.array([samples[t] for t in sample_time])
                changing = np.flatnonzero(abs(np.diff(finger_y)) > 0.5) + 1
                last_motion_time = sample_time[changing[-1]]
                actual_stop_ms = (release_stamp - last_motion_time) * 1000
                final_samples = sample_time >= release_stamp - 0.05
                release_finger_speed = (
                    float(
                        np.polyfit(
                            sample_time[final_samples] - release_stamp,
                            finger_y[final_samples],
                            1,
                        )[0]
                    )
                    if sum(final_samples) >= 2
                    else None
                )
                motion_end = last_motion_time
                motion_window = (sample_time >= motion_end - 0.05) & (
                    sample_time <= motion_end
                )
                measured_motion_speed = (
                    float(
                        np.polyfit(
                            sample_time[motion_window] - motion_end,
                            finger_y[motion_window],
                            1,
                        )[0]
                    )
                    if sum(motion_window) >= 2
                    else None
                )
                final_stop = sample_time >= release_stamp - 0.35
                stopped_range = float(np.ptp(finger_y[final_stop]))
                complete = sum(r["touch_phase"] == "0" for r in callbacks) == 1
                distance_delivered = abs(float(release["press_dy"]))
                gesture_qualified = (
                    complete and abs(distance_delivered - distance) <= 0.5
                )
                if requested_stop:
                    gesture_qualified &= actual_stop_ms >= 350 and stopped_range <= 0.5
                else:
                    gesture_qualified &= (
                        actual_stop_ms <= 30 and release_finger_speed is not None
                    )
                    gesture_qualified &= (
                        release_finger_speed is not None and release_finger_speed > 200
                    )
                with (args.raw / f"scroll-{name}.csv").open() as source:
                    frames = list(csv.DictReader(source))
                time = np.array(
                    [float(r["callback_time"]) - release_time for r in frames]
                )
                native = -np.array([float(r["uikit_offset"]) for r in frames])
                slint = -np.array([float(r["slint_offset"]) for r in frames])
                native_release = -float(release["uikit_content_y"])
                slint_release = -float(release["slint_content_y"])
                post = time >= 0
                window = post & (time <= 0.8)
                max_gap = float(np.max(np.diff(time[window])) * 1000)
                ended = [
                    r
                    for r in events
                    if r["event_type"] == "pan" and r["pan_state"] == "ended"
                ]
                summary = {
                    "platform": args.platform,
                    "scenario": name,
                    "requested_distance_pt": distance,
                    "requested_velocity_setting": requested_speed,
                    "requested_stop_ms": requested_stop,
                    "trial": trial,
                    "gesture_qualified": bool(gesture_qualified),
                    "sampling_qualified": max_gap <= 30,
                    "delivered_distance_pt": distance_delivered,
                    "delivered_motion_speed_pt_s": measured_motion_speed,
                    "measured_last_50_ms_finger_speed_pt_s": release_finger_speed,
                    "actual_stop_before_release_ms": float(actual_stop_ms),
                    "final_350_ms_finger_range_pt": stopped_range,
                    "native_recognizer_release_velocity_pt_s": float(
                        ended[0]["pan_velocity_y"]
                    )
                    if ended
                    else None,
                    "move_callbacks": sum(r["touch_phase"] == "1" for r in callbacks),
                    "median_frame_interval_ms": float(np.median(np.diff(time)) * 1000),
                    "max_return_sample_gap_ms": max_gap,
                    "uikit_release_exposure_pt": native_release,
                    "slint_release_exposure_pt": slint_release,
                    "starting_exposure_gap_pt": slint_release - native_release,
                    "starting_exposures_within_0_5_pt": abs(
                        slint_release - native_release
                    )
                    <= 0.5,
                    "return_rms_0_8_s_pt": float(
                        np.sqrt(np.mean((native[window] - slint[window]) ** 2))
                    ),
                    "max_return_gap_pt": float(np.max(abs(native[post] - slint[post]))),
                }
                for label, values, start in [
                    ("uikit", native, native_release),
                    ("slint", slint, slint_release),
                ]:
                    post_indices = np.flatnonzero(post)
                    peak_index = post_indices[np.argmax(values[post])]
                    summary[label + "_extra_exposure_after_release_pt"] = float(
                        max(0, values[peak_index] - start)
                    )
                    summary[label + "_peak_time_after_release_ms"] = float(
                        time[peak_index] * 1000
                    )
                    outside = np.flatnonzero(post & (abs(values) > 0.5))
                    summary[label + "_settled_within_0_5_pt_s"] = (
                        float(time[min(outside[-1] + 1, len(time) - 1)])
                        if len(outside)
                        else 0
                    )
                    summary[label + "_settled_in_recording"] = bool(
                        abs(values[-1]) <= 0.5
                    )
                summaries.append(summary)
                traces[(distance, requested_speed, requested_stop, trial)] = (
                    time,
                    native,
                    slint,
                )
                alpha = 1 if trial == 1 else 0.45
                ax.plot(
                    time,
                    native,
                    color="#c53228",
                    lw=2,
                    alpha=alpha,
                    label=f"UIKit repeat {trial}",
                )
                ax.plot(
                    time,
                    slint,
                    color="#165db0",
                    ls="--",
                    lw=2,
                    alpha=alpha,
                    label=f"Slint repeat {trial}",
                )
            ax.axvline(0, color="#555", ls=":", lw=1)
            ax.set_xlim(-0.05, 0.8)
            ax.set_xlabel("Time since delivered release (seconds)")
            ax.set_ylabel("Background exposed (points)")
            ax.set_title(
                f"Velocity setting {requested_speed}; "
                + (
                    "release while moving"
                    if not requested_stop
                    else (
                        "one-pixel slow finish"
                        if args.prefix == "release-quiet"
                        else "hold exactly still for 400 ms"
                    )
                )
            )
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)
    fig.suptitle(
        f"{args.platform.capitalize()}: {distance}-point pull, "
        + (
            "fresh low-velocity release"
            if args.prefix == "release-quiet"
            else "moving versus exact hold"
        ),
        fontsize=15,
    )
    fig.savefig(args.output / f"{args.platform}-release-d{distance}.png", dpi=170)

comparisons = []
grid = np.arange(0, 0.801, 0.05)
for distance in (
    args.distances
    if 400 in args.speeds and 1600 in args.speeds and 400 in args.holds
    else []
):
    for trial in range(1, args.repeats + 1):
        slow_t, slow_u, _ = traces[(distance, 400, 400, trial)]
        fast_t, fast_u, _ = traces[(distance, 1600, 400, trial)]
        difference = np.interp(grid, fast_t, fast_u) - np.interp(grid, slow_t, slow_u)
        comparisons.append(
            {
                "distance_pt": distance,
                "trial": trial,
                "native_stopped_speed_comparison_rms_at_20_hz_pt": float(
                    np.sqrt(np.mean(difference**2))
                ),
                "native_stopped_speed_comparison_max_at_20_hz_pt": float(
                    max(abs(difference))
                ),
                "note": "Actual exposures; no amplitude normalization or animation time shift.",
            }
        )
payload = {
    "platform": args.platform,
    "traces": summaries,
    "stopped_speed_comparisons": comparisons,
}
(args.output / f"{args.platform}-release-summary.json").write_text(
    json.dumps(payload, indent=2) + "\n"
)
with (args.output / f"{args.platform}-release-summary.csv").open(
    "w", newline=""
) as output:
    writer = csv.DictWriter(output, fieldnames=summaries[0].keys(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(summaries)
for r in summaries:
    print(
        f"d{r['requested_distance_pt']} v{r['requested_velocity_setting']} hold{r['requested_stop_ms']} "
        f"#{r['trial']}: stop={r['actual_stop_before_release_ms']:.1f}ms "
        f"qualified={r['gesture_qualified']}/{r['sampling_qualified']} "
        f"extra UIKit/Slint={r['uikit_extra_exposure_after_release_pt']:.2f}/"
        f"{r['slint_extra_exposure_after_release_pt']:.2f}pt"
    )
print(json.dumps(comparisons, indent=2))
