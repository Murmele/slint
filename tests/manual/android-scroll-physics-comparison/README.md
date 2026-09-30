<!-- Copyright © SixtyFPS GmbH <info@slint.dev> -->
<!-- SPDX-License-Identifier: MIT -->

# Murmele Slint and AOSP Scroll Comparison

Compare Murmele's `mm/flickable-scroll-animation-v2` scrolling against a bundled Android 16 AOSP `OverScroller` on the same screen.
The translucent reference forwards current and historical touch samples to Slint.
Both lists start at row 100, using cumulative row boundaries to avoid rounding drift.

The reference's fling trajectory uses AOSP with friction fixed to `0.015`.
Touch recognition and its velocity tracker use the installed Android framework.
This is an AOSP trajectory comparison, not a complete AOSP widget port.
Edge effects are disabled.
See [AOSP-PROVENANCE.md](AOSP-PROVENANCE.md) and the current device results in [FINDINGS.md](FINDINGS.md).

## Build and Run

Configure `ANDROID_HOME`, `ANDROID_NDK_HOME`, and a compatible `JAVA_HOME`.
Install the `aarch64-linux-android` Rust target and `cargo-apk`.

```sh
cd tests/manual/android-scroll-physics-comparison
SLINT_STYLE=material SLINT_SCROLL_DIAGNOSTICS=1 \
  CARGO_APK_RELEASE_KEYSTORE="$HOME/.android/debug.keystore" \
  CARGO_APK_RELEASE_KEYSTORE_PASSWORD=android \
  cargo apk build --release
adb -s "$ADB_SERIAL" install -r <reported-apk-path>
adb -s "$ADB_SERIAL" shell am start \
  -n dev.slint.aospscrollcomparison/android.app.NativeActivity
```

`SLINT_SCROLL_DIAGNOSTICS=1` enables a compile-time log of Slint's release estimate.
It does not change the estimator or simulation.

## Manual Recording

Swipe normally and wait 15 seconds after the last release.
CSV files are stored in the app's external files directory under `scroll-traces`.
Logcat reports each path with `TRACE_FILE`.

The CSV includes current and historical touches, samples consumed by the forwarding bridge, AOSP offset changes, and Slint samples.
Slint is sampled every 8 ms, with both positions also recorded at display-frame cadence.
Visible metrics update at 10 Hz.
Writes are buffered and flushed approximately once per second.

`time_ns` is observation time from `System.nanoTime()`.
`frame_time_ns` is the display callback timestamp.
`event_time_ms` retains the native touch timestamp.
Positions ending in `_dp` are logical distances; touch coordinates ending in `_px` are physical pixels.
The verifier checks the constant coordinate translation into Slint's window.

## Automated Screen Tests

```sh
python3 scripts/test_trace_checks.py
python3 scripts/run_tests.py --serial "$ADB_SERIAL" --output /tmp/aosp-screen-tests
python3 scripts/run_tests.py --serial "$ADB_SERIAL" --output /tmp/aosp-parity-tests --require-parity
```

The campaign performs slow, short hard, and long fast screen swipes, with two repeats each.
Requested distances and durations identify cases; they do not establish delivered velocity.
Every case saves a CSV, device log, screenshot, and measured results.

Delivery checks require a complete single-finger gesture and equal forwarded sample counts.
They reject changed timestamps, changed actions, and inconsistent coordinate translation.
They require initial alignment within 1 dp, visible movement on both sides, and at least two seconds of settled tail evidence.
Each case must record one native fling velocity and one Slint release estimate.

Parity checks compare measured release velocity within 10%, travel within 10% or 5 dp, and stopping time within 50 ms.
They also compare the post-release position curves at shared observation times within the travel tolerance.
The comparison uses actual elapsed time and dp, without duration or distance rescaling.
These are desired comparison tolerances, not Android specifications.
The default command fails on invalid delivery and reports parity separately.
`--require-parity` also fails on any parity mismatch.
A passing delivery test does not establish physics parity.
Use `--analyze-only` with the same output directory to recheck saved evidence without rerunning phone gestures.

Negative verifier tests reject lost history, changed timestamps, corrupted coordinates, initial misalignment, and a stationary Slint list.
The scripts accept an emulator serial for CI.
This branch does not configure or claim a passing GitHub workflow.
