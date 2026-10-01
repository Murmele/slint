// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: MIT
// cspell:ignore usleep XCUI

import XCTest

final class ScrollComparisonTests: XCTestCase {
    private struct ScrollMetrics {
        let uikitOffset: Double
        let slintOffset: Double
    }

    private func launch(
        scenario: String,
        startOffset: Double? = nil,
        fromBottomDistance: Double? = nil,
        inputTrace: Bool = false,
        traceSaveDelayMs: Int = 250,
        nativeOnlyInput: Bool = false,
        physicsVariant: String = "baseline",
        viewportHeight: Double? = nil
    ) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment["SLINT_BACKEND"] = "winit-skia"
        app.launchEnvironment["SCROLL_SCENARIO"] = scenario
        app.launchEnvironment["NATIVE_ONLY_INPUT"] = nativeOnlyInput ? "1" : "0"
        app.launchEnvironment["SLINT_IOS_SCROLL_EXPERIMENT"] = physicsVariant
        if let startOffset {
            app.launchEnvironment["START_OFFSET"] = String(startOffset)
        }
        if let viewportHeight {
            app.launchEnvironment["VIEWPORT_HEIGHT"] = String(viewportHeight)
        }
        if let fromBottomDistance {
            app.launchEnvironment["START_FROM_BOTTOM"] = "1"
            app.launchEnvironment["START_FROM_BOTTOM_DISTANCE"] = String(fromBottomDistance)
        }
        if inputTrace {
            app.launchEnvironment["INPUT_TRACE"] = "1"
            app.launchEnvironment["TRACE_SAVE_DELAY_MS"] = String(traceSaveDelayMs)
        }
        app.launch()
        let metrics = app.staticTexts["Scroll comparison metrics"]
        XCTAssertTrue(metrics.waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Slint"].exists)
        XCTAssertTrue(app.staticTexts["UIKit"].exists)
        return app
    }

    private struct PanProbe {
        let name: String
        let times: [Double]
        let xOffsets: [Double]
        let yOffsets: [Double]

        init(name: String, times: [Double], xOffsets: [Double]? = nil, yOffsets: [Double]) {
            precondition(times.count == yOffsets.count)
            precondition(xOffsets == nil || xOffsets?.count == times.count)
            self.name = name
            self.times = times
            self.xOffsets = xOffsets ?? Array(repeating: 0, count: times.count)
            self.yOffsets = yOffsets
        }
    }

    private func runPanProbe(_ probe: PanProbe, trial: Int, nativeOnlyInput: Bool = false,
                             physicsVariant: String = "baseline") {
        let scenario = "pan-entry-\(probe.name)-trial-\(trial)"
        let app = launch(scenario: scenario, startOffset: 1_000, inputTrace: true,
                         nativeOnlyInput: nativeOnlyInput, physicsVariant: physicsVariant)
        let processID = (app.value(forKey: "processID") as! NSNumber).int32Value
        let frame = app.frame
        let manifest = zip(probe.times, zip(probe.xOffsets, probe.yOffsets))
            .map { point in
                String(format: "%.4f:%.1f:%.1f", point.0, point.1.0, point.1.1)
            }
            .joined(separator: ";")
        XCTContext.runActivity(
            named: "PAN_PROBE_MANIFEST scenario=\(scenario) points=\(manifest)"
        ) { _ in }
        var succeeded = false
        probe.times.withUnsafeBufferPointer { times in
            probe.xOffsets.withUnsafeBufferPointer { xOffsets in
                probe.yOffsets.withUnsafeBufferPointer { yOffsets in
                    succeeded = synthesizePanProbe(
                        processID,
                        frame.width,
                        frame.height,
                        times.baseAddress,
                        xOffsets.baseAddress,
                        yOffsets.baseAddress,
                        Int32(probe.times.count),
                        0.08
                    )
                }
            }
        }
        XCTAssertTrue(succeeded, "Failed to deliver \(scenario)")
        let saved = expectation(description: "Input trace saved")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { saved.fulfill() }
        wait(for: [saved], timeout: 1)
        let metrics = app.staticTexts["Scroll comparison metrics"].value as? String ?? "missing"
        XCTContext.runActivity(named: "PAN_PROBE_RESULT scenario=\(scenario) \(metrics)") { _ in }
        app.terminate()
    }

