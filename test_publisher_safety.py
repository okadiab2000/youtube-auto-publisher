import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import upload_short


class PublisherLockSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.state_path = Path(self.temp_dir.name) / "state.json"
        self.output_path = Path(self.temp_dir.name) / "github_output"
        self.state_patcher = patch.object(upload_short, "STATE_FILE", self.state_path)
        self.state_patcher.start()
        self.addCleanup(self.state_patcher.stop)
        self.output_patcher = patch.dict(
            os.environ,
            {"GITHUB_OUTPUT": str(self.output_path)},
            clear=False,
        )
        self.output_patcher.start()
        self.addCleanup(self.output_patcher.stop)

    def write_state(self, state):
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False),
            encoding="utf-8",
        )

    def read_state(self):
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def output(self):
        return self.output_path.read_text(encoding="utf-8")

    def test_prepared_upload_can_be_locked_once(self):
        self.write_state({
            "pending_upload": {
                "status": "prepared",
                "filename": "video.webm",
                "drive_file_id": "drive-id",
                "title": "title",
                "slot": "2026-10-21-15",
            }
        })

        upload_short.cmd_lock()

        state = self.read_state()
        self.assertEqual(state["pending_upload"]["status"], "uploading")
        self.assertIn("locked_at", state["pending_upload"])
        self.assertIn("attempt=true", self.output())

    def test_uploading_state_cannot_be_locked_or_retried(self):
        original = {
            "pending_upload": {
                "status": "uploading",
                "filename": "video.webm",
                "drive_file_id": "drive-id",
                "title": "title",
                "slot": "2026-10-21-15",
                "locked_at": "2026-10-21T15:00:00+03:00",
            }
        }
        self.write_state(original)

        upload_short.cmd_lock()

        self.assertEqual(self.read_state(), original)
        self.assertIn("attempt=false", self.output())

    def test_no_pending_upload_does_not_authorize_attempt(self):
        original = {"pending_upload": None}
        self.write_state(original)

        upload_short.cmd_lock()

        self.assertEqual(self.read_state(), original)
        self.assertIn("attempt=false", self.output())

    def test_unexpected_pending_status_does_not_authorize_attempt(self):
        original = {"pending_upload": {"status": "unknown"}}
        self.write_state(original)

        upload_short.cmd_lock()

        self.assertEqual(self.read_state(), original)
        self.assertIn("attempt=false", self.output())

    def test_prepare_stops_when_titles_are_exhausted_before_google_api(self):
        titles_path = Path(self.temp_dir.name) / "titles.txt"
        titles_path.write_text("title one\\ntitle two\\n", encoding="utf-8")
        self.write_state({
            "next_video_index": 1,
            "next_title_index": 2,
            "published": [],
            "processed_slots": [],
            "pending_upload": None,
        })

        with patch.object(upload_short, "TITLES_FILE", titles_path):
            with patch.object(upload_short, "check_schedule"):
                with patch.object(
                    upload_short,
                    "current_slot",
                    return_value="2026-10-21-20",
                ):
                    with patch.object(upload_short, "get_google_services") as google:
                        upload_short.cmd_prepare()

        google.assert_not_called()
        self.assertIsNone(self.read_state()["pending_upload"])
        self.assertIn("ready=false", self.output())

    def test_publish_refuses_unlocked_prepared_upload(self):
        self.write_state({
            "pending_upload": {
                "status": "prepared",
                "filename": "video.webm",
                "drive_file_id": "drive-id",
                "title": "title",
                "slot": "2026-10-21-15",
            }
        })

        with patch.object(upload_short, "check_schedule"):
            with patch.object(upload_short, "get_google_services") as google_services:
                with self.assertRaisesRegex(RuntimeError, "not locked"):
                    upload_short.cmd_publish()
                google_services.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
