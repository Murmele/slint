#!/usr/bin/env python3
# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT

"""Extracts UIKit return curves from the app's Documents folder into one CSV.

Usage: extract_return_curves.py DOCUMENTS_DIR OUTPUT_CSV

Reads every `scroll-return-*.csv` written by `testReturnCurveHeldPulls` and
`testReturnCurveMovingReleases`, with its `input-*.csv` and `geometry-*.json`.
Times are seconds since the release callback.
Exposure is how far the content is past the top edge, in points.
"""

import csv
import json
import re
import sys
from pathlib import Path

SCENARIO = re.compile(
    r"return-vp(?P<viewport>\d+)-d(?P<distance>\d+)-speed(?P<speed>\d+)"
    r"-hold(?P<hold>\d+)-trial-(?P<trial>\d+)$"
)
# UITouch.Phase.ended
TOUCH_PHASE_ENDED = 3
WINDOW_BEFORE_RELEASE = 0.1
WINDOW_AFTER_RELEASE = 1.5
SETTLED_EXPOSURE = 0.5

COLUMNS = [
    "scenario",
    "viewport_length",
    "requested_viewport",
    "distance",
    "speed",
    "hold_ms",
    "trial",
    "release_pan_velocity_y",
    "time",
    "target_time",
    "uikit_exposure",
]


def release_event(input_path):
    with input_path.open(newline="") as file:
        for row in csv.DictReader(file):
            if (
                row["event_type"] == "touch_callback"
                and int(row["touch_phase"]) == TOUCH_PHASE_ENDED
            ):
                return float(row["callback_time"]), float(row["pan_velocity_y"])
    return None


def settle_time(samples):
    settled = None
    for time, exposure in samples:
        if time < 0:
            continue
        if abs(exposure) > SETTLED_EXPOSURE:
            settled = None
        elif settled is None:
            settled = time
    return settled


def extract(documents, writer):
    count = 0
    for scroll_path in sorted(documents.glob("scroll-return-*.csv")):
        scenario = scroll_path.stem.removeprefix("scroll-")
        match = SCENARIO.match(scenario)
        if not match:
            print(f"skipping {scroll_path.name}: unknown scenario name", file=sys.stderr)
            continue
        input_path = documents / f"input-{scenario}.csv"
        geometry_path = documents / f"geometry-{scenario}.json"
        if not input_path.exists() or not geometry_path.exists():
            print(f"skipping {scenario}: missing input trace or geometry", file=sys.stderr)
            continue
        release = release_event(input_path)
        if release is None:
            print(f"skipping {scenario}: no release in the input trace", file=sys.stderr)
            continue
        release_time, release_velocity = release
        viewport_length = json.loads(geometry_path.read_text())["uikit_viewport"][3]

        samples = []
        with scroll_path.open(newline="") as file:
            for row in csv.DictReader(file):
                time = float(row["callback_time"]) - release_time
                if not -WINDOW_BEFORE_RELEASE <= time <= WINDOW_AFTER_RELEASE:
                    continue
                target_time = float(row["display_target_time"]) - release_time
                exposure = -float(row["uikit_offset"])
                samples.append((time, exposure))
                writer.writerow(
                    [
                        scenario,
                        f"{viewport_length:.3f}",
                        match["viewport"],
                        match["distance"],
                        match["speed"],
                        match["hold"],
                        match["trial"],
                        f"{release_velocity:.3f}",
                        f"{time:.6f}",
                        f"{target_time:.6f}",
                        f"{exposure:.3f}",
                    ]
                )
        if not samples:
            print(f"skipping {scenario}: no samples around the release", file=sys.stderr)
            continue
        at_release = min(samples, key=lambda sample: abs(sample[0]))[1]
        peak = max(exposure for _, exposure in samples)
        settled = settle_time(samples)
        settled_text = f"{settled:.3f} s" if settled is not None else "not settled"
        print(
            f"{scenario}: viewport {viewport_length:.1f}, exposure at release {at_release:.3f}, "
            f"peak {peak:.3f}, release pan velocity {release_velocity:.1f}, settled {settled_text}"
        )
        count += 1
    return count


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    documents = Path(sys.argv[1])
    output = Path(sys.argv[2])
    with output.open("w", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(COLUMNS)
        count = extract(documents, writer)
    print(f"wrote {count} return curves to {output}")
    if count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
