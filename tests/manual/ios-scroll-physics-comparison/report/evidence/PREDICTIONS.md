# Predictions Before the Code Experiment

Source baseline: Murmele/slint `mm/flickable-scroll-animation-v2`, commit `5e0f6d10f1`.
The Release app runs three modes in separate processes with identical recorder settings.
No mode reads UIKit content offsets or recognizer translations to drive Slint.

1. Baseline mode retains the original 8-point threshold and incremental overscroll friction.
2. Threshold-only mode uses 10 points on iOS.
   It should remove the two-point final drag gap on explicitly held 40-point paths.
   It should leave a gap on some immediate paths where UIKit resets its baseline later.
3. Rubber-band mode uses the 10-point threshold and an invertible absolute-distance overscroll mapping.
   The proposed mapping is exposure = 0.55 × distance × viewport / (viewport + 0.55 × distance).
   The 0.55 coefficient comes from the prior 200-point phone pull and its observed approximately 92-point exposure.
   The 50- and 600-point pulls are held-out checks of this prediction, not inputs to that coefficient.
   Peak exposure should be within one point of UIKit when the two sides discard the same starting distance.
   Drag sampling density should no longer change the mathematical mapping for a fixed uncompressed distance.
4. The release spring is unchanged.
   Therefore, even a matching pull exposure does not predict a matching bounce-return curve.

Pan cases: immediate sparse 40-point, immediate dense 40-point, and explicitly held dense 40-point, twice in each mode.
Pull cases: 50, 200, and 600 points with a stationary hold before release, once per mode.
Delivered data, not requested timing, determine whether a trace supports each prediction.
Retain every raw CSV and failed prediction.

## Spring Coordinate Experiment

The candidate evolves spring travel in the uncompressed drag coordinate, then rubber-bands that travel before updating the displayed position.
The mass, stiffness, and damping ratio remain 0.5, 100, and 1.1.
An empirical initial-return coefficient, 2.4422646 per second, is calibrated from the earlier 200-point trace.
The initial raw-coordinate velocity includes the inverse rubber-band compression factor.
This is a candidate black-box model; it is not a claim about UIKit private code.
No time shifts or per-distance parameters are used in the running implementation.

The existing captured 50- and 600-point curves provide an offline cross-check.
The new 100-, 300-, and 450-point captures are unseen validation paths, each repeated twice.
The 50-, 200-, and 600-point paths run once with the candidate, for a total of nine new phone captures.
The candidate predicts substantially smaller return error, but the offline replay still has early-frame residuals.
Do not call the spring matched unless the maximum gap is at most 0.5 points throughout return in every complete trace.
Retain failures and separate improvement from a complete match.

## Second Round: Release Clock

The first spring candidate still shows an early return gap, including 7.76 points on the 600-point pull.
The second round logs the difference between the current backend clock and the animation tick in every input row.
It compares that candidate against the same model started from the current backend clock.
The spring coefficients and nonlinear mapping do not change.
Both variants run the 200- and 600-point paths twice.
The hypothesis is that a stale animation tick contributes to the early release error.
A positive measured clock age is required evidence for that hypothesis; changing the clock must improve the recorded curve to justify keeping it.
Both early and later return errors remain visible, without shifting recorded traces.

## Third Round: Return Curves for Fitting

This round records UIKit only, to fit spring-back models offline from `return-curves.csv`.
Two candidates are compared:

1. A linear spring on the displayed exposure.
   Stiffness, damping, and a starting velocity that depends on the exposure at release are fitted.
2. The spring-coordinate candidate, refitted: a spring on the raw drag distance, mapped through the rubber-band curve.

Held pulls cover 25–700 points at viewport lengths 774 and 387 points.
Moving releases cover 100, 300, and 600 points at 400 and 1,200 points per second, without a hold.
Every case runs three times.

The fit uses held pulls of 50, 100, 200, 300, 600, and 700 points.
Held pulls of 25, 150, 400, and 500 points and all moving releases are validation paths.
Candidate 1 predicts that the same exposure at release returns identically at both viewport lengths.
Candidate 2 predicts that the shorter viewport returns differently, because its rubber-band curve differs.
Neither candidate is matched unless the maximum gap stays at most 0.5 points in every validation trace.
