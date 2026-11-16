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


    def test_clipboard_json_creates_private_cookie_file(self):
        payload = json.dumps([{"name": "sessionid", "value": "test-private"}])
        target = Path(core.import_cookies_text(payload))
        self.assertEqual(target.parent, self.data)
        self.assertEqual(core.load_settings()["cookies_path"], str(target))
        self.assertEqual(core.validate_cookies(target)[0]["value"], "test-private")
        with self.assertRaises(ValueError):
            core.import_cookies_text(" ")
        self.assertEqual(core.validate_cookies(target)[0]["value"], "test-private")

    def test_end_live_uses_selected_mobile_identity(self):
        seen = {}
        class FakeStream:
            def __init__(self, **kwargs):
                seen["mode"] = kwargs["device_type"]
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def getContinuableStreamInfo(self, **_):
                return {"has_room": True, "room_id": "room-1",
                        "stream_id": "stream-1", "priority_region": "id"}
            def endStream(self, **kwargs):
                seen["end"] = kwargs

        with patch.object(core, "_ready_settings", return_value=({}, "/tmp/unused")), \
             patch.object(core, "_device_profile", return_value={"device_id": "123", "install_id": "456"}), \
             patch.dict(sys.modules, {"TiktokStreamKeyGenerator": SimpleNamespace(Stream=FakeStream)}):
            self.assertTrue(core.end_live("test-key", "mobile"))
        self.assertEqual(seen["mode"], "mobile")
        self.assertEqual(seen["end"]["priority_region"], "id")
        self.assertEqual(seen["end"]["room_id"], "room-1")

    def test_qr_login_writes_verified_cookies_to_private_storage(self):
        class FakeQrClient:
            def __init__(self, device_id, install_id):
                self.qr_client_secret = "expected"
                self.closed = False
            def get_qrcode(self):
                return {"token": "token", "qrcode_index_url":
                        "https://www.tiktok.com/qr/login?next_url=mock-valid"}
            def check_qrconnect(self, token):
                return {"data": {"status": "confirmed", "client_secret": "expected"}}
            def save_cookies(self, path):
                Path(path).write_text(json.dumps(
                    [{"name": "sessionid", "value": "private-session"}]))
            def close(self):
                self.closed = True

        with patch.object(core, "_device_profile", return_value={"device_id": "123", "install_id": "456"}), \
             patch.dict(sys.modules, {"TiktokStreamKeyGenerator": SimpleNamespace(
                 LiveStudioBrowserLoginClient=FakeQrClient)}):
            session = core.QrLoginSession()
            self.assertTrue(session.start("private-api-key").startswith("iVBORw0KGgo"))
            self.assertEqual(session.poll(), "confirmed")
            self.assertEqual(core.load_settings()["cookies_path"], str(self.data / "qr-cookies.json"))
            self.assertEqual(core.validate_cookies(self.data / "qr-cookies.json")[0]["value"], "private-session")
            session.close()
            self.assertTrue(session.client is None)

    def test_actual_qr_png_is_valid_and_readable(self):
        import base64
        import segno
        import io
        url = "https://www.tiktok.com/qr/login?next_url=https%3A%2F%2Fwww.tiktok.com"
        result = core.qr_png_from_response({"qrcode_index_url": url})
        data = base64.b64decode(result, validate=True)
        self.assertTrue(data.startswith(b"\\x89PNG\\r\\n\\x1a\\n"))
        self.assertGreater(len(data), 100)

        buffer = io.BytesIO()
        segno.make_qr(url).save(buffer, kind="png", scale=4)
        fallback = core.qr_png_from_response({
            "qrcode": base64.b64encode(buffer.getvalue()).decode("ascii")
        })
        self.assertTrue(base64.b64decode(fallback).startswith(b"\\x89PNG"))
        with self.assertRaisesRegex(ValueError, "PNG"):
            core.qr_png_from_response({"qrcode": "cG5n"})
        with self.assertRaisesRegex(ValueError, "tidak valid"):
            core.qr_png_from_response({"qrcode_index_url": "http://example.invalid"})

    def test_qr_login_does_not_accept_wrong_client_secret(self):
        class FakeQrClient:
            def __init__(self, *_):
                self.qr_client_secret = "expected"
            def get_qrcode(self):
                return {"token": "token", "qrcode_index_url":
                        "https://www.tiktok.com/qr/login?next_url=mock-valid"}
            def check_qrconnect(self, *_):
                return {"data": {"status": "confirmed", "client_secret": "different"}}
            def save_cookies(self, path):
                raise AssertionError("wrong QR confirmation cannot save cookies")
            def close(self):
                pass

        with patch.object(core, "_device_profile", return_value={"device_id": "123", "install_id": "456"}), \
             patch.dict(sys.modules, {"TiktokStreamKeyGenerator": SimpleNamespace(
                 LiveStudioBrowserLoginClient=FakeQrClient)}):
            session = core.QrLoginSession()
            session.start("private-api-key")
            self.assertEqual(session.poll(), "scanned")
            self.assertNotIn("cookies_path", core.load_settings())
            session.close()

if __name__ == "__main__":
    unittest.main()
