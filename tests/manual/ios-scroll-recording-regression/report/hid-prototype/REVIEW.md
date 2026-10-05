<!-- cspell:ignore UIKit HID NaN CMake xcresult -->
# Review Follow-Up

## Launch Direction and Motionless Animations

The direction-disagreement example is mathematically valid, but a blanket direction guard fails native parity.
Two phone captures delivered a reversal whose pan and scroll estimates had opposing signs.
UIKit coasted 67.0 and 66.7 points in the older direction.
The proposed guard left Slint stationary in both.
That counterexample is retained, and the direction guard is removed.
The final policy permits that measured UIKit behavior.
Timestamp-related mismatches remain; permitting a launch does not prove full reversal parity.

Native launches at or below the simulation's ten-point stopping speed are rejected before creating an in-bounds animation.
This uses the simulation's shared constant rather than duplicating it.
The check considers the effective launch after carried momentum, so a carried launch that moves is still eligible.

## Platform Scope and Gate Tests

The native iOS tracker policy is now selected by its type.
Linux and embedded builds select the original policy.
The non-iOS policy neither redistributes missing weights nor computes the unused pan blend.
Its one- and two-segment regression estimates remain 20 and 160 pt/s for constant 400 pt/s input.

Every tracker sets its own threshold estimate.
The shared platform-dependent accessor is removed.
The `can_flick` predicate used by `animate` is also exercised on CI hosts with the explicit native iOS policy.
Tests cover a native-accepted low-scroll-speed flick, the recorded sparse flick, opposing directions, stopped launches, and carried launches.
The full Release core suite passes all 408 tests.
The no-default-features `unsafe-single-threaded,libm` configuration also compiles.

## Diagnostic Safety and Cost

- HID `x`, `y`, and other floating fields convert non-finite values to JSON `null`.
  Serialization failures are caught and counted rather than escaping through the HID handler.
- A NaN/infinity control record is emitted by the diagnostic app.
  Its captured JSON contains `null` values, and the phone runs report zero serialization errors.
- Only `HID_TRACE=1` enables HID capture.
  The separate Rust environment parser is removed.
- The new public Winit callback and `input-tracing` feature are removed entirely.
  The backend matches the base branch, so there is no additional feature to expose through CMake.
- The macOS tracker calculates its blend once.
- The native-only forwarding flag is cached when the recognizer is created.
  HID packets are copied during capture; decoding, base64 encoding, and JSON serialization run on a serial worker queue.
  UIKit state is still sampled on its owning thread.
  File saving flushes the queue after the capture, outside the gesture path.
- The historical report now puts its two sentences on separate Markdown lines.

## Device Evidence

The initial reviewed build passed four short-flick and decelerating capture checks and four safety-profile capture checks.
The short-flick cases remained native-accepted and Slint-accepted.
The first reversal profile delivered near-zero launch speeds rather than the intended opposite-direction launch; both views stayed still.
The adjusted reversal profile supplied the native counterexample described above.
Requested trajectories are therefore never treated as proof of delivered segment speeds.

The final build passed six capture checks, including both native-accepted short flicks.
Their post-release travel was 78.667/77.859 points for UIKit/Slint in trial 1 and 78.000/78.026 in trial 2.
The final reversal captures still exposed residual input-time differences: UIKit coasted in both, while Slint coasted in one.
These capture checks validate recording and the short-flick regression; they do not assert complete reversal or travel parity.

The HID recorder uses private iOS APIs only in the opt-in manual diagnostic app.
Raw CSV, HID JSONL, and `.xcresult` evidence remains local under `output/ios-pr9-review-2026-10-05`.
Timestamp forwarding, pan-entry matching, and full curve parity remain outside this prototype's verified result.
