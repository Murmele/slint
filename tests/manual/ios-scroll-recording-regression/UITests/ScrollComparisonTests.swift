// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: MIT
// cspell:ignore XCUI XCTest
import XCTest

final class ScrollComparisonTests: XCTestCase {
    private struct Replay {
        let name: String
        let times: [Double]
        let y: [Double]
        let checksTail: Bool
    }
    private let replays = [
        Replay(name: "gesture9", times: [0.054258000, 0.058425000, 0.070955000, 0.075122000, 0.079270000], y: [-15.000, -20.000, -28.334, -30.667, -32.667], checksTail: false),
        Replay(name: "gesture10", times: [0.062613000, 0.066780000, 0.079265000, 0.083432000, 0.087599000, 0.091766000, 0.095949000, 0.100132000, 0.104295000, 0.108458000, 0.112624000, 0.116791000, 0.120962000], y: [9.667, 13.000, 15.667, 16.667, 18.000, 19.667, 21.000, 22.000, 23.334, 24.334, 25.667, 26.667, 28.334], checksTail: false),
        Replay(name: "gesture8", times: [0.062566000, 0.066733000, 0.070869000, 0.075006000, 0.079192000, 0.083379000, 0.087541000, 0.091704000, 0.095860000, 0.100017000, 0.104198000, 0.108379000, 0.112530000, 0.116682000, 0.120860000], y: [12.333, 16.333, 17.667, 19.000, 20.333, 21.333, 22.667, 24.000, 25.000, 26.333, 27.667, 29.333, 30.667, 31.667, 33.667], checksTail: true),
        Replay(name: "gesture13", times: [0.054238000, 0.058405000, 0.070913000, 0.075080000, 0.079231000, 0.083383000, 0.087541000, 0.091699000, 0.095875000, 0.100052000, 0.104214000], y: [14.000, 18.666, 25.666, 28.000, 31.333, 34.666, 37.666, 39.333, 41.666, 44.000, 45.666], checksTail: true)
    ]

    func testRecordedFlickAndSettlingParity() {
        continueAfterFailure = true
        for replay in replays {
            for trial in 1...2 {
                let app = XCUIApplication()
                let scenario = "recorded-\(replay.name)-trial\(trial)"
                app.launchEnvironment = ["SLINT_BACKEND": "winit-skia", "SLINT_STYLE": "cupertino",
                    "SCROLL_SCENARIO": scenario, "START_OFFSET": "7200", "INPUT_TRACE": "1",
                    "TRACE_SAVE_DELAY_MS": "5000", "NATIVE_ONLY_INPUT": "0"]
                app.launch()
                let metrics = app.staticTexts["Scroll comparison metrics"]
                XCTAssertTrue(metrics.waitForExistence(timeout: 10))
                let pid = (app.value(forKey: "processID") as! NSNumber).int32Value
                let x = Array(repeating: 0.0, count: replay.times.count)
                var delivered = false
                replay.times.withUnsafeBufferPointer { times in
                    x.withUnsafeBufferPointer { xs in
                        replay.y.withUnsafeBufferPointer { ys in
                            delivered = synthesizePanProbe(pid, app.frame.width, app.frame.height,
                                times.baseAddress, xs.baseAddress, ys.baseAddress, Int32(times.count), 0)
                        }
                    }
                }
                XCTAssertTrue(delivered, "Gesture injection failed: \(scenario)")
                let saved = expectation(description: "Wait for complete natural return")
                DispatchQueue.main.asyncAfter(deadline: .now() + 5.6) { saved.fulfill() }
                wait(for: [saved], timeout: 8)
                guard let value = metrics.value as? String,
                      let range = value.range(of: "Regression="),
                      let data = String(value[range.upperBound...]).data(using: .utf8),
                      let result = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                    XCTFail("Missing recorded outcome: \(scenario)")
                    app.terminate()
                    continue
                }
                func number(_ key: String) -> Double { (result[key] as? NSNumber)?.doubleValue ?? .nan }
                let json = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
                json.name = scenario
                json.lifetime = .keepAlways
                add(json)
                XCTAssertLessThanOrEqual(number("max_frame_gap_ms"), 30, "Sampling failure: \(scenario)")
                XCTAssertLessThanOrEqual(number("uikit_final_range_pt"), 0.05, "UIKit still moving")
                XCTAssertLessThanOrEqual(number("slint_final_range_pt"), 0.05, "Slint still moving")
                XCTAssertGreaterThan(number("uikit_post_range_pt"), 5, "UIKit did not fling; delivery is inconclusive")
                XCTAssertGreaterThan(number("slint_post_range_pt"), 5, "Slint failed to fling: \(scenario)")
                XCTAssertLessThanOrEqual(abs(number("slint_post_travel_pt")-number("uikit_post_travel_pt")), 5,
                    "Post-release travel mismatch: \(scenario)")
                if replay.checksTail {
                    XCTAssertLessThanOrEqual(abs(number("slint_settle_01_s")-number("uikit_settle_01_s")), 0.15,
                        "Long settling tail: \(scenario)")
                    XCTAssertLessThanOrEqual(abs(number("slint_settle_1_s")-number("uikit_settle_1_s")), 0.15,
                        "Tail mismatch remains at one point: \(scenario)")
                }
                XCTContext.runActivity(named: "\(scenario): \(value)") { _ in }
                app.terminate()
            }
        }
    }
}
