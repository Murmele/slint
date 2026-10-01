<!-- Copyright © SixtyFPS GmbH <info@slint.dev> -->
<!-- SPDX-License-Identifier: MIT -->

# UIKit and Slint Scroll Physics Comparison

The harness overlays a translucent native `UIScrollView` on a Slint `ScrollView`.
A passive recognizer forwards the original touch objects and event to Slint's UIKit host view.
Native viewport and content geometry come from Slint's live inner Flickable geometry.
The native view uses normal deceleration and vertical bounce.

See [the three-part report](FINDINGS.md) and [its PDF](report/REPORT.pdf) for measurements, charts, and unresolved behavior.
The report distinguishes gesture-delivery checks from physics matching.

## Build

Install Xcode, XcodeGen, and the Rust targets `aarch64-apple-ios` and `aarch64-apple-ios-sim`.
From this directory:

```sh
xcodegen generate
SLINT_STYLE=cupertino SLINT_BACKEND=winit-skia xcodebuild -project NativeSlintScroll.xcodeproj -scheme NativeSlintScroll -configuration Release -destination 'generic/platform=iOS' DEVELOPMENT_TEAM="$SCROLL_TEAM_ID" -allowProvisioningUpdates build
```

Set `SCROLL_TEAM_ID` to your signing team.
The project calls the repository's `scripts/build_for_ios_with_cargo.bash` and uses relative Cargo dependency paths.
The plist enables ProMotion display-link hints.
Physical recordings request 120 Hz, capped by the device's maximum, and store actual callback/display timestamps.

## Select an Experiment

Set `SLINT_IOS_SCROLL_EXPERIMENT` in the app's launch environment:

| Value | Behavior |
| --- | --- |
| `baseline` or unset | Original scrolling behavior |
| `threshold10` | 10-point iOS threshold |
| `rubberband10` | Threshold plus absolute rubber-band pull mapping |
| `spring-coordinate` | Pull mapping plus candidate return spring |
| `spring-clock` | Same candidate started from live backend time; a rejected control |
| `spring-runloop` | Failed delivery control: deferred release did not reach Slint; excluded from physics results |
| `spring-zero-velocity` | Raw-coordinate spring without the fitted initial return velocity |
| `spring-history` | Same spring, with a diagnostic direct path preserving UIKit touch times and history |

These modes are diagnostic experiments.
The candidate does not pass the full-curve matching criterion.

Set `INPUT_TRACE=1` for touch/coalesced-event CSVs and `START_OFFSET=0` for the top of both lists.
`SCROLL_ROW_COUNT` optionally sets the list length, from 1 to 1000 rows.
`TRACE_SAVE_DELAY_MS` sets the post-release recording period.
`TRACE_UNIQUE_FILES=1` retains separate recordings for successive gestures.
Recording disables auto-lock while the app is visible.
`NATIVE_ONLY_INPUT=1` keeps UIKit active while disabling forwarding to Slint for a control capture.

## Run Selected Tests

Set `SCROLL_DEVICE_UDID` to your device identifier and run one selected method at a time:

```sh
SLINT_STYLE=cupertino SLINT_BACKEND=winit-skia xcodebuild -project NativeSlintScroll.xcodeproj -scheme NativeSlintScroll -configuration Release -destination "platform=iOS,id=$SCROLL_DEVICE_UDID" DEVELOPMENT_TEAM="$SCROLL_TEAM_ID" -allowProvisioningUpdates -parallel-testing-enabled NO -only-testing:NativeSlintScrollUITests/ScrollComparisonTests/testLocalPanPhysicsExperiment test
```

The current campaign methods are:

