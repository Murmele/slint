# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT
# cspell:ignore fontsize runloop suptitle xlabel xlim ylabel

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
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
variants = [
    "spring-coordinate",
    "spring-runloop",
    "spring-zero-velocity",
    "spring-history",
]
titles = [
    "Current candidate",
    "Defer release one run-loop turn",
    "Zero initial spring velocity",
    "Direct touch time and history",
]
summaries = []
figures = [
    plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True) for _ in range(2)
]
axes = np.vstack([pair[1] for pair in figures])
for row_index, variant in enumerate(variants):
    for column, distance in enumerate([200, 600]):
        ax = axes[row_index, column]
        for trial in [1, 2]:
            name = f"overscroll-{variant}-d{distance}-trial-{trial}"
            with (args.raw / f"input-{name}.csv").open() as source:
                events = list(csv.DictReader(source))
            callbacks = [r for r in events if r["event_type"] == "touch_callback"]
            press = next(r for r in callbacks if r["touch_phase"] == "0")
            release = next(r for r in reversed(callbacks) if r["touch_phase"] == "3")
            release_time = float(release["callback_time"])
            forwarded = next(
                r for r in events if r["event_type"] == "slint_release_forwarded"
            )
            with (args.raw / f"scroll-{name}.csv").open() as source:
                frames = list(csv.DictReader(source))
            time = np.array([float(r["callback_time"]) - release_time for r in frames])
            native = -np.array([float(r["uikit_offset"]) for r in frames])
            slint = -np.array([float(r["slint_offset"]) for r in frames])
            window = (time >= 0) & (time <= 0.8)
            returned = time >= 0
            early = (time >= 0) & (time <= 0.06)
            tail = (time >= 0.15) & (time <= 0.8)
            hold = (time >= -0.15) & (time < 0)
            error = slint - native
            max_frame_gap = float(np.max(np.diff(time[window])) * 1000)
            complete = sum(r["touch_phase"] == "0" for r in callbacks) == 1
            delivered_distance = abs(float(release["press_dy"]))
            qualified = (
                complete
                and abs(delivered_distance - distance) <= 0.5
                and max_frame_gap <= 30
            )
            summary = {
                "scenario": name,
                "variant": variant,
                "requested_distance_pt": distance,
                "trial": trial,
                "complete_and_timing_qualified": qualified,
                "delivered_distance_pt": delivered_distance,
                "move_callbacks": sum(r["touch_phase"] == "1" for r in callbacks),
                "coalesced_samples": sum(
                    r["event_type"] == "coalesced_sample" for r in events
                ),
                "median_frame_interval_ms": float(np.median(np.diff(time)) * 1000),
                "max_return_frame_gap_ms": max_frame_gap,
                "release_forwarding_delay_ms": (
                    float(forwarded["callback_time"]) - release_time
                )
                * 1000,
                "release_sample_delivery_age_ms": (
                    release_time - float(release["touch_timestamp"])
                )
                * 1000,
                "uikit_pre_release_exposure_pt": -float(release["uikit_content_y"]),
                "slint_pre_release_exposure_pt": -float(release["slint_content_y"]),
                "max_hold_gap_pt": float(np.max(abs(error[hold]))),
                "return_rms_0_8_s_pt": float(np.sqrt(np.mean(error[window] ** 2))),
                "max_return_gap_pt": float(np.max(abs(error[returned]))),
                "max_first_60_ms_gap_pt": float(np.max(abs(error[early]))),
                "tail_rms_0_15_to_0_8_s_pt": float(np.sqrt(np.mean(error[tail] ** 2))),
                "full_return_within_0_5_pt": bool(np.all(abs(error[returned]) <= 0.5)),
                "both_lists_settled": bool(
                    abs(native[-1]) <= 0.5 and abs(slint[-1]) <= 0.5
                ),
                "qualified_for_physics": bool(
                    qualified and abs(native[-1]) <= 0.5 and abs(slint[-1]) <= 0.5
                ),
            }
            summaries.append(summary)
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
        ax.set_title(f"{titles[row_index]}: {distance}-point pull")
        ax.set_xlim(0, 0.8)
        ax.set_xlabel("Time since delivered release (seconds)")
        ax.set_ylabel("Background exposed (points)")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
for (fig, _), title, name in zip(
    figures,
    [
        "Simulator: current spring and deferred release, actual time and distance",
        "Simulator: zero initial velocity and direct touch history, actual time and distance",
    ],
    ["simulator-release-order.png", "simulator-velocity-and-history.png"],
):
    fig.suptitle(title, fontsize=15)
    fig.savefig(args.output / name, dpi=170)
(args.output / "simulator-summary.json").write_text(
    json.dumps(summaries, indent=2) + "\n"
)
with (args.output / "simulator-summary.csv").open("w", newline="") as output:
    writer = csv.DictWriter(output, fieldnames=summaries[0].keys(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(summaries)
for r in summaries:
    print(
        f"{r['variant']:22} d{r['requested_distance_pt']:3} #{r['trial']}: "
        f"RMS {r['return_rms_0_8_s_pt']:.3f}, max {r['max_return_gap_pt']:.3f}, "
        f"hold {r['max_hold_gap_pt']:.3f}, qualified {r['complete_and_timing_qualified']}"
    )
