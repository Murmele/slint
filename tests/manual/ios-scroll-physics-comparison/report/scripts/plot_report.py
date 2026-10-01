# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT
# cspell:ignore axvline fontsize suptitle xlabel xlim ylabel ylim

import argparse, csv
from pathlib import Path
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser()
parser.add_argument("--round1", type=Path, required=True)
parser.add_argument("--round2", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)


def capture(root, stem):
    rows = list(csv.DictReader((root / f"input-{stem}.csv").open()))
    callbacks = [r for r in rows if r["event_type"] == "touch_callback"]
    start = float(callbacks[0]["callback_time"])
    end = float(
        next(r for r in reversed(callbacks) if r["touch_phase"] == "3")["callback_time"]
    )
    fr = list(csv.DictReader((root / f"scroll-{stem}.csv").open()))
    time = np.array([float(r["callback_time"]) for r in fr])
    native = np.array([float(r["uikit_offset"]) for r in fr])
    slint = np.array([float(r["slint_offset"]) for r in fr])
    return time, native, slint, start, end


def pair(ax, t, u, s, alpha=1, repeat=None):
    suffix = "" if repeat is None else f" repeat {repeat}"
    ax.plot(t, u, color="#c53228", lw=2, alpha=alpha, label="UIKit" + suffix)
    ax.plot(t, s, color="#165db0", ls="--", lw=2, alpha=alpha, label="Slint" + suffix)
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)


fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
for col, d in enumerate([50, 200, 600]):
    t, u, s, press, release = capture(args.round1, f"overscroll-baseline-d{d}-trial-1")
    u = -u
    s = -s
    for row, origin in [(0, press), (1, release)]:
        pair(axes[row, col], t - origin, u, s)
        axes[row, col].set_ylabel("Background exposed (points)")
    axes[0, col].axvline(release - press, color="#555", ls=":")
    axes[0, col].set_xlim(0, release - press + 0.15)
    axes[0, col].set_xlabel("Time since delivered press (seconds)")
    axes[0, col].set_title(f"Original {d}-point pull")
    mask = t >= release
    gap = max(abs(u[mask] - s[mask]))
    axes[1, col].set_xlim(0, 0.8)
    axes[1, col].set_xlabel("Time since delivered release (seconds)")
    axes[1, col].set_title(f"Original return: maximum gap {gap:.2f} pt")
fig.suptitle("Part 1: original Slint versus UIKit on the physical iPhone", fontsize=15)
fig.savefig(args.output / "baseline-pull-and-return.png", dpi=170)

fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
for row, variant in enumerate(["baseline", "threshold10"]):
    for col, (delay, count) in enumerate([(0, 2), (0, 16), (80, 16)]):
        ax = axes[row, col]
        for trial in [1, 2]:
            t, u, s, press, release = capture(
                args.round1,
                f"pan-entry-code-{variant}-d40-delay{delay}-points{count}-trial-{trial}",
            )
            pair(
                ax,
                (t - press) * 1000,
                u - 1000,
                s - 1000,
                1 if trial == 1 else 0.4,
                trial,
            )
        ax.set_xlim(0, 350)
        ax.set_ylim(-1, 35)
        ax.set_xlabel("Time since delivered press (ms)")
        ax.set_ylabel("List travel (points)")
        ax.set_title(
            f"{'Original 8-point threshold' if row == 0 else '10-point threshold'}\n{'Immediate' if delay == 0 else 'Explicit 80 ms hold'}, {count} requested waypoints"
        )
fig.suptitle(
    "Part 2: threshold code change, two repeated captures per condition", fontsize=15
)
fig.savefig(args.output / "pan-before-after.png", dpi=170)

fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
for row, variant in enumerate(["spring-coordinate", "spring-clock"]):
    for col, d in enumerate([200, 600]):
        ax = axes[row, col]
        for trial in [1, 2]:
            t, u, s, press, release = capture(
                args.round2, f"overscroll-{variant}-d{d}-trial-{trial}"
            )
            pair(ax, t - release, -u, -s, 1 if trial == 1 else 0.4, trial)
        ax.set_xlim(0, 0.8)
        ax.set_xlabel("Time since delivered release (seconds)")
        ax.set_ylabel("Background exposed (points)")
        ax.set_title(
            f"{'Animation-tick start' if row == 0 else 'Live backend clock start'}\n{d}-point pull"
        )
fig.suptitle(
    "Part 3: the final clock experiment did not improve return RMS error", fontsize=15
)
fig.savefig(args.output / "release-clock-check.png", dpi=170)

fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), constrained_layout=True)
for col, d in enumerate([50, 200, 600]):
    t, u, s, press, release = capture(
        args.round1, f"overscroll-spring-coordinate-d{d}-trial-1"
    )
    pair(axes[col], (t - release) * 1000, -u, -s)
    axes[col].set_xlim(0, 60)
    axes[col].set_xlabel("Time since delivered release (ms)")
    axes[col].set_ylabel("Background exposed (points)")
    axes[col].set_title(f"First 60 ms after a {d}-point pull")
fig.suptitle(
    "Part 3: early release residuals remain visible at actual scale", fontsize=15
)
fig.savefig(args.output / "early-release-detail.png", dpi=170)