- `testLocalPanPhysicsExperiment`: three interior pan paths, two repeats, and three code modes.
- `testLocalOverscrollPhysicsExperiment`: 50-, 200-, and 600-point pulls with threshold-only and rubber-band modes.
- `testLocalSpringPhysicsExperiment`: spring candidate plus repeated unseen 100-, 300-, and 450-point paths.
- `testLocalSpringClockExperiment`: two repeats at 200 and 600 points for each spring clock mode.
- `testLocalSimulatorSpringAlternatives`: current candidate and three alternatives, two repeats at 200 and 600 points.
- `testOverscrollReleaseMomentumMatrix`: 100- and 600-point pulls, two speed settings, immediate or held release, two repeats.
- `testOverscrollQuietReleaseControl`: a one-physical-pixel slow finish to refresh native velocity before release.
- `testFlingIntoTopBoundary`: item 10, downward 200-point flick, six speed settings repeated twice; collision must occur after release.
- `testFlingIntoBottomBoundary`: separate 25-row bottom-boundary diagnostic; it does not answer the top-boundary question.
- `testOverscrollDeliverySmoke`: one controlled pull asserting both views move and return to the top.

Legacy scenario methods remain available for separate campaigns.
Pan and quiet-stop helpers use private XCTest event-synthesis classes for local diagnostics.
Release matrices and free-flight collisions use the public press/drag/hold API.
Its requested velocity setting is not a measured delivered point-per-second speed.
Interior pan probes include an explicit stationary waypoint for an initial hold.
Delivered events determine actual movement and timing; requested automation speed is not treated as a measured speed.

For the simulator, replace the destination with `platform=iOS Simulator,id=$SCROLL_SIMULATOR_UDID` and use `CODE_SIGNING_ALLOWED=NO`.
The tested simulator reported a 60 Hz maximum.
Simulator captures do not establish phone/simulator physics equivalence.

The branch's Winit touch adapter supplies no touch timestamps or history.
The recorder logs these UIKit samples, but they do not reach Slint through normal forwarding.
`spring-history` tests a separate delivery route through the core's internal touch event.
It converts UIKit sample age into the Slint animation clock and refreshes timers before dispatch.
It does not modify Winit, and any improvement requires a separate route/clock control before attribution to history.
Core touch conversion still drops the release timestamp when constructing the pointer release.
This mode therefore does not establish complete release-time preservation.

CSV files are written to the app's Documents directory with the scenario name.
Per-event CSVs are retained locally; the PR contains plots and per-gesture aggregate results.
The final clock monitor records age before forwarding and in subsequent recognizer/content callbacks, which are distinct dispatch stages.

## Analyze Free-Flight Collisions

Copy the scenario's `input-*.csv`, `scroll-*.csv`, and `geometry-*.json` files from the app's Documents directory into a private capture directory.
The analyzer verifies equal geometry, offset 648 at press, a complete 200-point gesture, and both lists inside the boundary throughout contact.
It records no-hit controls, crossing times, measured pre-impact speed, exposure peaks, return times, and settling within 0.5 points.
A missing speed estimate means fewer than three samples were available in its 50 ms fitting window.
A maximum post-release sample gap above 30 ms excludes the trace from numerical conclusions without deleting it.

```sh
python report/scripts/analyze_collisions.py --raw /path/to/top/raw --platform phone --boundary top --output /path/to/analysis
```

Use `--platform simulator` for simulator captures and `--boundary bottom` only for the separate bottom-boundary method.
The full-position chart shows actual offsets.
The top exposure detail reverses the sign of offset so background exposure is positive; no time or distance scale is normalized.
Both use the same delivered release origin, with individual impacts marked without shifting curves.
The 20 Hz comparison uses interpolation of the recorded position samples; capture itself runs at the platform's measured display-link rate.

## Reproduce the Held-Return Model Comparison

The committed `report/evidence/return-curves.csv` comes from the UIKit-only campaign on Murmele's `nigel/ios-uikit-scroll-parity-mm` branch.
It records actual points and seconds, including actual viewport height and reported pan release velocity.
With NumPy and Matplotlib installed, run:

```sh
python report/scripts/fit_held_models.py
python report/scripts/plot_held_models.py
```

The scripts preserve the declared fitting and held-validation distances.
Moving releases are excluded from this displacement-only fit.
The current candidate is replayed without refitting; the displayed-coordinate alternative uses one shared fit.
Both are offline predictions starting from UIKit's measured release exposure.
The report keeps the larger-pull improvements and smaller-pull regressions visible.
