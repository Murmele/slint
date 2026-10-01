# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT
# cspell:ignore interp

import argparse
import csv, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument(
    "--csv",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "evidence/return-curves.csv",
)
parser.add_argument(
    "--output",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "evidence/held-model-comparison.json",
)
args = parser.parse_args()
p = args.csv
groups = defaultdict(list)
with p.open() as source:
    for r in csv.DictReader(source):
        groups[r["scenario"]].append(r)
cases = []
for name, rows in groups.items():
    if int(rows[0]["hold_ms"]) != 400:
        continue
    ts = np.array([float(r["time"]) for r in rows])
    ys = np.array([float(r["uikit_exposure"]) for r in rows])
    post = ts >= 0
    cases.append(
        {
            "name": name,
            "distance": int(rows[0]["distance"]),
            "viewport": float(rows[0]["viewport_length"]),
            "x0": float(np.interp(0, ts, ys)),
            "t": ts[post],
            "y": ys[post],
        }
    )
fit = [r for r in cases if r["distance"] in [50, 100, 200, 300, 600, 700]]
validation = [r for r in cases if r["distance"] in [25, 150, 400, 500]]


def basis(t, omega, zeta):
    if zeta == 1:
        e = np.exp(-omega * t)
        return (1 + omega * t) * e, t * e
    d = math.sqrt(zeta * zeta - 1)
    r1 = omega * (-zeta + d)
    r2 = omega * (-zeta - d)
    a = np.exp(r1 * t)
    b = np.exp(r2 * t)
    return (-r2 * a + r1 * b) / (r1 - r2), (a - b) / (r1 - r2)


T = np.concatenate([r["t"] for r in fit])
X = np.concatenate([np.full(len(r["t"]), r["x0"]) for r in fit])
Y = np.concatenate([r["y"] for r in fit])
best = None
for omega in np.arange(8, 30.01, 0.5):
    for zeta in np.arange(1, 2.001, 0.05):
        f, g = basis(T, float(omega), float(zeta))
        a = X * f
        b = X * g
        beta = float(np.clip(np.dot(b, a - Y) / np.dot(b, b), 0, 15))
        rms = float(np.sqrt(np.mean((a - beta * b - Y) ** 2)))
        if best is None or rms < best["fit_rms_pt"]:
            best = {
                "omega": float(omega),
                "zeta": float(zeta),
                "beta": beta,
                "fit_rms_pt": rms,
            }
print("Shared displayed-coordinate model fitted on", len(fit), "curves:", best)
output = {
    "parameters": best,
    "fit_count": len(fit),
    "validation_count": len(validation),
    "curves": [],
}
for r in cases:
    f, g = basis(r["t"], best["omega"], best["zeta"])
    linear = r["x0"] * (f - best["beta"] * g)
    f0, g0 = basis(r["t"], math.sqrt(200), 1.1)
    compression = 1 - r["x0"] / r["viewport"]
    raw = r["x0"] / (0.55 * compression)
    remaining = raw * (f0 - 2.4422646 / compression * g0)
    travel = np.clip(raw - remaining, 0, raw)
    current = r["x0"] - 0.55 * travel * r["viewport"] / (r["viewport"] + 0.55 * travel)
    record = {
        "scenario": r["name"],
        "distance": r["distance"],
        "viewport": r["viewport"],
        "validation": r["distance"] in [25, 150, 400, 500],
    }
    for label, prediction in [("linear", linear), ("current_candidate", current)]:
        errors = prediction - r["y"]
        record[label] = {
            "rms_pt": float(np.sqrt(np.mean(errors**2))),
            "max_gap_pt": float(np.max(abs(errors))),
        }
    output["curves"].append(record)
for label in ["current_candidate", "linear"]:
    for subset in [False, True]:
        rows = [r for r in output["curves"] if r["validation"] == subset]
        print(
            label,
            "validation" if subset else "fit",
            "mean RMS",
            np.mean([r[label]["rms_pt"] for r in rows]),
            "max gap range",
            min(r[label]["max_gap_pt"] for r in rows),
            max(r[label]["max_gap_pt"] for r in rows),
            "within .5",
            sum(r[label]["max_gap_pt"] <= 0.5 for r in rows),
            "/",
            len(rows),
        )
args.output.write_text(json.dumps(output, indent=2) + "\n")
