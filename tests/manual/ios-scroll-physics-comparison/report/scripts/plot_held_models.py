# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT
# cspell:ignore axhline axhspan axisbelow fontsize fontweight gridspec interp labelsize sharex suptitle textcoords titlesize wspace xlabel xlim xticks xytext ylabel ylim zorder

import argparse
import csv, json, math
from pathlib import Path
from collections import defaultdict
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser()
parser.add_argument(
    "--csv",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "evidence/return-curves.csv",
)
parser.add_argument(
    "--fit",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "evidence/held-model-comparison.json",
)
parser.add_argument(
    "--output", type=Path, default=Path(__file__).resolve().parents[1] / "figures"
)
args = parser.parse_args()
base = args.output
base.mkdir(parents=True, exist_ok=True)
results = json.loads(args.fit.read_text())
params = results["parameters"]
validation = [r for r in results["curves"] if r["validation"]]
selected = [
    max(validation, key=lambda r: r["current_candidate"]["max_gap_pt"]),
    max(validation, key=lambda r: r["linear"]["max_gap_pt"]),
    max(
        (r for r in validation if r["distance"] == 150),
        key=lambda r: r["linear"]["max_gap_pt"] - r["current_candidate"]["max_gap_pt"],
    ),
]
groups = defaultdict(list)
with args.csv.open() as f:
    for row in csv.DictReader(f):
        groups[row["scenario"]].append(row)


def basis(t, omega, zeta):
    d = math.sqrt(zeta * zeta - 1)
    r1 = omega * (-zeta + d)
    r2 = omega * (-zeta - d)
    a = np.exp(r1 * t)
    b = np.exp(r2 * t)
    return (-r2 * a + r1 * b) / (r1 - r2), (a - b) / (r1 - r2)


def replay(record):
    raw = groups[record["scenario"]]
    ts = np.array([float(r["time"]) for r in raw])
    ys = np.array([float(r["uikit_exposure"]) for r in raw])
    x0 = float(np.interp(0, ts, ys))
    post = ts >= 0
    t = ts[post]
    y = ys[post]
    f, g = basis(t, params["omega"], params["zeta"])
    linear = x0 * (f - params["beta"] * g)
    f, g = basis(t, math.sqrt(200), 1.1)
    vp = record["viewport"]
    compression = 1 - x0 / vp
    initial = x0 / (0.55 * compression)
    remaining = initial * (f - 2.4422646 / compression * g)
    travel = np.clip(initial - remaining, 0, initial)
    current = x0 - 0.55 * travel * vp / (vp + 0.55 * travel)
    for key, pred in [("current_candidate", current), ("linear", linear)]:
        assert abs(float(np.max(abs(pred - y))) - record[key]["max_gap_pt"]) < 1e-9
    return t, y, current, linear


