# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT
# cspell:ignore axhline axvline flatnonzero fontsize interp polyfit suptitle xlabel xlim ylabel ylim

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
parser.add_argument("--boundary", choices=["top", "bottom"], default="top")
args = parser.parse_args()
direction = -1 if args.boundary == "top" else 1
args.output.mkdir(parents=True, exist_ok=True)
velocities = [400, 1000, 1500, 2200, 3000, 4500]
summaries = []
figures = [
    plt.subplots(3, 2, figsize=(13, 11), constrained_layout=True) for _ in range(2)
]


def impact(time, values, boundary):
    crossing = np.flatnonzero((time >= 0) & (values >= boundary))
    if not len(crossing):
        return {"hit": False}
    index = crossing[0]
    hit_time = float(time[index])
    if index and values[index] != values[index - 1]:
        fraction = (boundary - values[index - 1]) / (values[index] - values[index - 1])
        hit_time = float(time[index - 1] + fraction * (time[index] - time[index - 1]))
    before = (time >= max(0, hit_time - 0.05)) & (time < hit_time)
    speed = (
        float(np.polyfit(time[before] - hit_time, values[before], 1)[0])
        if sum(before) >= 3
        else None
    )
    after = np.flatnonzero(time >= hit_time)
    peak = after[np.argmax(values[after])]
    returning = np.flatnonzero((time >= time[peak]) & (values <= boundary + 0.5))
    outside = np.flatnonzero((time >= hit_time) & (abs(values - boundary) > 0.5))
    settled = bool(abs(values[-1] - boundary) <= 0.5)
    settling_time = (
        float(time[min(outside[-1] + 1, len(time) - 1)]) if len(outside) else hit_time
    )
    return {
        "hit": True,
        "hit_time_from_release_s": hit_time,
        "impact_speed_50_ms_fit_pt_s": speed,
        "impact_speed_sample_count": int(sum(before)),
        "peak_overscroll_pt": float(max(0, values[peak] - boundary)),
        "overscroll_resolved_at_0_5_pt": bool(values[peak] - boundary > 0.5),
        "peak_time_from_release_s": float(time[peak]),
        "impact_to_peak_s": float(time[peak] - hit_time),
        "first_return_to_boundary_s": float(time[returning[0]])
        if len(returning)
        else None,
        "settled_in_recording": settled,
        "settled_time_from_release_s": settling_time if settled else None,
        "impact_to_settled_s": settling_time - hit_time if settled else None,
    }


