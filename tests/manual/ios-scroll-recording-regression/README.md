<!-- cspell:ignore XCTest xcodegen xcresult UDID Matplotlib -->
# Recorded iOS Scroll Regression

This standalone app compares a plain UIKit scroll view with Slint using the same delivered touches.
It turns the manual short-flick and settling observations into native-reference assertions.
See [the measured report](report/REPORT.md) for baseline and latest-engine results.

## Cases and Assertions

`testRecordedFlickAndSettlingParity` runs four vertical replay profiles twice each.
The profiles derive from gestures 9, 10, 8, and 13 in the October 5 recording.
Each case starts a fresh app at offset 7,200 points, away from either boundary.
The existing fixture forwards the delivered UIKit touches to Slint.

- UIKit must coast more than five points, otherwise delivery is inconclusive.
- Slint must also coast more than five points.
- Signed post-release travel must agree within five points.
- For the two tail profiles, settling times must agree within 150 ms at both 0.1 and one point from final rest.
- Samples must have no gap above 30 ms, and both lists must be stationary during the final 200 ms.

These are regression guards, not a claim that errors below those limits constitute exact UIKit parity.
Failures remain ordinary XCTest failures; they are not marked as expected failures.
The measured result is attached to the test and saved alongside the raw traces.

`testFullRecordedSequenceParity` adds the recorded two-dimensional paths and all between-gesture gaps.
It starts at offset zero and runs the complete 13-gesture sequence.
The test checks the two original no-coasting cases and the two uninterrupted tail examples.
It does not fabricate historical `UITouch` samples.
XCTest may resample the trajectory, so delivered events must be checked before claiming faithful reproduction.

The vertical and full-sequence fixtures contain relative times and screen-local coordinates.
Raw touch identifiers and absolute device clocks remain local.

## Run on a Device

Install Xcode, XcodeGen, Rust, and the `aarch64-apple-ios` Rust target.
Generate the project in this directory:

```sh
xcodegen generate
```

Run only these tests in Release, replacing the device and signing-team placeholders:

```sh
SLINT_STYLE=cupertino SLINT_BACKEND=winit-skia xcodebuild test \
  -project NativeSlintScroll.xcodeproj -scheme NativeSlintScroll \
  -configuration Release -destination 'platform=iOS,id=DEVICE_UDID' \
  DEVELOPMENT_TEAM=YOUR_TEAM -parallel-testing-enabled NO \
  -only-testing:NativeSlintScrollUITests/ScrollComparisonTests/testRecordedFlickAndSettlingParity \
  -only-testing:NativeSlintScrollUITests/ScrollComparisonTests/testFullRecordedSequenceParity \
  -resultBundlePath /private/tmp/recorded-scroll-regression.xcresult
```

The Cargo dependencies and build script point to this checkout's engine.
The plist enables ProMotion; the recording sampler requests up to 120 Hz.
The generated Xcode project and raw recordings are ignored.

## Analyze Captures

Copy each scenario's `input-*.csv`, `scroll-*.csv`, `geometry-*.json`, and `regression-*.json` into a run's `raw` directory.
Add `metadata.json` with the exact `engine_commit` tested.
Use Python with NumPy and Matplotlib:

```sh
python3 report/scripts/analyze.py \
  --baseline /path/to/baseline --latest /path/to/latest --output report
```

The script checks delivered gestures, geometry, sample gaps, and final rest.
It exports relative-time position data and compares the measured outcomes.
Raw input and `.xcresult` bundles are not part of the published evidence.
