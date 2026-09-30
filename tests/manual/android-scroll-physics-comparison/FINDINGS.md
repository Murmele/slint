<!-- Copyright © SixtyFPS GmbH <info@slint.dev> -->
<!-- SPDX-License-Identifier: MIT -->

# Why Slint Master and AOSP Scrolling Differ

Date: September 30, 2026.
Slint base: `4e05af780806a06889f0effaad407949eb8a644d`.
Device: Samsung Galaxy A34, Android 16.
Build: Release with Material styling and Skia.
Scope: master only.

## Confirmed Causes

### Historical Input Arrives but the Velocity Tracker Ignores It

The Android backend forwards native event times and per-pointer historical positions.
The comparison bridge does the same for copied `MotionEvent` objects.
Slint's touch state preserves this information in its input events.

Master's `Flickable` matches `MouseEvent::Moved { position, .. }`.
It records current position deltas using `current_tick()` and a five-entry velocity buffer.
It does not consume the supplied timestamp or historical positions.
Callback timing can differ from native sample timing.
The five current movements can omit intermediate acceleration or reversals.

Available data and data used by the estimator are different claims.
The manual recording did not directly capture Slint's computed launch estimate.
It cannot quantify each mechanism's contribution.
The improved app adds that diagnostic.

### The Deceleration Models Differ

Master uses constant deceleration of `2000` logical pixels per second squared.
Speed decreases approximately linearly to zero or a boundary.
The reference uses AOSP's spline calculation, with a different speed decay and stopping trajectory.
Equal launch velocity cannot make these simulations agree.

Sources in this checkout:

- `internal/core/items/flickable.rs`: `handle_mouse`, `animate`, and `DECELERATION`.
- `internal/core/items/flickable/data_ringbuffer.rs`: `mean_velocity`.
- `internal/core/animations/simulations/constant_deceleration.rs`: `step_internal`.
- [Pinned AOSP OverScroller](https://android.googlesource.com/platform/frameworks/base/+/99b01a65cc4c104933788b3143285ab6bae65827/core/java/android/widget/OverScroller.java).

## Manual Recording Results

The user performed 11 single-finger gestures after correcting row geometry.
The CSV contains 629 current touch samples and 596 historical samples.
The median display observation interval was approximately 8.33 ms.
Slint positions were sampled every 8 ms.
Charts derive speed from position changes over 50 ms intervals.

| Gesture | AOSP travel | Slint travel | AOSP last movement | Slint last movement |
|---|---:|---:|---:|---:|
| 2: long rapid gesture | 6313 dp | 7645 dp | 2.416 s | 2.769 s |
| 4: short flick | 186 dp | 98 dp | 0.525 s | 0.312 s |
| 9: hard reverse flick | 2213 dp | 1481 dp | 1.541 s | 1.220 s |
| 10: short flick | 125 dp | 41 dp | 0.440 s | 0.203 s |
| 11: final flick | 159 dp | 144 dp | 0.491 s | 0.386 s |

Travel values are magnitudes measured after release.
Times are seconds after release, based on the last observed position change.
Sampling and physical-pixel quantization limit timing precision.
The final flick has relatively similar travel, but Slint stops approximately 105 ms earlier.
The long gesture shows the opposite duration relationship.
Different initial velocity and different decay both contribute.
No time or distance is scaled to percentages.

The retained capture and plots are under `output/android-aosp-recording-2026-09-30` in the original workspace.
They are historical evidence; the runner produces fresh evidence for each revision.

## Harness Error Corrected

Native rows rounded every 56 dp height to 158 physical pixels at the phone's 2.8125 scale factor.
Slint retained 157.5 pixels per row.
This accumulated approximately 50 pixels of alignment error by row 100.
The corrected app rounds cumulative row boundaries instead.
The initial offset difference is approximately 0.18 dp, or half a physical pixel.
Native text font padding is disabled to align labels.
This was a harness error, not a physics difference.

## Unresolved Behavior and Scope

The long gesture produced approximately 56 dp of separation before release while the finger remained down.
Post-release simulation cannot explain that separation.
Recognition displacement, delivery, coordinate conversion, and timing need a focused drag investigation.
Replaying history as additional drag displacement would double-count motion.

The reference recognizer and velocity tracker come from the installed Samsung framework.
Only its fling simulation is a pinned AOSP copy.
This app has not established that Samsung's tracker is identical to AOSP's tracker.
The diagnostic bridge preserves Java's millisecond event timestamps; it does not preserve sub-millisecond native precision.
It does not prove complete AOSP widget equivalence.

Android 16 AOSP normally uses a second-degree least-squares tracker for X/Y.
It skips resampled samples and clears velocity after a movement gap greater than 40 ms at release.
`ScrollView` also clamps velocity, selects the active pointer, applies a minimum threshold, and reverses the sign for content movement.
Exact velocity parity requires those inputs and policies.
[AOSP tracker](https://android.googlesource.com/platform/frameworks/native/+/refs/heads/android16-release/libs/input/VelocityTracker.cpp),
[AOSP ScrollView](https://android.googlesource.com/platform/frameworks/base/+/99b01a65cc4c104933788b3143285ab6bae65827/core/java/android/widget/ScrollView.java).

## Automated Evidence

The improved harness records input after event-loop forwarding and logs Slint's actual release estimate.
It tests slow, short hard, and long fast gestures twice each.
Delivery checks run before comparisons of velocity, travel, and stopping time.
The runner retains screenshots, logs, CSVs, and machine-readable results for every case.
Use `--require-parity` to make mismatches fail the command.
Keep parity failures visible while improving master.
A passing delivery campaign does not establish physics parity.

## Automated Device Results

The September 30 campaign passed delivery validation in all six runs.
All six also passed the 10% release-velocity comparison.
Both slow cases passed all parity tolerances.
Both short hard cases failed travel and position-curve parity.
Both long fast cases additionally failed stopping-time parity.
`--require-parity` exited with status 1 when rechecking the retained evidence.

| Case | Native release speed | Slint release speed | AOSP travel | Slint travel |
|---|---:|---:|---:|---:|
| Slow, trial 1 | 150.0 dp/s | 150.4 dp/s | 7.1 dp | 7.1 dp |
| Slow, trial 2 | 150.0 dp/s | 153.2 dp/s | 7.1 dp | 8.4 dp |
| Short hard, trial 1 | 1502.2 dp/s | 1493.5 dp/s | 393.6 dp | 570.1 dp |
| Short hard, trial 2 | 1501.9 dp/s | 1491.0 dp/s | 393.6 dp | 568.2 dp |
| Long fast, trial 1 | 1998.9 dp/s | 2011.7 dp/s | 646.8 dp | 1028.4 dp |
| Long fast, trial 2 | 1998.9 dp/s | 2013.9 dp/s | 646.8 dp | 1030.6 dp |

These are measured release estimates, not requested automation speeds.
Between 8 and 93 historical samples per run reached the forwarding bridge intact.
Short hard and long fast launch estimates differ by less than 1%, but travel differs by approximately 45% and 59%.
This directly demonstrates the simulation mismatch for these gestures.
It does not prove that launch estimates match for other paths or rapid reversals.
The six verifier unit tests also passed, including five checks that reject invalid captures.
Full device evidence is retained locally under `/private/tmp/slint-aosp-auto-results`.

## Next Changes to Validate

1. Consume native timestamps and history in master's velocity tracker.
2. Compare a pinned AOSP tracker and Slint using identical samples, including pauses and reversals.
3. Feed equal launch velocities into both simulations to isolate trajectory differences.
4. Adapt Android's simulation once the intended model is established by tests.
5. Diagnose finger-down separation independently.