for cell, velocity in enumerate(velocities):
    for trial in [1, 2]:
        name = f"collision-{args.boundary}-v{velocity}-trial{trial}"
        geometry = json.loads((args.raw / f"geometry-{name}.json").read_text())
        native_limit = (
            0
            if args.boundary == "top"
            else geometry["uikit_content"][1] - geometry["uikit_viewport"][3]
        )
        slint_limit = (
            0
            if args.boundary == "top"
            else geometry["slint_content"][1] - geometry["slint_viewport"][3]
        )
        same_geometry = (
            geometry["uikit_content"] == geometry["slint_content"]
            and geometry["uikit_viewport"] == geometry["slint_viewport"]
        )
        with (args.raw / f"input-{name}.csv").open() as source:
            events = list(csv.DictReader(source))
        callbacks = [r for r in events if r["event_type"] == "touch_callback"]
        press = next(r for r in callbacks if r["touch_phase"] == "0")
        release = next(r for r in reversed(callbacks) if r["touch_phase"] == "3")
        origin = float(release["callback_time"])
        motion = {float(r["touch_timestamp"]): float(r["y"]) for r in callbacks}
        touch_time = np.array(sorted(motion))
        touch_y = np.array([motion[t] for t in touch_time])
        recent = touch_time >= float(release["touch_timestamp"]) - 0.05
        delivered_speed = (
            -float(
                np.polyfit(touch_time[recent] - touch_time[-1], touch_y[recent], 1)[0]
            )
            if sum(recent) >= 2
            else None
        )
        with (args.raw / f"scroll-{name}.csv").open() as source:
            frames = list(csv.DictReader(source))
        time = np.array([float(r["callback_time"]) - origin for r in frames])
        native = np.array([float(r["uikit_offset"]) for r in frames])
        slint = np.array([float(r["slint_offset"]) for r in frames])
        contact = time < 0
        post = time >= 0
        geometry_ok = (
            same_geometry
            and abs(float(press["uikit_content_y"]) - 648) <= 0.5
            and abs(float(press["slint_content_y"]) - 648) <= 0.5
        )
        inside_at_release = (
            direction * (float(release["uikit_content_y"]) - native_limit) < 0
            and direction * (float(release["slint_content_y"]) - slint_limit) < 0
        )
        inside_during_contact = bool(
            np.all(direction * (native[contact] - native_limit) < 0)
            and np.all(direction * (slint[contact] - slint_limit) < 0)
        )
        complete = sum(r["touch_phase"] == "0" for r in callbacks) == 1
        delivered_distance = abs(float(release["press_dy"]))
        max_frame_gap = float(np.max(np.diff(time[post])) * 1000)
        trace = {
            "platform": args.platform,
            "scenario": name,
            "velocity_setting": velocity,
            "trial": trial,
            "negative_control": velocity == 400,
            "same_geometry": same_geometry,
            "native_viewport_pt": geometry["uikit_viewport"],
            "slint_viewport_pt": geometry["slint_viewport"],
            "content_size_pt": geometry["uikit_content"],
            "boundary": args.boundary,
            "native_boundary_offset_pt": native_limit,
            "slint_boundary_offset_pt": slint_limit,
            "delivered_distance_pt": delivered_distance,
            "measured_last_50_ms_finger_speed_pt_s": abs(delivered_speed)
            if delivered_speed is not None
            else None,
            "measured_last_50_ms_finger_velocity_y_pt_s": -delivered_speed
            if delivered_speed is not None
            else None,
            "measured_last_50_ms_content_velocity_pt_s": delivered_speed,
            "native_recognizer_release_velocity_pt_s": -float(
                release["pan_velocity_y"]
            ),
            "uikit_release_offset_pt": float(release["uikit_content_y"]),
            "slint_release_offset_pt": float(release["slint_content_y"]),
            "inside_bounds_during_contact_and_at_release": inside_during_contact
            and inside_at_release,
            "gesture_qualified": bool(
                geometry_ok
                and complete
                and abs(delivered_distance - 200) <= 0.5
                and inside_during_contact
                and inside_at_release
            ),
            "sampling_qualified": max_frame_gap <= 30,
            "median_sampling_interval_ms": float(np.median(np.diff(time)) * 1000),
            "max_post_release_sample_gap_ms": max_frame_gap,
            "recording_duration_post_release_s": float(time[-1]),
            "uikit": impact(time, direction * (native - native_limit), 0),
            "slint": impact(time, direction * (slint - slint_limit), 0),
        }
        grid = np.arange(0, min(1.5, float(time[-1])) + 0.001, 0.05)
        gap = np.interp(grid, time, slint) - np.interp(grid, time, native)
        trace["offset_rms_at_20_hz_pt"] = float(np.sqrt(np.mean(gap**2)))
        trace["max_offset_gap_at_20_hz_pt"] = float(max(abs(gap)))
        trace["hit_outcomes_match"] = trace["uikit"]["hit"] == trace["slint"]["hit"]
        trace["resolved_bounce_outcomes_match"] = trace["uikit"].get(
            "overscroll_resolved_at_0_5_pt", False
        ) == trace["slint"].get("overscroll_resolved_at_0_5_pt", False)
        summaries.append(trace)
        for plot_index, (_, axes) in enumerate(figures):
            ax = axes.flat[cell]
            alpha = 1 if trial == 1 else 0.45
            native_y = (
                native if plot_index == 0 else direction * (native - native_limit)
            )
            slint_y = slint if plot_index == 0 else direction * (slint - slint_limit)
            ax.plot(
                time,
                native_y,
                color="#c53228",
                lw=2,
                alpha=alpha,
                label=f"UIKit repeat {trial}",
            )
            ax.plot(
                time,
                slint_y,
                color="#165db0",
                ls="--",
                lw=2,
                alpha=alpha,
                label=f"Slint repeat {trial}",
            )
            if trial == 1:
                ax.axhline(
                    native_limit if plot_index == 0 else 0, color="#777", ls=":", lw=1
                )
                for label, color in [("uikit", "#c53228"), ("slint", "#165db0")]:
                    if trace[label]["hit"]:
                        ax.axvline(
                            trace[label]["hit_time_from_release_s"],
                            color=color,
                            ls=":",
                            alpha=0.5,
                        )
            ax.set_xlim(
                0,
                min(float(time[-1]), 2.6)
                if plot_index == 0 or velocity <= 1000
                else 1.5,
            )
            if (
                plot_index == 1
                and not trace["uikit"]["hit"]
                and not trace["slint"]["hit"]
            ):
                ax.set_ylim(min(float(native_y.min()), float(slint_y.min())) - 10, 10)
            elif plot_index == 1:
                ax.set_ylim(
                    -30,
                    max(
                        40,
                        float(
                            max(
                                (direction * (native - native_limit)).max(),
                                (direction * (slint - slint_limit)).max(),
                            )
                        )
                        * 1.15,
                    ),
                )
            ax.set_xlabel("Time since delivered release (seconds)")
            ax.set_ylabel(
                "List offset (points)"
                if plot_index == 0
                else f"Distance past {args.boundary} (points)"
            )
            ax.set_title(
                f"Velocity setting {velocity}"
                + (" - no-hit control" if velocity == 400 else "")
            )
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)

for (fig, _), title, suffix in zip(
    figures,
    [
        "Free flight, edge contact, and return",
        "Bounce detail on the same release clock",
    ],
    ["flight", "bounce"],
):
    fig.suptitle(
        f"{args.platform.capitalize()}: {title}; item 10, {args.boundary} boundary",
        fontsize=15,
    )
    fig.savefig(
        args.output / f"{args.platform}-{args.boundary}-collision-{suffix}.png", dpi=170
    )
(args.output / f"{args.platform}-{args.boundary}-collision-summary.json").write_text(
    json.dumps(summaries, indent=2) + "\n"
)
for r in summaries:
    print(
        r["scenario"],
        "qualified",
        r["gesture_qualified"],
        r["sampling_qualified"],
        "UIKit",
        r["uikit"],
        "Slint",
        r["slint"],
    )
