"""Offline contracts for Streamlabs Android no-RapidAPI login and LIVE calls."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

from Libs import simple_android_stream as core
from Libs import streamlabs_android as module


class StreamlabsAndroidTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        patcher = patch.object(core, "user_data_dir", return_value=str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_loopback_pkce_flow_and_exchange_uses_one_time_code(self):
        login = module.StreamlabsBrowserLogin()
        self.addCleanup(login.close)
        url = login.begin()
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        self.assertEqual(parsed.hostname, "streamlabs.com")
        self.assertEqual(params["code_flow"], ["true"])
        self.assertTrue(params["code_challenge"][0])
        port = int(params["port"][0])
        self.assertFalse(login.ready())
        with urlopen(f"http://127.0.0.1:{port}/callback?success=true&code=mock-one-time-code",
                     timeout=3) as response:
            self.assertIn(b"diterima", response.read())
        self.assertTrue(login.ready())
        mock_response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"success": True, "data": {"oauth_token": "test-secret"}},
        )
        with patch.object(module.requests, "get", return_value=mock_response) as request:
            self.assertEqual(login.exchange(), "test-secret")
        _, kwargs = request.call_args
        self.assertEqual(kwargs["params"]["code"], "mock-one-time-code")
        self.assertEqual(kwargs["params"]["code_verifier"], login.verifier)
        with self.assertRaisesRegex(RuntimeError, "sudah diproses"):
            login.exchange()

    def test_browser_login_rejects_false_callback(self):
        from urllib.error import HTTPError
        login = module.StreamlabsBrowserLogin()
        self.addCleanup(login.close)
        login.begin()
        with self.assertRaises(HTTPError):
            urlopen(f"http://127.0.0.1:{login.server.server_port}/?success=false", timeout=3)
        self.assertTrue(login.ready())
        with self.assertRaisesRegex(RuntimeError, "ditolak"):
            login.exchange()

    def test_save_token_checks_remote_account_before_persisting(self):
        with patch.object(module.StreamlabsClient, "info", return_value={
            "can_be_live": False, "user": {"username": "sample"},
        }):
            result = core.save_streamlabs_token("private-token")
        self.assertEqual(result, {"can_be_live": False, "username": "sample"})
        self.assertEqual(core.load_settings()["streamlabs_token"], "private-token")
        with self.assertRaisesRegex(ValueError, "tidak valid"):
            core.save_streamlabs_token("bad token")
        self.assertEqual(core.load_settings()["streamlabs_token"], "private-token")

    def test_token_renewal_accepts_same_account_not_another(self):
        core.save_settings({
            "streamlabs_token": "expired-token",
            "streamlabs_username": "sameaccount",
            "streamlabs_active": {
                "room_id": "r1", "server": "rtmp://test", "key": "secret"
            }
        })
        with patch.object(module.StreamlabsClient, "info", return_value={
            "can_be_live": True, "user": {"username": "sameaccount"}
        }):
            core.save_streamlabs_token("new-token")
        self.assertEqual(core.load_settings()["streamlabs_token"], "new-token")
        with patch.object(module.StreamlabsClient, "info", return_value={
            "can_be_live": True, "user": {"username": "otheraccount"}
        }):
            with self.assertRaisesRegex(RuntimeError, "ganti akun"):
                core.save_streamlabs_token("other-token")
        self.assertEqual(core.load_settings()["streamlabs_token"], "new-token")

    def test_streamlabs_mode_needs_no_rapidapi_or_cookies_and_reuses_room(self):
        self.assertRaisesRegex(ValueError, "Login Streamlabs",
                               core.get_credentials, "Testing", "", "streamlabs")
        core.save_settings({"streamlabs_token": "private-token"})
        with patch.object(module.StreamlabsClient, "info", return_value={"can_be_live": True}), \
             patch.object(module.StreamlabsClient, "start", return_value={
                 "room_id": "r1", "server": "rtmps://example.invalid/live", "key": "private-key",
             }) as start:
            first = core.get_credentials("Test LIVE", "", "streamlabs")
            second = core.get_credentials("Test LIVE", "", "streamlabs")
        start.assert_called_once_with("Test LIVE", category="")
        self.assertFalse(first["resumed"])
        self.assertTrue(second["resumed"])
        self.assertEqual(first["key"], second["key"])
        self.assertEqual(first["mode"], "streamlabs")
        self.assertEqual(core.load_settings()["streamlabs_active"]["room_id"], "r1")
        with patch.object(module.StreamlabsClient, "end", return_value=True) as end:
            self.assertTrue(core.end_live("", "streamlabs"))
        end.assert_called_once_with("r1")
        self.assertFalse(core.end_live("", "streamlabs"))
        self.assertNotIn("streamlabs_active", core.load_settings())

    def test_streamlabs_no_live_permission_does_not_start(self):
        core.save_settings({"streamlabs_token": "private-token"})
        with patch.object(module.StreamlabsClient, "info", return_value={
            "can_be_live": False, "application_status": {"status": "pending"},
        }), patch.object(module.StreamlabsClient, "start") as start:
            with self.assertRaisesRegex(RuntimeError, "pending"):
                core.get_credentials("Test LIVE", "", "streamlabs")
        start.assert_not_called()
        self.assertNotIn("streamlabs_active", core.load_settings())

    def test_end_error_keeps_room_for_retry(self):
        core.save_settings({"streamlabs_token": "private-token", "streamlabs_active": {
            "room_id": "r1", "server": "rtmp://server", "key": "secret"
        }})
        with patch.object(module.StreamlabsClient, "end", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                core.end_live("", "streamlabs")
        self.assertEqual(core.load_settings()["streamlabs_active"]["room_id"], "r1")

    def test_client_posts_streamlabs_fields_and_extracts_real_response(self):
        client = module.StreamlabsClient("private-token")
        class Response:
            def raise_for_status(self):
                pass
            def json(self):
                return {"id": "room-3", "rtmp": "rtmps://test.invalid/live", "key": "secret"}
        try:
            with patch.object(client.session, "request", return_value=Response()) as req:
                result = client.start("Hello", "")
            self.assertEqual(result["room_id"], "room-3")
            method, url = req.call_args.args
            self.assertEqual(method, "POST")
            self.assertTrue(url.endswith("/tiktok/stream/start"))
            fields = {name: value[1] for name, value in req.call_args.kwargs["files"]}
            self.assertEqual(fields, {"title": "Hello", "device_platform": "win32",
                                     "category": "", "audience_type": "0"})
            self.assertEqual(req.call_args.kwargs["timeout"], 25)
        finally:
            client.close()

    def test_client_rejects_incomplete_result(self):
        client = module.StreamlabsClient("private-token")
        try:
            with patch.object(client, "_json", return_value={
                "id": "r1", "rtmp": "", "key": "key"
            }):
                with self.assertRaisesRegex(RuntimeError, "tidak memberikan"):
                    client.start("Test")
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
