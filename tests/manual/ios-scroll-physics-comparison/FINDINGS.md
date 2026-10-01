<!-- Copyright © SixtyFPS GmbH <info@slint.dev> -->
<!-- SPDX-License-Identifier: MIT -->

# UIKit and Slint: Three-Part Physics Report

October 1, 2026. Physical iPhone 13 Pro Max, iOS 27.0, Release, Cupertino style, Winit/Skia.
Source baseline: Murmele/slint `mm/flickable-scroll-animation-v2`, commit `5e0f6d10f14857cc4adc8aedda56b91ec65cb24f`.
Both views measure 408 × 774 points and have 400 × 72000-point content with 72-point rows.
The new automated position captures have a median interval near 8.335 ms, approximately 120 Hz.
Every chart uses actual point distances and elapsed time, without normalization.

**Status:** the pull mapping matches closely on the tested paths.
The spring candidate improves the return but still fails the matching criterion.
Immediate pan entry remains unmatched.
These are opt-in diagnostic code changes, not a production parity fix.

## Part 1: Before Changes

Slint subtracts an 8-point threshold, then applies overscroll friction to each event delta according to the current displayed exposure.
A first movement crossing the boundary can pass through unresisted.
Different batching of the same total movement can therefore produce different exposure.

UIKit consumed 10 points on explicitly held paths; Slint consumed 8.
Immediate UIKit paths consumed 10–15.333 points in earlier captures.
This measures discarded list movement, not a universal recognizer threshold.

Recognition was observed before the pan action reset the translation baseline.
Apple documents that the `began` action runs in the next run-loop cycle.
[Apple: UIGestureRecognizer.State.began](https://developer.apple.com/documentation/uikit/uigesturerecognizer/state-swift.enum/began).
Disabling Slint touch forwarding did not eliminate UIKit's additional discarded movement.

![Earlier manual pull before the physics changes](report/figures/manual-before-changes.png)

That earlier real-finger capture ran at 60 Hz.
Its peak return gap was 45.418 points, with settling within 0.5 points after about 0.642 seconds for UIKit and 0.742 seconds for Slint.
It is separate from the later 120 Hz automated captures.

## Part 2: Fixing the Pull

The candidate uses a 10-point threshold and an absolute rubber-band mapping:

```text
exposure = 0.55 × distance × viewport / (viewport + 0.55 × distance)
```

The coefficient was proposed from the 200-point capture.
The 50- and 600-point paths were checks outside that calibration distance.
Each event inverts the current exposure, adds the finger delta in the underlying drag coordinate, and reapplies the mapping.
A unit test verifies batching independence and reversals at both bounds.

| Pull | UIKit peak | Modified Slint peak | Absolute gap |
| ---: | ---: | ---: | ---: |
| 50 pt | 21.333 pt | 21.392 pt | 0.059 pt |
| 200 pt | 92.000 pt | 92.069 pt | 0.069 pt |
| 600 pt | 228.667 pt | 228.642 pt | 0.025 pt |

![Improved pulls with the original spring](report/figures/modified-pull-and-return.png)

The 10-point threshold removed the held 40-point path's 2-point gap in both repeats, including zero sampled contact separation.
Immediate paths still diverged.
No mode reads UIKit positions to drive Slint.

## Part 3: The Return Animation

The original spring operates on displayed exposure, with mass 0.5, stiffness 100, damping ratio 1.1, and zero initial velocity.
The candidate evolves spring travel in the underlying drag coordinate and maps that travel back to the display.
An empirical initial-return rate of 2.4422646 per second was calibrated from the 200-point trace.
This is a candidate black-box model, not a claim about UIKit private code.

| Pull | Original spring maximum gap | Candidate maximum gap |
| ---: | ---: | ---: |
| 50 pt | 2.549 pt | 1.167 pt |
| 200 pt | 10.269 pt | 2.458 pt |
| 600 pt | 40.177 pt | 7.760 pt |

![Return animation before and after the spring change](report/figures/spring-before-after.png)

Three unseen distances were each repeated twice:

| Pull | Repeat 1 maximum gap | Repeat 2 maximum gap |
| ---: | ---: | ---: |
| 100 pt | 1.894 pt | 1.201 pt |
| 300 pt | 4.016 pt | 3.764 pt |
| 450 pt | 7.197 pt | 6.969 pt |

![Independent validation of the spring candidate](report/figures/spring-holdouts.png)

The predeclared criterion was at most 0.5 points throughout return in every complete trace.
The candidate fails it.
It is an improvement, not a solved spring.

A second round records animation-clock age and compares the same spring started from current backend time against the previous animation tick.
Both variants passed their phone gesture-delivery checks.
The clock results and a polished PDF will be added in a follow-up commit.

### Validation and Evidence

The first experiment round contains 18 complete pan traces and 18 complete pull traces.
Delivered distances and stationary holds were checked from the actual events.
The spring unit tests and rubber-band batching/reversal test passed.
Green XCTest results establish gesture delivery and settling, not physics parity.
A first inconsistent threshold implementation failed its motion assertion and was corrected before these comparisons.

- [Pan aggregate results](report/evidence/pan-summary.csv).
- [Pull aggregate results](report/evidence/pull-summary.csv).
- [Written predictions](report/evidence/PREDICTIONS.md).
- [Capture validation](report/evidence/validation.json), including the failed spring criterion.
- [Build and selected-test instructions](README.md).

The published evidence contains charts and per-gesture aggregates.
Raw per-event touch CSVs and `.xcresult` bundles remain local.
For a full match, pan dispatch, release velocity, spring timing, boundary transitions, and carried momentum still need independent validation.
This campaign does not establish parity for bottom-bound flings, interruptions, multitouch, or carried momentum.
