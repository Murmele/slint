# Release momentum and distance controls

The matrix compares 100- and 600-point pulls at automation velocity settings of 400 and 1600.
Each path either releases immediately or remains at its endpoint for 400 ms before release.
Run every condition twice on the simulator and twice on the physical phone, in Release.
Use the current `spring-coordinate` candidate for Slint; no spring constants change during this matrix.
The UIKit reference remains a plain scroll view with normal deceleration.

Predictions precede these runs:

- Moving release carries outward velocity into UIKit's bounce, producing extra post-release exposure.
- The stopped path substantially reduces that extra exposure.
- Slint's current spring-back constructor ignores outward release velocity, so it does not reproduce that extra motion.
- Speed differences after a real stop may disappear; if they remain, distinguish retained input history from changed spring parameters.
- Different absolute settling times at different distances do not prove different parameters.
  A fixed spring can take longer to reach the same absolute position tolerance from a larger displacement.

Validate complete press/move/release delivery and the actual distance for every trace.
Measure delivered motion speed from distinct timestamped touch samples, not from the request.
Measure the actual stop interval and retain the pan recognizer's reported release velocity separately.
An old cached recognizer velocity is not proof of continued finger movement.
Log native content changes and both position curves at the display-link rate, with actual callback times.

Measure post-release extra exposure, time of peak, settling time, and the full position curve.
Require delivered stopped paths to remain within 0.5 points over their final 350 ms.
Require immediate releases to retain a measurable moving segment close to release.
Exclude delivery failures from physics conclusions; keep their evidence.
Do not shift curves, stretch time, or rescale distance to force agreement.
No per-distance or per-speed spring parameters are introduced from these measurements.

## Delivery correction and quiet-stop follow-up

The original dense private path did not deliver the intended timing.
The public press/drag/hold path replaced it after a separate delivery check; the failed original traces remain local.
Its exact 400 ms stationary hold did not clear UIKit's cached pan velocity, contrary to the initial stopped-path prediction.
That failed prediction is retained above.
Before the quiet-stop follow-up, the stated control was a one-physical-pixel slow finish to refresh the native velocity estimate.
It is a near-stationary control, not proof that a perfectly motionless synthetic hold has the same release state as a human pause.
