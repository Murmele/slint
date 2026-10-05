# Second Review Follow-Up

## Correctness Changes

The normal Winit build no longer substitutes dispatch-time `Instant::now()` for missing touch capture timestamps.
Queued events can arrive close together after a stall, so that substitution can produce extreme velocities.
The capture-time dependency proposal remains separate and the corresponding experiment remains historical evidence.
The ordinary build doesn't claim capture-time accuracy.

Momentum retention now records supplied input times for press and move events.
It compares those with subsequent input times at the 100 ms retention boundary.
The press sample in the velocity buffer already used the supplied timestamp; that part of the review's first-segment claim wasn't correct.
Animation time remains separate from input bookkeeping.

## Policy and Logging Cleanup

- Native iOS has its own tracker instead of a const-generic policy used by every platform.
- Linux and embedded keep a separate legacy tracker with their original sparse-sample and expiry behavior.
- Common velocity estimates no longer contain native gate and minimum-speed fields.
- A release policy is computed once and its axis-aware `can_flick` derives the gate internally.
  The effective carried launch remains an explicit input and finite checks remain.
- Frame logging and its direct dependencies are removed from the renderer and diagnostic app.

The opposing-direction launch remains supported.
Measured UIKit segments near `[-439.92, +300, +300]` pt/s produce a +300 pt/s pan estimate and a -143.95 pt/s scroll estimate.
UIKit reported +144 pt/s in content-offset coordinates and coasted 67 points in the older direction.
The capture-time Slint experiment coasted 66.918 points.
A blanket sign guard rejects this native behavior.

## Validation and Pending Items

The 53 focused Flickable regressions pass.
They include same-tick burst handling, stationary-sample rejection, non-iOS policy preservation, and the input-time momentum boundary.
The iOS Release build compiles.

Two focused phone captures tested exact holds without intervening movement samples.
The delivered touch timestamps show holds of 299.954 ms and 2008.333 ms.
UIKit coasted 242.667 and 261.667 points respectively.
Its release delegate and deceleration outcome are retained with the lower-level traces.
Slint coasted 261.032 and 260.003 points respectively; the remaining travel errors are not classified as parity.
Both captures passed delivery checks with one touch, no HID serialization errors, and frame gaps below 30 ms.
A two-second cutoff would contradict the measured native behavior.
The result supports retention through two seconds, not an empirical claim about every possible hold duration.
No arbitrary longer timeout was introduced.

The generated-data archive is prepared locally at `/private/tmp/pr9-redacted-scroll-evidence-2026-10-05.tar.gz`.
It is 145,853 bytes with SHA-256 `afb3f42bedc3e70177b4a1fc0e64f24a55a98f4a9f4c63e04a2aecd5e5fd85cb`.
Automatic approval review rejected its public release upload pending explicit authorization.
Bulk generated traces are removed from the current PR tip.
The [original public snapshot](https://github.com/Murmele/slint/tree/3028c50cc90ea724a102d1a4a2b5b540e85b2a62/tests/manual/ios-scroll-recording-regression/report) remains available while external hosting awaits approval.
This is a source-tree cleanup; earlier Git objects remain until final squash/merge handling.
The standalone executable workspace's lockfile remains for reproducibility.
