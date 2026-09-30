# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT

import unittest

from analyze_trace import check_delivery


def fixture():
    rows = []
    for kind in ("touch", "consumed_touch"):
        for index, action in enumerate(("0", "2", "1")):
            rows.append(dict(kind=kind, pointer_id="0", action=action,
                             event_time_ms=str(index * 10), x_px="100", y_px=str(500 - index * 20)))
    for kind in ("touch_history", "consumed_history"):
        rows.append(dict(kind=kind, pointer_id="0", action="2", event_time_ms="5", x_px="100", y_px="490"))
    for index in range(25):
        rows.append(dict(kind="frame", aosp_y_dp=str(5544 + index), slint_y_dp=str(5544 + index)))
    return rows


class DeliveryChecks(unittest.TestCase):
    def test_complete_delivery(self):
        self.assertTrue(check_delivery(fixture())["history_exercised"])

    def test_missing_history_is_rejected(self):
        rows = [row for row in fixture() if row["kind"] != "consumed_history"]
        with self.assertRaisesRegex(ValueError, "Lost"):
            check_delivery(rows)

    def test_changed_timestamp_is_rejected(self):
        rows = fixture()
        next(row for row in rows if row["kind"] == "consumed_touch")["event_time_ms"] = "7"
        with self.assertRaisesRegex(ValueError, "timestamp"):
            check_delivery(rows)

    def test_coordinate_corruption_is_rejected(self):
        rows = fixture()
        next(row for row in rows if row["kind"] == "consumed_history")["y_px"] = "500"
        with self.assertRaisesRegex(ValueError, "translation"):
            check_delivery(rows)

    def test_alignment_failure_is_rejected(self):
        rows = fixture()
        next(row for row in rows if row["kind"] == "frame")["slint_y_dp"] = "5500"
        with self.assertRaisesRegex(ValueError, "aligned"):
            check_delivery(rows)

    def test_stationary_slint_is_rejected(self):
        rows = fixture()
        for row in rows:
            if row["kind"] == "frame":
                row["slint_y_dp"] = "5544"
        with self.assertRaisesRegex(ValueError, "visibly move"):
            check_delivery(rows)


if __name__ == "__main__":
    unittest.main()
