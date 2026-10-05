#!/usr/bin/env python3
"""Compare measured, paired regression captures across frozen engine revisions."""

# cspell:ignore matplotlib xlabel ylabel suptitle figsize sharex sharey interp axvline xlim ylim fontsize supxlabel supylabel
import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def read_csv(path):
    with path.open() as source:
        return list(csv.DictReader(source))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--latest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.output / "evidence"
    figures = args.output / "figures"
    evidence.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    records = []
    position_rows = []
    traces = {}
    commits = {
        name: json.loads((directory / "metadata.json").read_text())["engine_commit"]
        for name, directory in [("baseline", args.baseline), ("latest", args.latest)]
    }
    for run, root in [("baseline", args.baseline), ("latest", args.latest)]:
        for gesture in [9, 10, 8, 13]:
            for trial in [1, 2]:
                scenario = f"recorded-gesture{gesture}-trial{trial}"
                raw = root / "raw"
                result = json.loads((raw / f"regression-{scenario}.json").read_text())
                events = [
                    r
                    for r in read_csv(raw / f"input-{scenario}.csv")
                    if r["event_type"] == "touch_callback"
                ]
                presses = [r for r in events if r["touch_phase"] == "0"]
                releases = [r for r in events if r["touch_phase"] == "3"]
                if len(presses) != 1 or len(releases) != 1:
                    raise ValueError(f"{run}/{scenario}: incomplete delivered gesture")
                press, release = presses[0], releases[0]
                origin = float(release["callback_time"])
                frames = read_csv(raw / f"scroll-{scenario}.csv")
                t = np.array([float(r["callback_time"]) - origin for r in frames])
                native = np.array([float(r["uikit_offset"]) for r in frames])
                slint = np.array([float(r["slint_offset"]) for r in frames])
                geometry = json.loads((raw / f"geometry-{scenario}.json").read_text())
                if geometry["uikit_viewport"] != geometry["slint_viewport"]:
                    raise ValueError("Geometry mismatch")
                issues = []
                if result["max_frame_gap_ms"] > 30:
                    issues.append("sampling gap")
                if (
                    max(result["uikit_final_range_pt"], result["slint_final_range_pt"])
                    > 0.05
                ):
                    issues.append("not settled")
                if result["uikit_post_range_pt"] <= 5:
                    issues.append("UIKit did not coast")
                travel_gap = abs(
                    result["slint_post_travel_pt"] - result["uikit_post_travel_pt"]
                )
                tail_delta = result["slint_settle_01_s"] - result["uikit_settle_01_s"]
                records.append(
                    dict(
                        run=run,
                        engine_commit=commits[run],
                        scenario=scenario,
                        gesture=gesture,
                        trial=trial,
                        delivered_dy_pt=float(release["press_dy"]),
                        contact_ms=(
                            float(release["touch_timestamp"])
                            - float(press["touch_timestamp"])
                        )
                        * 1000,
                        native_pan_velocity_y=float(release["pan_velocity_y"]),
                        geometry=geometry,
                        delivery_issues=issues,
                        measured=result,
                        travel_gap_pt=travel_gap,
                        tail_delta_s=tail_delta,
                        coast_parity=result["slint_post_range_pt"] > 5,
                        travel_parity=travel_gap <= 5,
                        tail_parity=(
                            abs(tail_delta) <= 0.15
                            and abs(
                                result["slint_settle_1_s"] - result["uikit_settle_1_s"]
                            )
                            <= 0.15
                        )
                        if gesture in [8, 13]
                        else None,
                    )
                )
                traces[(run, gesture, trial)] = (t, native, slint)
                for tt, nn, ss in zip(t, native, slint):
                    position_rows.append(
                        dict(
                            run=run,
                            scenario=scenario,
                            seconds_from_release=f"{tt:.9f}",
                            uikit_offset_pt=f"{nn:.3f}",
                            slint_offset_pt=f"{ss:.3f}",
                        )
                    )
    (evidence / "results.json").write_text(
        json.dumps(
            dict(
                criteria=dict(
                    travel_gap_pt=5,
                    tail_gap_s=0.15,
                    settling_reference="Own final observed offset, at 0.1 and 1 pt",
                ),
                cases=records,
            ),
            indent=2,
        )
        + "\n"
    )
    with (evidence / "positions.csv").open("w") as target:
        writer = csv.DictWriter(
            target, fieldnames=list(position_rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(position_rows)
    fig, axes = plt.subplots(4, 2, figsize=(12, 13), sharex=True)
    for row, gesture in enumerate([9, 10, 8, 13]):
        for col, run in enumerate(["baseline", "latest"]):
            t, n, s = traces[(run, gesture, 1)]
            ax = axes[row, col]
            ax.plot(t, n, color="#c53b32", label="UIKit measured")
            ax.plot(t, s, color="#1976b4", label="Slint measured")
            ax.axvline(0, color="#777777", lw=0.7)
            ax.set_xlim(-0.15, 4.5)
            ax.grid(alpha=0.2)
            ax.set_title(
                f"{run}: {commits[run][:10]} · gesture {gesture} · trial 1", fontsize=10
            )
            ax.set_ylabel("Actual content offset (pt)")
            ax.legend(fontsize=8)
    fig.supxlabel("Seconds from delivered release callback")
    fig.suptitle(
        "Recorded-profile regression · actual time and offsets · no normalization"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(figures / "paired-positions.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
    for row, gesture in enumerate([8, 13]):
        for col, run in enumerate(["baseline", "latest"]):
            t, n, s = traces[(run, gesture, 1)]
            ax = axes[row, col]
            tt = np.arange(0.6, 4, 0.05)
            for yy, color, label in [(n, "#c53b32", "UIKit"), (s, "#1976b4", "Slint")]:
                speed = abs(
                    (np.interp(tt + 0.05, t, yy) - np.interp(tt - 0.05, t, yy)) / 0.1
                )
                ax.plot(tt, speed, color=color, label=label)
            ax.set_xlim(0.9, 3.6)
            ax.set_ylim(0, 35)
            ax.grid(alpha=0.2)
            ax.legend()
            ax.set_title(f"{run}: {commits[run][:10]} · gesture {gesture} · trial 1")
    fig.supxlabel("Seconds from delivered release callback")
    fig.supylabel("Speed derived from measured positions (pt/s)")
    fig.suptitle("Settling tails · 100 ms position differences evaluated at 20 Hz")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(figures / "settling-tails.png", dpi=160)
    plt.close(fig)
    for run in ["baseline", "latest"]:
        cases = [r for r in records if r["run"] == run]
        tails = [r for r in cases if r["tail_parity"] is not None]
        print(
            run,
            "delivery qualified",
            sum(not r["delivery_issues"] for r in cases),
            "/8",
            "travel pass",
            sum(r["travel_parity"] for r in cases),
            "/8",
            "tail pass",
            sum(r["tail_parity"] for r in tails),
            "/4",
            "tail delta",
            min(r["tail_delta_s"] for r in tails),
            max(r["tail_delta_s"] for r in tails),
        )


if __name__ == "__main__":
    main()
