import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import upload_short


CAIRO = ZoneInfo("Africa/Cairo")


class ScheduleSafetyTests(unittest.TestCase):
    def test_start_date_is_enforced(self):
        before_start = datetime(2026, 10, 18, 15, 0, tzinfo=CAIRO)
        with self.assertRaisesRegex(RuntimeError, "Publishing starts on"):
            upload_short.check_schedule(before_start)

    def test_three_pm_cairo_slot_is_allowed(self):
        at_three = datetime(2026, 10, 21, 15, 0, tzinfo=CAIRO)
        upload_short.check_schedule(at_three)

    def test_eight_pm_cairo_slot_is_allowed(self):
        at_eight = datetime(2026, 10, 21, 20, 0, tzinfo=CAIRO)
        upload_short.check_schedule(at_eight)

    def test_other_hours_are_blocked(self):
        for hour in (0, 14, 16, 19, 21, 23):
            with self.subTest(hour=hour):
                at_hour = datetime(2026, 10, 21, hour, 0, tzinfo=CAIRO)
                with self.assertRaisesRegex(RuntimeError, "allowed only"):
                    upload_short.check_schedule(at_hour)

    def test_slot_key_uses_cairo_local_date_and_hour(self):
        at_three = datetime(2026, 10, 21, 15, 30, tzinfo=CAIRO)
        at_eight = datetime(2026, 10, 21, 20, 10, tzinfo=CAIRO)
        self.assertEqual(upload_short.current_slot(at_three), "2026-10-21-15")
        self.assertEqual(upload_short.current_slot(at_eight), "2026-10-21-20")


if __name__ == "__main__":
    unittest.main(verbosity=2)
