<!-- Copyright © SixtyFPS GmbH <info@slint.dev> -->
<!-- SPDX-License-Identifier: MIT -->

# UIKit and Slint scroll physics comparison

This manual iOS harness superimposes a translucent native `UIScrollView` over a
Slint `ScrollView`.
A passive gesture recognizer forwards the original `UITouch` objects and
`UIEvent` to Slint's underlying UIKit view.
Both implementations therefore receive the same event objects, coordinates,
and timestamps.

A live overlay shows each scroll offset, their point and percentage difference,
each frame velocity, the velocity difference, and the maximum offset separation.
The UI test target also records frame-by-frame CSV traces for speed sweeps,
boundary behavior, interruption, reversal, and rapid repeated flicks.

`testShortHardFlickRetainsReleaseMomentum` uses XCTest's public gesture API to
move 120 points at a requested 6,400 points per second.
It repeats the gesture three times and records a known expected failure when
Slint travels less than half UIKit's settled distance.

The rapid-flick helper uses private XCTest event-synthesis classes.
Its cases use 75–350 ms between lifting one touch and beginning the next.
Each timing case runs three times to expose launch-velocity instability.
Use this project only for local diagnostics.

## Setup

1. Install [XcodeGen](https://github.com/yonaskolb/XcodeGen).
2. Run `xcodegen generate` in this directory.
3. Open `NativeSlintScroll.xcodeproj` and select a development team for the app
   and UI test targets.
4. Choose an attached iPhone and run the `NativeSlintScroll` scheme in Release.

The Xcode build phase calls the repository's
`scripts/build_for_ios_with_cargo.bash` script. The Cargo dependencies use
paths relative to the repository, so the harness does not depend on any
temporary checkout location.

See [FINDINGS.md](FINDINGS.md) for the measurements collected on the original
iPhone 13 Pro Max investigation.

## Capturing Return Curves

`testReturnCurveHeldPulls` and `testReturnCurveMovingReleases` record UIKit's return after a pull from the top edge.
Slint receives no touches in these tests, so they check only UIKit.
They run at two viewport lengths, set through `VIEWPORT_HEIGHT`, so a fit can separate pull distance from viewport length.
Each case repeats three times; the full run launches the app about 100 times and takes about 15 minutes.

1. Run both tests in Release on the attached iPhone:

   ```sh
   xcodebuild test -project NativeSlintScroll.xcodeproj -scheme NativeSlintScroll \
       -configuration Release -destination "platform=iOS,id=$DEVICE_ID" \
       -only-testing:NativeSlintScrollUITests/ScrollComparisonTests/testReturnCurveHeldPulls \
       -only-testing:NativeSlintScrollUITests/ScrollComparisonTests/testReturnCurveMovingReleases
   ```

   Prefix the command with `TEST_RUNNER_RETURN_CURVE_REPEATS=1` for a quick smoke run.
2. Copy the app's `Documents` folder from the phone:

   ```sh
   xcrun devicectl device copy from --device "$DEVICE_ID" \
       --domain-type appDataContainer --domain-identifier dev.slint.native-scroll-prototype \
       --source Documents --destination captures
   ```

3. Extract the return curves:

   ```sh
   python3 extract_return_curves.py captures report/evidence/return-curves.csv
   ```

   The script prints one line per trace, with exposure at release, peak, release velocity, and settle time.
   Check that every case appears before committing the CSV.
4. Commit only `report/evidence/return-curves.csv` to the branch you tested, and push it.
   Put the device model, iOS version, and tested commit in the commit message.
   List any failed or missing cases there too, instead of rerunning only the passing ones.
   Leave `captures/` and `.xcresult` bundles out; `.gitignore` excludes `captures/`.
   Don't change the fit and validation split in `report/evidence/PREDICTIONS.md`.
