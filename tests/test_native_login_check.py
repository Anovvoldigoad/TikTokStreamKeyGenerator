"""No-RapidAPI, read-only TikTok web login probe; mocked network only."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from Libs import simple_android_stream as core


def reply(payload, code=200):
    return SimpleNamespace(status_code=code, json=lambda: payload)


class NativeLoginCheckTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        patcher = patch.object(core, "user_data_dir", return_value=str(self.data))
        patcher.start()
        self.addCleanup(patcher.stop)

    def setup_cookies(self, entries):
        path = self.data / "cookies.json"
        path.write_text(json.dumps(entries), encoding="utf-8")
        core.save_settings({"cookies_path": str(path)})

    def test_session_valid_uses_only_official_tiktok_domain(self):
        self.setup_cookies([
            {"name": "sessionid", "value": "private", "domain": ".tiktok.com"},
            {"name": "tt_csrf_token", "value": "csrf", "domain": "www.tiktok.com"},
            {"name": "unsafe", "value": "not-to-send", "domain": "example.com"},
        ])
        with patch("requests.get", return_value=reply({
            "message": "success",
            "data": {"user_id_str": "1234", "username": "example"},
        })) as request:
            info = core.check_native_login_session()
        self.assertEqual(info, {"state": "valid", "username": "example"})
        self.assertEqual(request.call_args.args[0], "https://www.tiktok.com/passport/web/account/info/")
        self.assertEqual(request.call_args.kwargs["cookies"],
                         {"sessionid": "private", "tt_csrf_token": "csrf"})
        self.assertFalse(request.call_args.kwargs["allow_redirects"])
        self.assertEqual(request.call_args.kwargs["timeout"], 15)

    def test_expired_token_is_not_reported_as_authenticated(self):
        self.setup_cookies([{"name": "sessionid", "value": "expired"}])
        with patch("requests.get", return_value=reply({
            "message": "error", "data": {"error_code": 13, "name": "session_expired"}
        })):
            self.assertEqual(core.check_native_login_session(), {
                "state": "expired", "username": ""
            })

    def test_missing_cookie_refuses_network(self):
        with patch("requests.get") as request:
            with self.assertRaisesRegex(ValueError, "Impor cookies"):
                core.check_native_login_session()
        request.assert_not_called()

    def test_offsite_cookie_does_not_leave_application(self):
        self.setup_cookies([{"name": "sessionid", "value": "secret", "domain": "example.com"}])
        with patch("requests.get") as request:
            with self.assertRaisesRegex(ValueError, "domain tiktok.com"):
                core.check_native_login_session()
        request.assert_not_called()

    def test_ambiguous_response_is_not_false_success(self):
        self.setup_cookies([{"name": "sessionid", "value": "private"}])
        with patch("requests.get", return_value=reply({"message": "success", "data": {}})):
            with self.assertRaisesRegex(RuntimeError, "belum mengonfirmasi"):
                core.check_native_login_session()
        with patch("requests.get", return_value=reply({}, code=403)):
            with self.assertRaisesRegex(RuntimeError, "Status login belum bisa dipastikan"):
                core.check_native_login_session()
        with patch("requests.get", return_value=SimpleNamespace(
            status_code=200, json=lambda: (_ for _ in ()).throw(ValueError())
        )):
            with self.assertRaisesRegex(RuntimeError, "non-JSON"):
                core.check_native_login_session()


if __name__ == "__main__":
    unittest.main()
