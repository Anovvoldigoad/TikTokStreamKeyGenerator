"""Offline contracts for the single-purpose Android RTMP/key screen."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from Libs import simple_android_stream as core


class SimpleAndroidCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        patcher = patch.object(core, "user_data_dir", return_value=str(self.data))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_config_private_roundtrip(self):
        core.save_settings({"rapidapi_key": "private", "devices": {"pc": {"device_id": "123"}}})
        self.assertEqual(core.load_settings()["rapidapi_key"], "private")
        self.assertEqual(core.config_path().parent, self.data)

    def test_cookie_export_accepts_logged_in_session(self):
        path = self.data / "cookies.json"
        path.write_text(json.dumps([{"name": "sessionid", "value": "secret"}]))
        self.assertEqual(core.validate_cookies(str(path))[0]["name"], "sessionid")

    def test_cookie_export_rejects_non_session_cookies(self):
        path = self.data / "cookies.json"
        path.write_text(json.dumps([{"name": "ttwid", "value": "not-a-session"}]))
        with self.assertRaisesRegex(ValueError, "sesi login"):
            core.validate_cookies(str(path))

    def test_missing_api_key_fails_without_network(self):
        with self.assertRaisesRegex(ValueError, "RapidAPI"):
            core.get_credentials("Test", "")

    def test_invalid_title_fails_without_network(self):
        with self.assertRaisesRegex(ValueError, "Judul"):
            core.get_credentials(" ", "irrelevant")

    def test_existing_live_room_is_not_overwritten(self):
        class FakeStream:
            def __init__(self, **kwargs):
                self.baseStreamUrl = "rtmps://server.example/live"
                self.streamKey = "example-private-key"
                self.roomId = "room-1"
                self.create_calls = 0
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def getContinuableStreamInfo(self, **_):
                return {"has_room": True, "can_resume": True}
            def createStream(self, *_args, **_kwargs):
                self.create_calls += 1
                raise AssertionError("existing room must not be overwritten")

        with patch.object(core, "_ready_settings", return_value=({}, "/tmp/unused")), \
             patch.object(core, "_device_profile", return_value={"device_id": "d", "install_id": "i"}), \
             patch.dict(sys.modules, {"TiktokStreamKeyGenerator": SimpleNamespace(Stream=FakeStream)}):
            result = core.get_credentials("Testing", "private")
        self.assertTrue(result["resumed"])
        self.assertEqual(result["server"], "rtmps://server.example/live")
        self.assertEqual(result["key"], "example-private-key")

    def test_unrecoverable_existing_room_prevents_new_creation(self):
        class FakeStream:
            def __init__(self, **_):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def getContinuableStreamInfo(self, **_):
                return {"has_room": True, "can_resume": False}
            def createStream(self, *_a, **_k):
                raise AssertionError("do not create second LIVE room")

        with patch.object(core, "_ready_settings", return_value=({}, "/tmp/unused")), \
             patch.object(core, "_device_profile", return_value={"device_id": "d", "install_id": "i"}), \
             patch.dict(sys.modules, {"TiktokStreamKeyGenerator": SimpleNamespace(Stream=FakeStream)}):
            with self.assertRaisesRegex(RuntimeError, "room LIVE aktif"):
                core.get_credentials("Testing", "private")


if __name__ == "__main__":
    unittest.main()
