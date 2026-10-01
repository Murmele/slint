# Simulator spring alternatives

These predictions precede the simulator run.
The phone is unavailable and is excluded from this campaign.
Use the booted iPhone 18 Pro Simulator, iOS 27.0, in Release.

Compare each candidate against `spring-coordinate` with 200- and 600-point pulls, twice each.
Use each capture's own UIKit reference, actual callback time, and unscaled points.
Measure RMS error over the first 0.8 seconds after the delivered release, and maximum return error.
Require both lists to move and settle within 0.5 points.
A candidate improves consistently only if its RMS decreases in both repeats at both distances.
The full return matches only if every measured return gap stays within 0.5 points.

1. `spring-runloop`: defer Slint release forwarding to the next main run-loop turn.
   If release ordering causes the early gap, this reduces the first 60 ms gap and total RMS.
   Log the actual forwarding time; do not subtract the delay from the graph.
2. `spring-zero-velocity`: remove the fitted initial return velocity in the raw-coordinate spring.
   This should reduce the initial movement but slow the later return.
   It improves only if the complete measured curve improves, including the tail.
3. `spring-history`: deliver UIKit sample times and coalesced positions directly to Slint's internal touch event.
   This diagnostic bypasses Winit and refreshes the animation clock before delivery.
   A held pull should have little release momentum, so history alone is unlikely to correct the spring shape.
   Any improvement requires a later direct-dispatch control before attribution to history alone.

Keep negative results.
No candidate reads the native content offset to drive Slint.
Simulator results do not establish physical-phone parity.
