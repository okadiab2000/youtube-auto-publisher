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
        self.assertEqual(upload_short.resolve_publish_slot(at_three), "2026-10-21-15")

    def test_eight_pm_cairo_slot_is_allowed(self):
        at_eight = datetime(2026, 10, 21, 20, 0, tzinfo=CAIRO)
        upload_short.check_schedule(at_eight)
        self.assertEqual(upload_short.resolve_publish_slot(at_eight), "2026-10-21-20")

    def test_grace_before_hour_is_accepted(self):
        early = datetime(2026, 10, 21, 14, 55, tzinfo=CAIRO)
        self.assertEqual(upload_short.resolve_publish_slot(early), "2026-10-21-15")
        upload_short.check_schedule(early)

        early20 = datetime(2026, 10, 21, 19, 50, tzinfo=CAIRO)
        self.assertEqual(upload_short.resolve_publish_slot(early20), "2026-10-21-20")
        upload_short.check_schedule(early20)

    def test_grace_after_hour_is_accepted(self):
        late = datetime(2026, 10, 21, 16, 20, tzinfo=CAIRO)
        self.assertEqual(upload_short.resolve_publish_slot(late), "2026-10-21-15")
        upload_short.check_schedule(late)

        late20 = datetime(2026, 10, 21, 21, 20, tzinfo=CAIRO)
        self.assertEqual(upload_short.resolve_publish_slot(late20), "2026-10-21-20")
        upload_short.check_schedule(late20)

    def test_outside_grace_windows_are_blocked(self):
        for hour, minute in [
            (0, 0),
            (12, 0),
            (14, 30),
            (16, 30),
            (18, 0),
            (19, 30),
            (21, 30),
            (23, 0),
        ]:
            with self.subTest(hour=hour, minute=minute):
                at = datetime(2026, 10, 21, hour, minute, tzinfo=CAIRO)
                self.assertIsNone(upload_short.resolve_publish_slot(at))
                with self.assertRaisesRegex(RuntimeError, "allowed only"):
                    upload_short.check_schedule(at)

    def test_slot_key_uses_cairo_local_date_and_hour(self):
        at_three = datetime(2026, 10, 21, 15, 30, tzinfo=CAIRO)
        at_eight = datetime(2026, 10, 21, 20, 10, tzinfo=CAIRO)
        self.assertEqual(upload_short.current_slot(at_three), "2026-10-21-15")
        self.assertEqual(upload_short.current_slot(at_eight), "2026-10-21-20")

    def test_late_run_still_maps_to_correct_slot(self):
        almost_eight = datetime(2026, 10, 23, 19, 59, tzinfo=CAIRO)
        slot = upload_short.resolve_publish_slot(almost_eight)
        self.assertEqual(slot, "2026-10-23-20")
        upload_short.check_schedule(almost_eight)

    def test_very_late_run_after_grace_is_blocked(self):
        too_late = datetime(2026, 10, 23, 21, 30, tzinfo=CAIRO)
        self.assertIsNone(upload_short.resolve_publish_slot(too_late))


if __name__ == "__main__":
    unittest.main(verbosity=2)
