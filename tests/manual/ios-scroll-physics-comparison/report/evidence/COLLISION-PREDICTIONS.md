# Fling into the bottom boundary

Use 25 rows, each 72 points high, with item 10 at the top (initial offset 648 points).
The bottom boundary is derived from the actual content and viewport geometry saved with each trace.
An upward 200-point finger path leaves content inside the boundary at release on both tested screens.
The finger lifts immediately after motion; no held overscroll is part of these tests.

Run velocity settings 1000, 1500, 2200, 3000, and 4500 twice each.
These settings are intended to reach the bottom through free deceleration after release.
The 400 setting is a negative control intended to stop inside the list, twice.
Classify actual delivered finger, release, and impact speeds in points per second, not by the setting.

Verify equal content sizes and viewport sizes before considering a comparison valid.
Verify initial offsets of 648 points and a complete press/move/release sequence.
Reject collision classification if either list is already outside its bounds while the finger is down.
A valid gesture that makes UIKit hit the boundary while Slint misses is a behavior mismatch, not a delivery failure.

Record first boundary crossing, speed in the final 50 ms before impact, peak overscroll and its time,
return-to-boundary time, and settling within 0.5 points.
Retain the free-flight and bounce curves together on actual time and offset axes.
Every graph has one common origin at the delivered release.
Annotate each measured impact without shifting either list's curve to align impacts.

Slint's current `spring-coordinate` mode changes pan entry and pulling outside the bounds.
An in-bounds fling and its natural collision use the branch's existing FlickAnimation path.
This campaign does not alter that path or copy UIKit positions or velocities into Slint.

## Corrected direction: fling into the top boundary

The first campaign interpreted the requested boundary as the bottom.
The user clarified that the target is the start of the list.
Keep those results separate; they do not answer the top-boundary question.

Start at offset 648 points with the full 1000-row list.
Move the finger downward 200 points and release immediately.
The two lists must remain above offset zero throughout contact and at release.
Use the same six velocity settings and two repeats in fresh app launches.
The 400 setting is expected to stop inside; higher settings are intended to hit offset zero after release.
Treat a higher setting that does not hit as an observed no-hit outcome, never as an automatic delivery failure.
Measure impact speed, exposure, time to peak, time to return, and time to settle.
Plot both actual offsets against a common release clock.
The exposure detail may reverse the sign of offset to display positive background exposure, but must not rescale time or distance.