plt.rcParams.update(
    {
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "legend.fontsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)
red = "#c53228"
blue = "#165db0"
green = "#16836a"
fig, axes = plt.subplots(
    2, 3, figsize=(16, 9), gridspec_kw={"height_ratios": [1.6, 1]}, sharex=True
)
fig.subplots_adjust(
    top=0.745, bottom=0.17, left=0.06, right=0.985, wspace=0.25, hspace=0.32
)
fig.suptitle(
    "Held-pull return: measured UIKit versus two model predictions",
    x=0.06,
    y=0.97,
    ha="left",
    fontsize=20,
    fontweight="bold",
)
fig.text(
    0.06,
    0.924,
    "13.1 → 5.0 pt is the worst error across 24 validation curves — the maxima occur in different cases.",
    fontsize=13,
)
fig.text(
    0.06,
    0.892,
    "Actual points and seconds since delivered release. No time shifts or distance normalization.",
    fontsize=11,
    color="#475569",
)
fig.text(
    0.06,
    0.861,
    "UIKit is measured. Both models start at its release exposure; blue and green are offline predictions, not new device runs.",
    fontsize=11,
    color="#475569",
)
labels = [
    "Case with the largest current-model error",
    "Case with the largest alternative-model error",
    "Smaller pull where the alternative gets worse",
]
for column, (record, label) in enumerate(zip(selected, labels)):
    t, y, current, alternative = replay(record)
    ax = axes[0, column]
    er = axes[1, column]
    ax.plot(t, y, color=red, lw=2.4, label="UIKit — measured")
    ax.plot(
        t, current, color=blue, lw=2, ls="--", label="Current Slint candidate — replay"
    )
    ax.plot(
        t,
        alternative,
        color=green,
        lw=2,
        ls="-.",
        label="Alternative spring — prediction",
    )
    before = record["current_candidate"]["max_gap_pt"]
    after = record["linear"]["max_gap_pt"]
    ax.set_title(
        f"{label}\n{record['distance']} pt pull · {record['viewport']:.0f} pt viewport · repeat 1\nMaximum gap: {before:.2f} → {after:.2f} pt",
        loc="left",
        pad=12,
    )
    ax.set_ylabel("Background exposure (points)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.18)
    ax.legend(loc="upper right")
    er.axhspan(-0.5, 0.5, color="#e5e7eb", alpha=0.9, label="±0.5 pt matching band")
    er.axhline(0, color=red, lw=1.6, label="UIKit reference = 0")
    er.plot(t, current - y, color=blue, ls="--", lw=2, label="Current model − UIKit")
    er.plot(t, alternative - y, color=green, ls="-.", lw=2, label="Alternative − UIKit")
    er.set_ylabel("Position error (points)")
    er.set_xlabel("Time since release (seconds)")
    er.set_xlim(0, 0.8)
    er.grid(alpha=0.18)
    if column == 0:
        er.legend(loc="upper right", fontsize=8)
    for predicted, color in [(current, blue), (alternative, green)]:
        error = predicted - y
        idx = int(np.argmax(abs(error)))
        er.scatter(t[idx], error[idx], color=color, s=32, zorder=5)
fig.text(
    0.06,
    0.083,
    "Shared alternative fitted only to 36 training curves; these cases belong to the 24 held-out validation curves.",
    fontsize=11,
)
fig.text(
    0.06,
    0.054,
    "Errors are checked over the full recorded 0–1.5 s after release; the chart shows the first 0.8 s. All 24 validation curves still fail ±0.5 pt.",
    fontsize=10,
    color="#475569",
)
fig.savefig(base / "held-return-model-comparison.png", dpi=180)


rows = sorted(validation, key=lambda r: (r["distance"], r["viewport"], r["scenario"]))
fig, ax = plt.subplots(figsize=(15, 6.8))
fig.subplots_adjust(left=0.06, right=0.985, top=0.79, bottom=0.25)
x = np.arange(len(rows))
ax.bar(
    x - 0.18,
    [r["current_candidate"]["max_gap_pt"] for r in rows],
    width=0.36,
    color=blue,
    label="Current Slint candidate — replay",
)
ax.bar(
    x + 0.18,
    [r["linear"]["max_gap_pt"] for r in rows],
    width=0.36,
    color=green,
    label="Alternative spring — prediction",
)
ax.axhline(0.5, color=red, lw=1.6, ls=":", label="Required maximum gap: 0.5 pt")
ax.set_xticks(
    x,
    [
        f"{r['distance']} / {r['viewport']:.0f} / {r['scenario'].split('-')[-1]}"
        for r in rows
    ],
    rotation=60,
    ha="right",
)
ax.set_ylabel("Maximum absolute position error (points)")
ax.set_ylim(0, 14.5)
ax.grid(axis="y", alpha=0.18)
ax.set_axisbelow(True)
ax.legend(loc="upper left")
for key, offset, color in [("current_candidate", -0.18, blue), ("linear", 0.18, green)]:
    index = max(range(len(rows)), key=lambda i: rows[i][key]["max_gap_pt"])
    value = rows[index][key]["max_gap_pt"]
    ax.annotate(
        f"{value:.2f} pt",
        xy=(index + offset, value),
        xytext=(0, 9),
        textcoords="offset points",
        ha="center",
        color=color,
        fontweight="bold",
    )
fig.suptitle(
    "All 24 held-pull validation curves: smaller worst error, mixed improvements",
    x=0.06,
    y=0.97,
    ha="left",
    fontsize=19,
    fontweight="bold",
)
fig.text(
    0.06,
    0.919,
    "The largest error falls from 13.11 to 4.98 pt. The alternative worsens many smaller-pull cases.",
    fontsize=12,
)
fig.text(
    0.06,
    0.883,
    "Actual error over 0–1.5 seconds since release. No per-case refitting, time shifts, or distance normalization.",
    fontsize=11,
    color="#475569",
)
fig.text(
    0.06,
    0.066,
    "Labels: finger path (pt) / actual viewport height (pt) / repeat. UIKit-only recordings; model results are offline predictions.",
    fontsize=11,
    color="#475569",
)
fig.savefig(base / "held-return-validation-errors.png", dpi=180)
print(base / "held-return-model-comparison.png")
print(base / "held-return-validation-errors.png")
