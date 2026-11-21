"""Offline core PC LIVE contract running with Android app-private paths.

This exercises the actual Stream class; every external network/signature call
is stubbed. Tests do not use credentials, call TikTok, or create any LIVE.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
import TiktokStreamKeyGenerator as app


class AndroidPcLiveContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cookies_path = Path(self.directory.name) / "cookies.json"
        self.cookies_path.write_text(
            json.dumps({"cookies": [{"name": "sessionid", "value": "test-not-a-token"}]}),
            encoding="utf-8",
        )
        with patch.object(app, "_new_http_session", side_effect=requests.Session), \
             patch.object(app, "build_common_headers", return_value={}):
            self.stream = app.Stream(
                cookies_path=str(self.cookies_path), device_type="pc",
                device_profile={"device_id": "123456789", "install_id": "987654321"},
            )
        self.addCleanup(self.stream.s.close)

    def test_wrapped_cookie_reaches_real_live_http_session(self):
        self.assertEqual(self.stream.client.kind, "pc")
        self.assertEqual(self.stream.s.cookies.get("sessionid"), "test-not-a-token")

    def test_real_create_room_parses_tiktok_stream_key(self):
        response = {
            "status_code": 0, "data": {
                "living_room_attrs": {"room_id_str": "899999"},
                "stream_id_str": "755555",
                "stream_url": {"rtmp_push_url": "rtmps://stream.example.test/live/secret-key"},
                "owner_user_id_str": "111",
            },
        }
        with patch.object(self.stream, "_ensure_region_context"), \
             patch.object(self.stream, "_prepare_chat_preferences", return_value={}), \
             patch.object(self.stream, "getServerUrl", return_value="https://webcast.example.test/"), \
             patch.object(self.stream, "_apply_live_studio_headers"), \
             patch.object(self.stream, "_studio_params", return_value={"aid": "8311"}), \
             patch.object(self.stream, "_store_region_headers", return_value={}), \
             patch.object(self.stream, "_request_json", return_value=response) as request, \
             patch.object(self.stream, "_check_created_live_settings"), \
             patch.object(app, "_build_signature_headers", return_value={
                 "x-argus": "mock", "x-ladon": "mock", "x-khronos": "123"}):
            self.assertTrue(self.stream.createStream(
                "Test LIVE", "5", "0", device_id="123456789", install_id="987654321"))
        self.assertEqual(self.stream.roomId, "899999")
        self.assertEqual(self.stream.streamId, "755555")
        self.assertEqual(self.stream.baseStreamUrl, "rtmps://stream.example.test/live")
        self.assertEqual(self.stream.streamKey, "secret-key")
        self.assertIn("webcast/room/create/", request.call_args.args[1])
        self.assertEqual(request.call_args.kwargs["method"] if "method" in request.call_args.kwargs
                         else request.call_args.args[0], "POST")

    def test_missing_push_url_closes_newly_created_room(self):
        response = {"status_code": 0, "data": {
            "living_room_attrs": {"room_id_str": "8000"},
            "stream_id_str": "9000",
            "stream_url": {},
        }}
        with patch.object(self.stream, "_ensure_region_context"), \
             patch.object(self.stream, "_prepare_chat_preferences", return_value={}), \
             patch.object(self.stream, "getServerUrl", return_value="https://webcast.example.test/"), \
             patch.object(self.stream, "_apply_live_studio_headers"), \
             patch.object(self.stream, "_studio_params", return_value={"aid": "8311"}), \
             patch.object(self.stream, "_store_region_headers", return_value={}), \
             patch.object(self.stream, "_request_json", return_value=response), \
             patch.object(self.stream, "endStream", return_value=True) as finish, \
             patch.object(app, "_build_signature_headers", return_value={
                 "x-argus": "mock", "x-ladon": "mock", "x-khronos": "123"}):
            with self.assertRaisesRegex(RuntimeError, "ended"):
                self.stream.createStream("Test", "5", device_id="123", install_id="456")
        finish.assert_called_once()
        self.assertEqual(finish.call_args.kwargs["room_id"], "8000")
        self.assertEqual(finish.call_args.kwargs["stream_id"], "9000")

    def test_anchor_heartbeat_and_end_have_real_room_identity(self):
        self.stream.roomId, self.stream.streamId = "8000", "9000"
        with patch.object(self.stream, "_pingAnchorStatus",
                          return_value={"status_code": 0}) as ping:
            self.stream.anchorHeartbeat(
                app.ANCHOR_STATUS_PREPARE, device_id="123", install_id="456")
            self.assertEqual(ping.call_args.kwargs["room_id"], "")
            self.assertEqual(ping.call_args.args[0], app.ANCHOR_STATUS_PREPARE)
        with patch.object(self.stream, "getServerUrl", return_value="https://webcast.example.test/"), \
             patch.object(self.stream, "_studio_params", return_value={"aid": "8311"}), \
             patch.object(self.stream, "_signed_get_json", return_value={}), \
             patch.object(self.stream, "_pingAnchorStatus",
                          return_value={"status_code": 0}) as ping:
            self.assertTrue(self.stream.endStream(
                device_id="123", install_id="456", room_id="8000", stream_id="9000"))
            self.assertEqual(ping.call_args.args[0], app.ANCHOR_STATUS_FINISH)
            self.assertEqual(ping.call_args.kwargs["room_id"], "8000")
            self.assertEqual(ping.call_args.kwargs["stream_id"], "9000")
            self.assertEqual(ping.call_args.kwargs["repeat"], 2)

    def test_complete_rtmps_push_url_keeps_signed_key_and_query(self):
        room = {
            "living_room_attrs": {"room_id_str": "8123"},
            "stream_id_str": "9000",
            "stream_url": {
                "rtmp_push_url": "rtmps://stream.example.test/live/secret-key?auth=a/b",
            },
        }
        self.assertTrue(self.stream._apply_room_info(room))
        self.assertEqual(self.stream.baseStreamUrl, "rtmps://stream.example.test/live")
        self.assertEqual(self.stream.streamKey, "secret-key?auth=a/b")

    def test_incomplete_push_url_is_not_reported_as_a_usable_stream(self):
        for url in (
            "rtmps://stream.example.test/live/",
            "rtmp://stream.example.test",
            "https://stream.example.test/live/not-rtmp",
            "rtmp://stream.example.test/live",
        ):
            with self.subTest(url=url):
                room = {
                    "living_room_attrs": {"room_id_str": "8123"},
                    "stream_id_str": "9000",
                    "stream_url": {"rtmp_push_url": url},
                }
                self.assertFalse(self.stream._apply_room_info(room))
                self.assertEqual(self.stream.streamKey, "")

    def test_proxy_command_logs_redact_remote_stream_credentials(self):
        from TiktokStreamKeyGenerator import _mask_stream_url
        for url in ("rtmp://host.example/live/secret", "rtmps://host.example/live/secret?token=xyz"):
            with self.subTest(url=url):
                masked = _mask_stream_url(url)
                self.assertNotIn("secret", masked)
                self.assertNotIn("token", masked)
                self.assertNotIn("xyz", masked)
        local = "rtmp://127.0.0.1:19350/live/obs"
        self.assertEqual(_mask_stream_url(local), local)



if __name__ == "__main__":
    unittest.main()