    private func runPanProbeFamily(_ probes: [PanProbe], repeats: Int = 10) {
        let requestedRepeats = ProcessInfo.processInfo.environment["PAN_PROBE_REPEATS"]
            .flatMap(Int.init) ?? repeats
        for probe in probes {
            for trial in 1...requestedRepeats {
                runPanProbe(probe, trial: trial)
            }
        }
    }

    func testPanEntryCoalescedEvidence() {
        var probes: [PanProbe] = []
        for distance in [24.0, 40.0] {
            for delay in [0.0, 0.08] {
                for count in [2, 16] {
                    let steps = 1...count
                    probes.append(PanProbe(
                        name: "coalescing-d\(Int(distance))-delay\(Int(delay * 1_000))-points\(count)",
                        times: (delay > 0 ? [delay] : []) + steps.map { delay + Double($0) * 0.16 / Double(count) },
                        yOffsets: (delay > 0 ? [0.0] : []) + steps.map { -distance * Double($0) / Double(count) }
                    ))
                }
            }
        }
        runPanProbeFamily(probes, repeats: 1)
    }

    func testPanEntryHeldEvidence() {
        var probes: [PanProbe] = []
        for distance in [24.0, 40.0] {
            for count in [2, 16] {
                let steps = 1...count
                probes.append(PanProbe(
                    name: "held-d\(Int(distance))-delay80-points\(count)",
                    times: [0.08] + steps.map { 0.08 + Double($0) * 0.16 / Double(count) },
                    yOffsets: [0] + steps.map { -distance * Double($0) / Double(count) }
                ))
            }
        }
        runPanProbeFamily(probes, repeats: 1)
    }

    func testPanEntryForwardingControl() {
        for count in [2, 16] {
            for nativeOnly in [false, true] {
                let steps = 1...count
                let probe = PanProbe(
                    name: "forwarding-d40-delay0-points\(count)-nativeOnly\(nativeOnly ? 1 : 0)",
                    times: steps.map { Double($0) * 0.16 / Double(count) },
                    yOffsets: steps.map { -40 * Double($0) / Double(count) }
                )
                runPanProbe(probe, trial: 1, nativeOnlyInput: nativeOnly)
            }
        }
    }

    func testLocalPanPhysicsExperiment() {
        for variant in ["baseline", "threshold10", "rubberband10"] {
            for (delay, count) in [(0.0, 2), (0.0, 16), (0.08, 16)] {
                let steps = 1...count
                let probe = PanProbe(
                    name: "code-\(variant)-d40-delay\(Int(delay * 1000))-points\(count)",
                    times: (delay > 0 ? [delay] : []) + steps.map { delay + Double($0) * 0.16 / Double(count) },
                    yOffsets: (delay > 0 ? [0.0] : []) + steps.map { -40 * Double($0) / Double(count) }
                )
                for trial in 1...2 {
                    runPanProbe(probe, trial: trial, physicsVariant: variant)
                }
            }
        }
    }

    func testPanEntryDeliveryDiscovery() {
        let duration = 0.08
        let distance = -80.0
        let probes = [1, 2, 3, 6, 10].map { count in
            PanProbe(
                name: "delivery-\(count)-samples",
                times: (1...count).map { duration * Double($0) / Double(count) },
                yOffsets: (1...count).map { distance * Double($0) / Double(count) }
            )
        }
        runPanProbeFamily(probes)
    }

