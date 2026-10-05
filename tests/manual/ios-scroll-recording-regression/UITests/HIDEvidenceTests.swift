// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: MIT
import XCTest

final class HIDEvidenceTests: XCTestCase {
    func testFocusedInputEvidence() throws {
        let baseTimes = [0.08, 0.12, 0.16, 0.20]
        let baseY = [0.0, -20.0, -40.0, -60.0]
        let jitterTimes = baseTimes + [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
        let jitterY = baseY + [-60 + 1.0/3, -60, -60 + 1.0/3, -60, -60 + 1.0/3, -60]
        let cases: [(String, [Double], [Double], Double)] = [
            ("hid-short-flick", [0.054258, 0.058425, 0.070955, 0.075122, 0.079270],
             [-15, -20, -28.334, -30.667, -32.667], 0),
            ("hid-held-exact", baseTimes, baseY, 0.3),
            ("hid-held-jitter", jitterTimes, jitterY, 0.016667)
        ]
        try capture(cases)
    }

    func testReleaseGateEvidence() throws {
        try capture([
            ("hid-gate-accelerating", [0.08, 0.196, 0.204], [0, -11.6, -26], 0),
            ("hid-gate-decelerating", [0.08, 0.188, 0.196, 0.204], [0, -86.4, -87.2, -88], 0)
        ])
    }

    func testSparseJitterReleaseGate() throws {
        try capture([
            ("hid-gate-two-jitters", [0.08, 0.12, 0.16, 0.20, 0.25, 0.30],
             [0, -20, -40, -60, -60 + 1.0/3, -60], 0.016667)
        ])
    }

    private func capture(_ cases: [(String, [Double], [Double], Double)]) throws {
        for (name, times, y, hold) in cases {
            for trial in 1...2 {
                let scenario = "\(name)-trial\(trial)"
                let app = XCUIApplication()
                app.launchEnvironment = ["SLINT_BACKEND": "winit-skia", "SLINT_STYLE": "cupertino",
                    "SCROLL_SCENARIO": scenario, "START_OFFSET": "7200", "INPUT_TRACE": "1",
                    "HID_TRACE": "1", "TRACE_SAVE_DELAY_MS": "5000", "NATIVE_ONLY_INPUT": "0"]
                app.launch()
                let metrics = app.staticTexts["Scroll comparison metrics"]
                XCTAssertTrue(metrics.waitForExistence(timeout: 10))
                let pid = (app.value(forKey: "processID") as! NSNumber).int32Value
                let x = Array(repeating: 0.0, count: times.count)
                var delivered = false
                times.withUnsafeBufferPointer { ts in x.withUnsafeBufferPointer { xs in y.withUnsafeBufferPointer { ys in
                    delivered = synthesizePanProbe(pid, app.frame.width, app.frame.height,
                        ts.baseAddress, xs.baseAddress, ys.baseAddress, Int32(times.count), hold)
                }}}
                XCTAssertTrue(delivered)
                let saved = expectation(description: "Wait for HID capture")
                DispatchQueue.main.asyncAfter(deadline: .now() + 5.6) { saved.fulfill() }
                wait(for: [saved], timeout: 8)
                let value = try XCTUnwrap(metrics.value as? String)
                let range = try XCTUnwrap(value.range(of: "Regression="))
                let data = try XCTUnwrap(String(value[range.upperBound...]).data(using: .utf8))
                let result = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
                let nodes = try XCTUnwrap(result["hid_digitizer_nodes"] as? NSNumber).intValue
                XCTAssertGreaterThan(nodes, 0, "No actual HID digitizer data was captured")
                let gap = try XCTUnwrap(result["max_frame_gap_ms"] as? NSNumber).doubleValue
                XCTAssertLessThanOrEqual(gap, 30, "Recording disrupted frame cadence")
                let touches = try XCTUnwrap(result["max_simultaneous_touches"] as? NSNumber).intValue
                XCTAssertEqual(touches, 1)
                let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
                attachment.name = scenario; attachment.lifetime = .keepAlways; add(attachment)
                XCTContext.runActivity(named: "\(scenario): \(value)") { _ in }
                app.terminate()
            }
        }
    }
}
