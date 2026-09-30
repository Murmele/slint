#!/usr/bin/env python3
# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT

"""Run screen swipes, retain evidence, and report delivery separately from parity."""

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

from analyze_trace import evaluate, read_trace

PACKAGE = "dev.slint.aospscrollcomparison"


def save_results(output, density, results, require_parity):
    (output / "results.json").write_text(json.dumps({"density": density, "results": results}, indent=2))
    delivery_ok = all(result["delivery_passed"] for result in results)
    parity_ok = all(result["parity_passed"] for result in results)
    return 0 if delivery_ok and (parity_ok or not require_parity) else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--require-parity", action="store_true")
    parser.add_argument("--analyze-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.analyze_only:
        saved = json.loads((args.output / "results.json").read_text())
        results = []
        for previous in saved["results"]:
            folder = args.output / f"{previous['case']}-{previous['trial']}"
            result = {key: previous[key] for key in ("case", "trial", "requested_duration_ms")}
            try:
                result.update(evaluate(read_trace(folder / "trace.csv"),
                                       (folder / "device.log").read_text(), saved["density"]))
                result["delivery_passed"] = True
                result["parity_passed"] = all(result["parity"].values())
            except ValueError as error:
                result.update(delivery_passed=False, parity_passed=False, error=str(error))
            results.append(result)
            print(f"{result['case']}-{result['trial']}: delivery={result['delivery_passed']} parity={result['parity_passed']}")
        return save_results(args.output, saved["density"], results, args.require_parity)

    def adb(*arguments):
        return subprocess.check_output(["adb", "-s", args.serial, *arguments])

    density_text = adb("shell", "wm", "density").decode()
    density = int(re.findall(r"(?:Physical|Override) density: (\d+)", density_text)[-1]) / 160
    size = re.findall(r"(?:Physical|Override) size: (\d+)x(\d+)", adb("shell", "wm", "size").decode())[-1]
    width, height = map(int, size)
    results = []
    for name, distance_dp, requested_ms in (("slow", 120, 800), ("short-hard", 120, 80), ("long-fast", 360, 180)):
        for trial in range(1, args.repeats + 1):
            folder = args.output / f"{name}-{trial}"
            folder.mkdir(exist_ok=True)
            adb("shell", "am", "force-stop", PACKAGE)
            adb("shell", "am", "start", "-n", f"{PACKAGE}/android.app.NativeActivity", "--ei", "recording_tail_ms", "4000")
            time.sleep(1.2)
            pid = adb("shell", "pidof", PACKAGE).decode().strip()
            x, y = width // 2, int(height * 0.72)
            adb("shell", "input", "swipe", str(x), str(y), str(x), str(y - round(distance_dp * density)), str(requested_ms))
            time.sleep(4.5)
            log = adb("logcat", "-d", "--pid=" + pid).decode(errors="replace")
            (folder / "device.log").write_text(log)
            (folder / "screen.png").write_bytes(adb("exec-out", "screencap", "-p"))
            files = re.findall(r"TRACE_FILE,([^\s]+\.csv)", log)
            result = {"case": name, "trial": trial, "requested_duration_ms": requested_ms}
            try:
                if len(files) != 1:
                    raise ValueError("Expected exactly one recording file for this process")
                adb("pull", files[0], str(folder / "trace.csv"))
                result.update(evaluate(read_trace(folder / "trace.csv"), log, density))
                result["delivery_passed"] = True
                result["parity_passed"] = all(result["parity"].values())
            except (ValueError, subprocess.CalledProcessError) as error:
                result.update(delivery_passed=False, parity_passed=False, error=str(error))
            results.append(result)
            print(f"{name}-{trial}: delivery={result['delivery_passed']} parity={result['parity_passed']}", flush=True)
    return save_results(args.output, density, results, args.require_parity)


if __name__ == "__main__":
    raise SystemExit(main())
