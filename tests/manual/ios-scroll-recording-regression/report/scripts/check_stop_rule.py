#!/usr/bin/env python3
"""Check fixed stopping-speed candidates against recorded position curves."""

# cspell:ignore linalg lstsq rcond axhline figsize matplotlib suptitle xlabel ylabel ylim
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    groups = defaultdict(list)
    for file in [
        args.evidence / "positions.csv",
        args.evidence / "diagnosis/manual-curves.csv",
    ]:
        with file.open() as source:
            for row in csv.DictReader(source):
                if float(row["seconds_from_release"]) >= 0:
                    groups[(row.get("run", "manual"), row["scenario"])].append(row)
    decay = -math.log(0.135)
    results = []
    for (run, scenario), rows in groups.items():
        time = np.array([float(r["seconds_from_release"]) for r in rows])
        for toolkit in ["uikit", "slint"]:
            position = np.array([float(r[toolkit + "_offset_pt"]) for r in rows])
            train = (time >= 0.08) & (time <= 1)
            late = (time > 1) & (time <= 4.5)
            matrix = np.column_stack([np.ones(len(time)), np.exp(-decay * time)])
            offset, amplitude = np.linalg.lstsq(
                matrix[train], position[train], rcond=None
            )[0]
            speed = abs(amplitude) * decay
            moving = np.where(abs(position - position[-1]) > 0.005)[0]
            stop = float(time[moving[-1] + 1])
            result = dict(
                run=run,
                scenario=scenario,
                toolkit=toolkit,
                effective_start_speed_pt_s=float(speed),
                observed_position_stop_s=stop,
                inferred_speed_at_stop_pt_s=speed * math.exp(-decay * stop),
            )
            for cutoff in [1.0, 10.0]:
                predicted_stop = math.log(speed / cutoff) / decay
                prediction = offset + amplitude * np.exp(
                    -decay * np.minimum(time, predicted_stop)
                )
                error = prediction - position
                result[str(cutoff)] = dict(
                    predicted_stop_s=predicted_stop,
                    timing_error_s=predicted_stop - stop,
                    late_rms_pt=float(np.sqrt(np.mean(error[late] ** 2))),
                    late_max_pt=float(np.max(abs(error[late]))),
                )
            results.append(result)
    output = dict(decay_rate=decay, training_window_s=[0.08, 1.0], cases=results)
    (args.evidence / "diagnosis/stop-rule-check.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for name, color, label in [
        ("uikit", "#c53b32", "UIKit"),
        ("slint", "#1976b4", "Slint"),
    ]:
        rows = [r for r in results if r["toolkit"] == name]
        axes[0].plot(
            range(1, len(rows) + 1),
            [r["inferred_speed_at_stop_pt_s"] for r in rows],
            "o",
            color=color,
            label=label,
        )
    axes[0].set_xlabel("Recorded curve")
    axes[0].set_ylabel("Effective stopping speed from early fit (pt/s)")
    axes[0].set_ylim(0, 12)
    native = [r for r in results if r["toolkit"] == "uikit"]
    for cutoff, color, label in [
        ("1.0", "#1976b4", "1 pt/s cutoff"),
        ("10.0", "#c53b32", "10 pt/s cutoff"),
    ]:
        axes[1].plot(
            range(1, len(native) + 1),
            [r[cutoff]["timing_error_s"] * 1000 for r in native],
            "o",
            color=color,
            label=label,
        )
    axes[1].axhline(0, color="#666666", linewidth=0.7)
    axes[1].set_xlabel("Recorded UIKit curve")
    axes[1].set_ylabel("Predicted stop minus observed stop (ms)")
    for axis in axes:
        axis.legend()
        axis.grid(alpha=0.2)
    fig.suptitle(
        "Stopping-rule check · six manual + sixteen automated curves · first-second fit"
    )
    fig.tight_layout()
    fig.savefig(args.evidence.parent / "figures/stopping-rule-diagnosis.png", dpi=160)
    plt.close(fig)
    print("Evaluated", len(results) // 2, "paired curves")


if __name__ == "__main__":
    main()
