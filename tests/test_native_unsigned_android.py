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

    def test_indonesian_unknown_idc_tries_sg_then_global_without_signer(self):
        core.save_settings({"cookies_path": core.load_settings()["cookies_path"]})
        cookie_path = Path(core.load_settings()["cookies_path"])
        cookies = json.loads(cookie_path.read_text())
        for cookie in cookies:
            if cookie["name"] == "tt-target-idc":
                cookie["value"] = "unknown-indonesia-idc"
        cookie_path.write_text(json.dumps(cookies))
        seen_hosts = []
        def respond(method, url, **opts):
            seen_hosts.append(url)
            self.assertNotIn("X-RapidAPI-Key", opts["headers"])
            self.assertEqual(method, "GET")
            return fake_response({"status_code": 20003 if len(seen_hosts) == 1 else 0})
        with patch.object(native.requests, "request", side_effect=respond):
            result = native.check_native_studio()
        self.assertTrue(result["allowed"])
        self.assertEqual(len(seen_hosts), 2)
        self.assertIn("alisg.tiktokv.com", seen_hosts[0])
        self.assertIn("webcast.tiktokv.com", seen_hosts[1])
        self.assertEqual(result["host"], "webcast.tiktokv.com")

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

    def test_active_live_precheck_refuses_second_room(self):
        with patch.object(native.requests, "request", return_value=fake_response({
            "status_code": 0, "data": {"live_status": 2}
        })) as request:
            with self.assertRaisesRegex(RuntimeError, "masih aktif"):
                native.start_native_studio("Never create second LIVE")
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "GET")
        self.assertNotIn("native_unsigned_room", core.load_settings())

    def test_restart_recovers_room_for_cleanup_without_persisting_stream_key(self):
        created = {
            "status_code": 0,
            "data": {
                "id_str": "room-a", "stream_id_str": "stream-b",
                "living_room_attrs": {"room_id_str": "room-ping"},
                "stream_url": {
                    "rtmp_push_url": "rtmps://push.invalid/live/secret?signature=sensitive"
                },
            },
        }
        def respond(method, url, **_):
            if url.endswith("/create_info/"):
                return fake_response({"status_code": 0})
            if url.endswith("/create/"):
                return fake_response(created)
            if url.endswith("/ping/anchor/"):
                return fake_response({"status_code": 0})
            raise AssertionError("unexpected request")
        with patch.object(native.requests, "request", side_effect=respond):
            output = native.start_native_studio("Test")
        self.assertIn("signature=sensitive", output["key"])
        stored = core.load_settings()["native_unsigned_room"]
        self.assertEqual(stored["room_id"], "room-a")
        self.assertNotIn("key", str(stored))
        self.assertNotIn("sensitive", str(stored))
        native._active = None  # Simulate process restart and lost RTMP key.
        with patch.object(native.requests, "request") as request:
            with self.assertRaisesRegex(RuntimeError, "Akhiri Room"):
                native.start_native_studio("Do not duplicate")
        request.assert_not_called()
        with patch.object(native.requests, "request", return_value=fake_response({
            "status_code": 0
        })) as request:
            self.assertTrue(native.end_native_studio())
        self.assertIn("status=4", request.call_args.kwargs["data"])
        self.assertNotIn("native_unsigned_room", core.load_settings())
        self.assertIsNone(native._active)

    def test_restored_room_host_must_be_known_before_sending_cookies(self):
        core.save_settings({
            **core.load_settings(),
            "native_unsigned_room": {
                "room_id": "one", "ping_room_id": "two",
                "stream_id": "three", "host": "https://attacker.invalid"
            }
        })
        with patch.object(native.requests, "request") as request:
            with self.assertRaisesRegex(RuntimeError, "Host room"):
                native.end_native_studio()
        request.assert_not_called()
        self.assertIn("native_unsigned_room", core.load_settings())

    def test_failed_private_persistence_attempts_to_end_just_created_live(self):
        def respond(method, url, **_):
            if url.endswith("/create_info/"):
                return fake_response({"status_code": 0})
            if url.endswith("/create/"):
                return fake_response({"status_code": 0, "data": {
                    "id_str": "one", "stream_id_str": "two",
                    "stream_url": {"rtmp_push_url": "rtmp://example.invalid/live/key"}
                }})
            if url.endswith("/ping/anchor/"):
                return fake_response({"status_code": 0})
            raise AssertionError(url)
        with patch.object(native.requests, "request", side_effect=respond) as request, \
             patch.object(native, "save_settings", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(RuntimeError, "menyimpan identitas"):
                native.start_native_studio("Test")
        self.assertEqual(request.call_count, 3)
        self.assertIn("status=4", request.call_args.kwargs["data"])
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