    func testPanEntryBaselineDiscovery() {
        let probes = [8.0, 12.0, 20.0, 40.0].map { firstDistance in
            PanProbe(
                name: "baseline-\(Int(firstDistance))-then-20",
                times: [0.02, 0.04, 0.06, 0.10, 0.12, 0.14],
                yOffsets: [
                    -firstDistance / 3,
                    -firstDistance * 2 / 3,
                    -firstDistance,
                    -firstDistance,
                    -firstDistance - 10,
                    -firstDistance - 20,
                ]
            )
        }
        runPanProbeFamily(probes)
    }

    func testPanEntryDirectionDiscovery() {
        let times = [0.013, 0.027, 0.040, 0.053, 0.067, 0.080]
        let y = [-13.0, -27.0, -40.0, -53.0, -67.0, -80.0]
        let probes = [
            PanProbe(name: "direction-straight", times: times, yOffsets: y),
            PanProbe(
                name: "direction-jitter",
                times: times,
                xOffsets: [4, -4, 4, -4, 4, 0],
                yOffsets: y
            ),
            PanProbe(
                name: "direction-reversal",
                times: times,
                yOffsets: [-18, -8, -28, -45, -63, -80]
            ),
        ]
        runPanProbeFamily(probes)
    }

    func testPanEntryVelocityDiscovery() {
        let times = [0.013, 0.027, 0.040, 0.053, 0.067, 0.080]
        let probes = [
            PanProbe(
                name: "velocity-linear",
                times: times,
                yOffsets: [-13, -27, -40, -53, -67, -80]
            ),
            PanProbe(
                name: "velocity-front-loaded",
                times: times,
                yOffsets: [-30, -45, -50, -53, -67, -80]
            ),
            PanProbe(
                name: "velocity-back-loaded",
                times: times,
                yOffsets: [-2, -8, -20, -53, -67, -80]
            ),
        ]
        runPanProbeFamily(probes)
    }

