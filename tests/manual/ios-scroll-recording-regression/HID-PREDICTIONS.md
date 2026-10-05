<!-- cspell:ignore HID UIKit -->
# HID Release-Gate Predictions

These predictions precede the four release-gate captures.
They use the six earlier HID captures and the original manual touch recording.

The measured pan velocity matches an 80/20 blend of the two latest primary movement segment velocities.
The scroll-release velocity matches a 60/35/5 blend of the latest three primary movement segment velocities.
Missing weights are provisionally assigned to the oldest available segment.
Historical samples within a coalesced batch are not additional primary movements in this model.

Two competing gates remain:

- Pan gate: deceleration starts when the measured pan speed reaches 250 pt/s.
- Scroll gate: deceleration starts when the weighted scroll-release speed reaches 250 pt/s.

The accelerating profile aims for pan speed above the boundary and scroll speed below it.
The decelerating profile aims for pan speed below the boundary and scroll speed above it.
Each runs twice in a fresh view.
Classify these cells by delivered primary HID samples, not requested trajectory speeds.
If the delivered speeds do not straddle the boundary, that cell is inconclusive.

The exact-hold captures also predict retained native velocity when no new movement samples arrive.
The one-pixel jitter captures predict a below-threshold native velocity after newer movement samples replace the older ones.
The previous six captures support that distinction; they do not establish behavior for every hold duration.
