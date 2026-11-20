"""Unsigned TikTok LIVE Studio Android protocol tests (no real credentials)."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from Libs import native_unsigned_android as native
from Libs import simple_android_stream as core


def fake_response(payload, status=200):
    return SimpleNamespace(
        json=lambda: payload, raise_for_status=lambda: None,
        status_code=status,
    )


class NativeUnsignedTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data = Path(folder.name)
        patcher = patch.object(core, "user_data_dir", return_value=str(self.data))
        patcher.start()
        self.addCleanup(patcher.stop)
        cookie_path = self.data / "cookies.json"
        cookie_path.write_text(json.dumps([
            {"name": "sessionid_ss", "value": "private", "domain": ".tiktok.com"},
            {"name": "tt-target-idc", "value": "alisg", "domain": ".tiktok.com"},
            {"name": "store-country-code", "value": "id", "domain": ".tiktok.com"},
            {"name": "foreign", "value": "leak", "domain": "attacker.example"},
        ]))
        core.save_settings({"cookies_path": str(cookie_path)})
        native._active = None
        native._streaming = False
        self.addCleanup(setattr, native, "_active", None)
        self.addCleanup(setattr, native, "_streaming", False)

    def test_preflight_is_read_only_and_requires_no_signer(self):
        with patch.object(native.requests, "request", return_value=fake_response({
            "status_code": 0, "data": {}
        })) as req:
            out = native.check_native_studio()
        self.assertTrue(out["allowed"])
        self.assertIn("alisg", out["host"])
        args, opts = req.call_args
        self.assertEqual(args[0], "GET")
        self.assertIn("/webcast/room/create_info/", args[1])
        self.assertNotIn("foreign=leak", opts["headers"]["Cookie"])
        self.assertIn("sessionid=private", opts["headers"]["Cookie"])
        self.assertFalse(opts["allow_redirects"])
        self.assertNotIn("x-argus", opts["headers"])
        self.assertNotIn("x-rapidapi-key", opts["headers"])
        self.assertEqual(opts["timeout"], 20)

    def test_rejected_preflight_never_creates_room(self):
        with patch.object(native.requests, "request", return_value=fake_response({
            "status_code": 20800, "message": "no live auth"
        })) as req:
            with self.assertRaisesRegex(RuntimeError, "Tidak ada room"):
                core.get_credentials("Testing", "", "native_unsigned")
        req.assert_called_once()
        self.assertEqual(req.call_args.args[0], "GET")

    def test_start_heartbeat_encoder_confirm_and_finish(self):
        created = {
            "status_code": 0,
            "data": {
                "id_str": "room1", "stream_id_str": "stream2",
                "living_room_attrs": {"room_id_str": "room3"},
                "stream_url": {
                    "rtmp_push_url": "rtmps://push.example/live/key?sign=hidden"
                },
            }
        }
        calls = []
        def respond(method, url, **opts):
            calls.append((method, url, opts))
            if url.endswith("/create_info/"):
                return fake_response({"status_code": 0, "data": {}})
            if url.endswith("/create/"):
                return fake_response(created)
            if url.endswith("/ping/anchor/"):
                return fake_response({"status_code": 0})
            raise AssertionError("unexpected API request")
        with patch.object(native.requests, "request", side_effect=respond):
            out = core.get_credentials("Test", "", "native_unsigned")
            self.assertEqual(out["mode"], "native_unsigned")
            self.assertEqual(out["server"], "rtmps://push.example/live/")
            self.assertEqual(out["key"], "key?sign=hidden")
            second = core.get_credentials("Test", "", "native_unsigned")
            self.assertTrue(second["resumed"])
            self.assertTrue(native.heartbeat_native_studio())
            self.assertTrue(native.mark_native_studio_streaming())
            self.assertTrue(native.heartbeat_native_studio())
            self.assertTrue(core.end_live("", "native_unsigned"))
        self.assertEqual([x[0] for x in calls],
                         ["GET", "POST", "POST", "POST", "POST"])
        posts = [x[2]["data"] for x in calls if x[1].endswith("/ping/anchor/")]
        self.assertIn("status=1", posts[0])
        self.assertIn("status=2", posts[1])
        self.assertIn("status=4", posts[2])
        self.assertIsNone(native._active)
        self.assertFalse(native._streaming)

    def test_incomplete_room_is_stopped_not_reported_as_usable(self):
        def respond(method, url, **opts):
            if url.endswith("/create_info/"):
                return fake_response({"status_code": 0})
            if url.endswith("/create/"):
                return fake_response({"status_code": 0, "data": {
                    "id_str": "room1", "stream_id_str": "stream2",
                    "stream_url": {"rtmp_push_url": "bad-url"}
                }})
            if url.endswith("/ping/anchor/"):
                self.assertIn("status=4", opts["data"])
                return fake_response({"status_code": 0})
            raise AssertionError(url)
        with patch.object(native.requests, "request", side_effect=respond) as request:
            with self.assertRaisesRegex(RuntimeError, "tidak lengkap"):
                native.start_native_studio("test")
        self.assertEqual(request.call_count, 3)
        self.assertIsNone(native._active)

    def test_unrecognized_region_uses_fixed_host_and_key_cannot_be_fake(self):
        native.HOST_BY_IDC.get("random-host")
        self.assertIsNone(native._parse_push_url({"stream_url": {
            "rtmp_push_url": "https://site.invalid/not/rtmp"
        }}))
        self.assertIsNone(native._parse_push_url({}))
        with self.assertRaises(ValueError):
            native.UnsignedStudioClient().request("DELETE", "/webcast/room/create/")
        with self.assertRaises(ValueError):
            native.UnsignedStudioClient().request("GET", "https://evil.example/")


if __name__ == "__main__":
    unittest.main()