    private func drag(
        _ app: XCUIApplication,
        from startY: CGFloat,
        to endY: CGFloat,
        velocity: CGFloat
    ) {
        let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: startY))
        let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: endY))
        start.press(
            forDuration: 0.02,
            thenDragTo: end,
            withVelocity: XCUIGestureVelocity(rawValue: velocity),
            thenHoldForDuration: 0
        )
    }

    private func flick(
        _ app: XCUIApplication,
        distance: CGFloat,
        velocity: CGFloat
    ) {
        let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.65))
        let end = start.withOffset(CGVector(dx: 0, dy: -distance))
        start.press(
            forDuration: 0.02,
            thenDragTo: end,
            withVelocity: XCUIGestureVelocity(rawValue: velocity),
            thenHoldForDuration: 0
        )
    }

    private func pullDownAndHold(
        _ app: XCUIApplication,
        distance: CGFloat
    ) {
        let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.25))
        let end = start.withOffset(CGVector(dx: 0, dy: distance))
        start.press(
            forDuration: 0.05,
            thenDragTo: end,
            withVelocity: XCUIGestureVelocity(rawValue: 400),
            thenHoldForDuration: 0.40
        )
    }

    @discardableResult
    private func waitForTrace(_ app: XCUIApplication, name: String) -> ScrollMetrics? {
        let settled = expectation(description: "Capture \(name)")
        DispatchQueue.main.asyncAfter(deadline: .now() + 6) { settled.fulfill() }
        wait(for: [settled], timeout: 8)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        let metrics = app.staticTexts["Scroll comparison metrics"].value as? String ?? "missing"
        XCTContext.runActivity(named: "\(name): \(metrics)") { _ in }
        let pattern = #"UIKit=([-0-9.]+), Slint=([-0-9.]+)"#
        let expression = try! NSRegularExpression(pattern: pattern)
        let range = NSRange(metrics.startIndex..., in: metrics)
        guard let match = expression.firstMatch(in: metrics, range: range),
              let nativeRange = Range(match.range(at: 1), in: metrics),
              let slintRange = Range(match.range(at: 2), in: metrics),
              let nativeOffset = Double(metrics[nativeRange]),
              let slintOffset = Double(metrics[slintRange]) else {
            XCTFail("Missing numeric scroll metrics: \(metrics)")
            return nil
        }
        XCTAssertGreaterThan(nativeOffset, 100, "UIKit did not receive the gesture")
        XCTAssertGreaterThan(slintOffset, 100, "Slint did not receive the gesture")
        return ScrollMetrics(uikitOffset: nativeOffset, slintOffset: slintOffset)
    }

    func testShortHardFlickRetainsReleaseMomentum() {
        for trial in 1...3 {
            let name = "short-hard-d120-v6400-trial-\(trial)"
            let app = launch(scenario: name)
            flick(app, distance: 120, velocity: 6_400)
            guard let metrics = waitForTrace(app, name: name) else {
                app.terminate()
                continue
            }
            XCTAssertGreaterThan(metrics.uikitOffset, 700, "UIKit did not capture hard-flick momentum")
            XCTExpectFailure("Slint loses the release momentum of a short, hard flick")
            XCTAssertGreaterThanOrEqual(
                metrics.slintOffset, metrics.uikitOffset * 0.5,
                "Slint traveled less than half UIKit's distance")
            app.terminate()
        }
    }

    func testVelocitySweep() {
        for velocity in [200.0, 400.0, 800.0, 1_600.0, 3_200.0, 6_400.0, 12_800.0, 25_600.0] {
            let name = "velocity-\(Int(velocity))"
            let app = launch(scenario: name)
            drag(app, from: 0.75, to: 0.30, velocity: velocity)
            waitForTrace(app, name: name)
            app.terminate()
        }
    }

    func testCurveTransitionSweep() {
        for velocity in stride(from: 450.0, through: 1_200.0, by: 50.0) {
            let name = "curve-velocity-\(Int(velocity))"
            let app = launch(scenario: name)
            drag(app, from: 0.75, to: 0.30, velocity: velocity)
            waitForTrace(app, name: name)
            app.terminate()
        }
    }

    func testLargeFastCurveSweep() {
        for velocity in [3_200.0, 4_800.0, 6_400.0, 8_000.0, 9_600.0, 11_200.0] {
            let name = "large-fast-velocity-\(Int(velocity))"
            let app = launch(scenario: name)
            drag(app, from: 0.90, to: 0.10, velocity: velocity)
            waitForTrace(app, name: name)
            app.terminate()
        }
    }

    func testMomentumCarry() {
        for flickCount in [2, 3, 4] {
            let name = "momentum-carry-\(flickCount)"
            let app = launch(scenario: name)
            for flick in 0..<flickCount {
                drag(app, from: 0.75, to: 0.30, velocity: 1_600)
                if flick + 1 < flickCount { usleep(120_000) }
            }
            waitForTrace(app, name: name)
            app.terminate()
        }
    }

    func testRepeatedHardFlickAcceleration() {
        let cases: [(count: Int32, gap: Double)] = [
            (1, 0.125),
            (4, 0.075),
            (4, 0.125),
            (4, 0.200),
            (4, 0.350),
        ]
        for testCase in cases {
            for trial in 1...3 {
                let milliseconds = Int(testCase.gap * 1_000)
                let name = "repeated-hard-flicks-\(testCase.count)-gap-\(milliseconds)ms-trial-\(trial)"
                let app = launch(scenario: name)
                let processID = (app.value(forKey: "processID") as! NSNumber).int32Value
                XCTAssertTrue(synthesizeRapidFlicksWithGap(
                    processID, app.frame.width, app.frame.height,
                    testCase.count, testCase.gap))
                waitForTrace(app, name: name)
                app.terminate()
            }
        }
    }

    func testTopPullBounce() {
        for velocity in [400.0, 1_600.0, 3_200.0] {
            let name = "top-pull-\(Int(velocity))"
            let app = launch(scenario: name)
            drag(app, from: 0.30, to: 0.75, velocity: velocity)
            waitForTrace(app, name: name)
            app.terminate()
        }
    }

    func testTopPullDistanceAndReturnCurve() {
        for distance in [50.0, 100.0, 200.0, 300.0] {
            let name = "top-pull-distance-\(Int(distance))"
            let app = launch(scenario: name)
            pullDownAndHold(app, distance: distance)
            waitForTrace(app, name: name)
            app.terminate()
        }
    }

    func testLocalSpringClockExperiment() {
        for variant in ["spring-coordinate", "spring-clock"] {
            captureOverscroll(distances: [200, 600], repeats: 2,
                              physicsVariant: variant)
        }
    }

    func testLocalSpringPhysicsExperiment() {
        captureOverscroll(distances: [50, 200, 600], repeats: 1,
                          physicsVariant: "spring-coordinate")
        captureOverscroll(distances: [100, 300, 450], repeats: 2,
                          physicsVariant: "spring-coordinate")
    }

    func testLocalOverscrollPhysicsExperiment() {
        for variant in ["threshold10", "rubberband10"] {
            captureOverscroll(distances: [50, 200, 600], repeats: 1, physicsVariant: variant)
        }
    }

    func testOverscrollDeliverySmoke() {
        captureOverscroll(distances: [200], repeats: 1)
    }

    func testOverscrollPullAndReturnSimulator() {
        captureOverscroll(distances: [50, 200, 600], repeats: 2)
    }

    private func captureOverscroll(distances: [Double], repeats: Int,
                                   physicsVariant: String = "baseline") {
        for distance in distances {
            for trial in 1...repeats {
                captureOverscrollPull(
                    name: "overscroll-\(physicsVariant)-d\(Int(distance))-trial-\(trial)",
                    distance: distance,
                    duration: max(0.5, distance / 400),
                    holdDuration: 0.40,
                    physicsVariant: physicsVariant)
            }
        }
    }

    /// Pulls down from the top by `distance` points over `duration` seconds,
    /// holds for `holdDuration` seconds, releases, and saves the traces after the return.
    /// With `nativeOnlyInput`, Slint receives no touches and only UIKit is checked.
    private func captureOverscrollPull(
        name: String,
        distance: Double,
        duration: Double,
        holdDuration: Double,
        physicsVariant: String = "baseline",
        nativeOnlyInput: Bool = false,
        viewportHeight: Double? = nil
    ) {
        let app = launch(scenario: name, startOffset: 0, inputTrace: true,
                         traceSaveDelayMs: 2_200, nativeOnlyInput: nativeOnlyInput,
                         physicsVariant: physicsVariant, viewportHeight: viewportHeight)
        let processID = (app.value(forKey: "processID") as! NSNumber).int32Value
        XCTAssertTrue(synthesizeOverscrollPull(
            processID, app.frame.width, app.frame.height, distance, duration, holdDuration
        ), "Failed to synthesize the pull")
        let saved = expectation(description: "Save overscroll return")
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.6) { saved.fulfill() }
        wait(for: [saved], timeout: 5)
        let metrics = app.staticTexts["Scroll comparison metrics"].value as? String ?? ""
        func value(_ key: String) -> Double? {
            let expression = try! NSRegularExpression(pattern: "\(key)=([-0-9.]+)")
            let range = NSRange(metrics.startIndex..., in: metrics)
            guard let match = expression.firstMatch(in: metrics, range: range),
                  let number = Range(match.range(at: 1), in: metrics) else { return nil }
            return Double(metrics[number])
        }
        guard let nativePeak = value("UIKitPeakOverscroll"),
              let slintPeak = value("SlintPeakOverscroll"),
              let nativeOffset = value("UIKit"), let slintOffset = value("Slint") else {
            XCTFail("Missing overscroll metrics: \(metrics)")
            app.terminate()
            return
        }
        XCTAssertGreaterThan(nativePeak, 2, "UIKit did not receive the pull")
        XCTAssertLessThanOrEqual(abs(nativeOffset), 0.5, "UIKit did not return to the top")
        if !nativeOnlyInput {
            XCTAssertGreaterThan(slintPeak, 2, "Slint did not receive the pull")
            XCTAssertLessThanOrEqual(abs(slintOffset), 0.5, "Slint did not return to the top")
        }
        XCTContext.runActivity(named: "\(name): \(metrics)") { _ in }
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        app.terminate()
    }

    private let returnCurveViewports = [774.0, 387.0]

    private var returnCurveRepeats: Int {
        ProcessInfo.processInfo.environment["RETURN_CURVE_REPEATS"].flatMap(Int.init) ?? 3
    }

    private func captureReturnCurve(viewport: Double, distance: Double, speed: Double,
                                    holdDuration: Double, trial: Int) {
        let name = "return-vp\(Int(viewport))-d\(Int(distance))-speed\(Int(speed))"
            + "-hold\(Int(holdDuration * 1_000))-trial-\(trial)"
        captureOverscrollPull(
            name: name,
            distance: distance,
            duration: holdDuration > 0 ? max(0.5, distance / speed) : distance / speed,
            holdDuration: holdDuration,
            nativeOnlyInput: true,
            viewportHeight: viewport)
    }

    /// UIKit return curves after a held pull, for fitting the spring-back model.
    /// See README.md for extracting the traces.
    func testReturnCurveHeldPulls() {
        for viewport in returnCurveViewports {
            for distance in [25.0, 50, 100, 150, 200, 300, 400, 500, 600, 700] {
                for trial in 1...returnCurveRepeats {
                    captureReturnCurve(viewport: viewport, distance: distance, speed: 400,
                                       holdDuration: 0.40, trial: trial)
                }
            }
        }
    }

    /// UIKit return curves after releasing a pull while the finger still moves.
    func testReturnCurveMovingReleases() {
        for viewport in returnCurveViewports {
            for distance in [100.0, 300, 600] {
                for speed in [400.0, 1_200] {
                    for trial in 1...returnCurveRepeats {
                        captureReturnCurve(viewport: viewport, distance: distance, speed: speed,
                                           holdDuration: 0, trial: trial)
                    }
                }
            }
        }
    }

    func testBottomPullBounce() {
        for velocity in [400.0, 1_600.0, 3_200.0] {
            let name = "bottom-pull-\(Int(velocity))"
            let app = launch(scenario: name, fromBottomDistance: 0)
            drag(app, from: 0.75, to: 0.30, velocity: velocity)
            waitForTrace(app, name: name)
            app.terminate()
        }
    }

    func testFlingExhaustsBottom() {
        for (distance, velocity) in [(150.0, 400.0), (300.0, 800.0), (600.0, 1_600.0)] {
            let name = "exhaust-bottom-d\(Int(distance))-v\(Int(velocity))"
            let app = launch(scenario: name, fromBottomDistance: distance)
            drag(app, from: 0.75, to: 0.30, velocity: velocity)
            waitForTrace(app, name: name)
            app.terminate()
        }
    }

    func testFlingExhaustsTop() {
        for (offset, velocity) in [(150.0, 400.0), (300.0, 800.0), (600.0, 1_600.0)] {
            let name = "exhaust-top-d\(Int(offset))-v\(Int(velocity))"
            let app = launch(scenario: name, startOffset: offset)
            drag(app, from: 0.30, to: 0.75, velocity: velocity)
            waitForTrace(app, name: name)
            app.terminate()
        }
    }

    func testReverseDuringDeceleration() {
        let app = launch(scenario: "reverse-during-deceleration", startOffset: 1_500)
        drag(app, from: 0.75, to: 0.30, velocity: 1_600)
        usleep(120_000)
        drag(app, from: 0.30, to: 0.75, velocity: 1_600)
        waitForTrace(app, name: "reverse-during-deceleration")
    }

    func testTouchStopsDeceleration() {
        let app = launch(scenario: "touch-stops-deceleration", startOffset: 1_500)
        drag(app, from: 0.75, to: 0.30, velocity: 1_600)
        usleep(300_000)
        let stop = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.50))
        stop.press(forDuration: 0.5)
        waitForTrace(app, name: "touch-stops-deceleration")
    }
}
