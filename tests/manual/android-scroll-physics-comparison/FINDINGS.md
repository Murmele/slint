<!-- Copyright © SixtyFPS GmbH <info@slint.dev> -->
<!-- SPDX-License-Identifier: MIT -->

# Murmele Android Scrolling Compared With AOSP

## Tested Revision and Setup

Date: September 30, 2026.
Repository: [Murmele/slint](https://github.com/Murmele/slint/tree/mm/flickable-scroll-animation-v2).
Branch: `mm/flickable-scroll-animation-v2`.
Upstream commit: `bdbec1e4372d2d13f0782fc1bcea5aa6bffcfac7`.
Local comparison harness: `406a18d41a299d46d7a75c2bddd6eb4c58b122f2`.
Device: Samsung Galaxy A34, model SM-A346B, Android 16.
Density: 2.8125 physical pixels per dp.
Build: Release, Material style, Skia renderer.

The harness forwards the same current and historical touch samples to Slint and the native reference.
Both lists start at row 100, with an initial offset difference of 0.18 dp.
The reference fling uses a bundled Android 16 AOSP `OverScroller`, with friction fixed to `0.015`.
Its recognizer and `VelocityTracker` use the installed Samsung framework.
This is an AOSP trajectory comparison, not a complete AOSP widget port.
See [AOSP-PROVENANCE.md](AOSP-PROVENANCE.md).

Murmele's estimator and physics are unchanged.
The core instrumentation only logs the release estimate behind `SLINT_SCROLL_DIAGNOSTICS=1`.

## Screen Test Results

The campaign ran three gesture cases twice each, starting a fresh app process for every run.
All six delivery checks passed, including preservation of native timestamps, current samples, historical samples, and coordinate translation.
Every run exercised history: 7–95 historical samples reached the forwarding bridge.
Both lists moved in every run.
The six verifier unit tests also passed.

Requested distance and duration identify each case; release speeds below come from measured estimates.
The cases were slow (120 dp / 800 ms), short hard (120 dp / 80 ms), and long fast (360 dp / 180 ms).

| Case | Repeat | AOSP release speed (dp/s) | Slint release speed (dp/s) | AOSP post-release travel (dp) | Slint post-release travel (dp) | Result |
|---|---:|---:|---:|---:|---:|---|
| Slow | 1 | 150.0 | 129.4 | 7.1 | 6.1 | Release-speed comparison failed |
| Slow | 2 | 150.0 | 159.4 | 7.1 | 9.4 | All tolerances passed |
| Short hard | 1 | 1501.9 | 1532.7 | 393.6 | 419.4 | All tolerances passed |
| Short hard | 2 | 1502.2 | 1523.0 | 393.6 | 415.4 | All tolerances passed |
| Long fast | 1 | 1998.9 | 2022.0 | 646.8 | 675.4 | All tolerances passed |
| Long fast | 2 | 1998.9 | 1944.3 | 646.8 | 632.7 | All tolerances passed |

Five of six runs passed all comparison tolerances.
The strict `--require-parity` campaign returned status 1 because slow repeat 1 failed the release-speed comparison.
The failure remains in the retained results.

## Remaining Differences

### Release Estimates Are Close for Fast Flicks but Vary at Low Speed

The four faster runs differ from native release speed by 1.2–2.7%.
The slow runs differ by -13.8% and +6.2% despite native estimates of 150.0 dp/s in both.
Two repeats do not establish how often the low-speed difference occurs.

### Coordinate Truncation and Recency Weighting Reproduce the Estimate Error

An offline replay reconstructed Slint's last 20 samples from the retained current and historical touch records.
It applied integer coordinate truncation, density conversion, the 100 ms horizon, and the source's exponentially weighted quadratic fit.
The replay reproduced all six logged estimates within 0.002 dp/s.
This ties the launch mismatch to the estimator's inputs and weighting, rather than a different fling curve.

| Case | Repeat | Logged Slint (dp/s) | Replayed truncated, weighted fit (dp/s) | Fractional coordinates, weighted fit (dp/s) | Fractional coordinates, uniform fit (dp/s) |
|---|---:|---:|---:|---:|---:|
| Slow | 1 | 129.398 | 129.397 | 146.978 | 149.935 |
| Slow | 2 | 159.378 | 159.378 | 152.627 | 150.367 |
| Short hard | 1 | 1532.739 | 1532.739 | 1522.412 | 1491.459 |
| Short hard | 2 | 1522.950 | 1522.950 | 1529.642 | 1499.587 |
| Long fast | 1 | 2022.017 | 2022.016 | 2040.779 | 1997.890 |
| Long fast | 2 | 1944.255 | 1944.254 | 1944.151 | 1987.746 |

The production Android backend and comparison bridge both truncate floating-point touch coordinates to physical integers before converting to logical coordinates.
The estimator weights each sample with `0.5^(age / half_life)`, where `half_life` is the sample window's span divided by 14.
A 100 ms window therefore has a half-life of about 7 ms.
Recent quantization and timestamp irregularities have much more influence than older samples.

For slow repeat 1, retaining fractional coordinates changes the weighted estimate from 129.4 to 147.0 dp/s.
Removing recency weighting as well gives 149.9 dp/s, versus the native estimate of 150.0 dp/s.
For long fast repeat 2, retaining fractional coordinates barely changes the estimate; the weighting accounts for most of the difference in this replay.
Neither factor alone explains every case.
The uniform fractional-coordinate fits are within 0.7% of the native estimates across these six runs.
This is an observed counterfactual, not proof that the device's tracker uses exactly that implementation.

Sources:

- `internal/backends/android-activity/androidwindowadapter.rs`: `pointer_logical_position`.
- `internal/backends/android-activity/javahelper.rs`: `callback_forward_touch`.
- `internal/core/items/flickable/velocity_tracker/general.rs`: `estimate_velocity_internal` and `RECENCY_HALF_LIFE_DIVISOR`.
- `internal/core/items/flickable/velocity_tracker/least_square.rs`: `solve_weighted`.

### Travel and Timing Still Differ

The short hard flicks travel 5.6–6.6% farther in Slint after release.
The long fast flicks differ by +4.4% and -2.2%.
Slint's last recorded movement occurs 0–34 ms later across these six runs.

| Case | Repeat | AOSP last movement after release (ms) | Slint last movement after release (ms) | Maximum post-release displacement difference (dp) |
|---|---:|---:|---:|---:|
| Slow | 1 | 114 | 139 | 1.5 |
| Slow | 2 | 120 | 153 | 2.8 |
| Short hard | 1 | 738 | 772 | 25.8 |
| Short hard | 2 | 738 | 763 | 27.7 |
| Long fast | 1 | 914 | 939 | 38.5 |
| Long fast | 2 | 912 | 912 | 38.2 |

### The Source Spline Explains the Actual Slint Fling

Slint's velocity-driven Android simulation uses its portable AOSP spline implementation.
Replaying that spline with each logged Slint velocity reproduced its sampled animation with a maximum per-run RMS error of 0.049 dp.
The largest individual residual was 0.23 dp.
The fitted start-clock offset was at most 0.1 ms relative to consumed release.
The replay did not scale distance or duration.
The displayed native/Slint charts retain their original absolute positions and observation times.

| Case | Repeat | Source-predicted Slint fling distance (dp) | Native distance from its fling callback (dp) | Source-predicted Slint duration (ms) |
|---|---:|---:|---:|---:|
| Slow | 1 | 5 | 7.1 | 123 |
| Slow | 2 | 8 | 7.1 | 143 |
| Short hard | 1 | 407 | 393.6 | 760 |
| Short hard | 2 | 403 | 393.6 | 756 |
| Long fast | 1 | 659 | 646.8 | 932 |
| Long fast | 2 | 616 | 646.8 | 905 |

The Slint start position implied by its final offset and source-predicted fling distance agrees with the native fling start within 0.015 dp in every run.
This and the curve replay explain the final separation through differing release estimates and distance quantization.
Slint truncates total distance to an integer logical pixel; AOSP truncates to an integer physical pixel.
That introduces a smaller discrepancy even with equal logical release speeds.
These runs provide no evidence of an additional large spline-shape error at the tested speeds.

Sources: `internal/core/animations/simulations/android.rs` and `internal/core/animations/simulations/android/spline.rs`.

### The Runner's Travel Baseline Includes Pending Drag Movement

The runner takes its baseline from the last display-frame observation before the native release callback.
That frame can precede Slint's last drag update.
The reported post-release travel therefore includes pending drag displacement in addition to the fling.
For short hard repeat 1, the runner reports 419.4 dp, whereas the source predicts a 407 dp fling.
The remaining 12.4 dp is consistent with the outstanding drag movement at its baseline.
Long fast repeat 1 similarly reports 675.4 dp for a 659 dp fling.

The existing results remain unchanged so this limitation stays visible.
Future travel assertions should record each simulation's actual start offset rather than rely on a pre-release frame.
Reported last-movement times also combine simulation duration, observation delay, and coordinate quantization.
They are not exact animation-completion timestamps.

### The Observed Lists Also Separate Before Release

The following values compare absolute sampled positions, preserving any difference already present when the finger lifts.
A positive final difference means Slint finished farther down the list.

| Case | Repeat | Maximum observed separation before release (dp) | Final Slint minus AOSP offset (dp) |
|---|---:|---:|---:|
| Slow | 1 | 1.4 | -2.1 |
| Slow | 2 | 2.5 | +0.9 |
| Short hard | 1 | 32.2 | +13.4 |
| Short hard | 2 | 24.5 | +9.4 |
| Long fast | 1 | 38.9 | +12.2 |
| Long fast | 2 | 29.7 | -30.8 |

The bridge's median queue delay was 0.08–0.23 ms per run, with individual delays up to 7.45 ms.
Of 235 native offset changes during contact, 232 had a later Slint sample within one physical pixel of the same offset.
Those matching observations lagged by a median of 4.0–6.1 ms per run, and at most 16.2 ms.
Some intermediate native positions were skipped by the Slint sampling timer.

The atomic offset shown in the Java frame callback is the last value published by Slint's 8 ms timer.
The native offset is read directly from the native view.
This asymmetry and the asynchronous bridge can produce a temporary gap while both positions follow the same finger movement.
The matching offset records and aligned fling start positions support latency as the main explanation for separation in these straight swipes.
They do not establish the visible presentation time of either renderer or settle rapid-reversal behavior.
The original charts are not shifted to hide this delay.

## What Passing Means

The existing comparison allows 10% release-speed error and 50 ms difference in the last recorded movement.
Travel and post-release displacement curves allow 10% of native travel or 5 dp, whichever is larger.
These are harness tolerances, not Android specifications.
Passing them does not establish a one-to-one match.

Frame observations have a median interval of approximately 8.32 ms, or 120 Hz.
Slint publishes its sampled offset through an 8 ms timer; native offset changes are also recorded independently.
Native integer-pixel offsets and Slint's floating-point offsets have different quantization.
Timing and instantaneous separation have these measurement limits.
Java touch timestamps retain millisecond precision.
The comparison charts do not rescale time or distance, or shift one side to overlap the other.

## Evidence and Next Questions

The [retained evidence](evidence/murmele-galaxy-a34-2026-09-30/README.md) includes all six compressed CSVs, release log excerpts, results, build metadata, diagnosis, and absolute-position charts.
The [offline replay](scripts/replay_diagnosis.py) reconstructs estimator ablations and the source curve without a phone.
See [README.md](README.md#replay-the-recorded-diagnosis) for the command.
The replay checks require matching release estimates within 0.01 dp/s, inferred start alignment within 0.02 dp, and spline RMS error below 0.06 dp.
All six passed.

Full device logs, screenshots, the deployed APK, and the chart generator remain in the original workspace's `output/android-aosp-murmele-2026-09-30` directory.

The next focused changes to validate are preserving fractional touch coordinates, choosing an Android estimator from identical delivered samples, and recording exact simulation starts.
Renderer presentation timing needs separate instrumentation if transient visible separation remains after correcting the observer.
This campaign did not test rapid reversals, repeated flicks, boundaries, maximum speed, or the minimum-fling threshold.
It makes no conclusions about those behaviors or about iOS.
