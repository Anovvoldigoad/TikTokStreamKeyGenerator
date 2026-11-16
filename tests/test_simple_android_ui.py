"""Offscreen Qt smoke tests for the minimal Android page (no TikTok network)."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox, QWidget

from simple_android import SimpleAndroidWindow


class SimpleAndroidUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch("simple_android.load_settings", return_value={}):
            self.window = SimpleAndroidWindow()
        self.addCleanup(self.window.close)

    def test_mode_switch_has_no_native_popup_and_does_not_block_buttons(self):
        self.assertEqual(self.window.findChildren(QComboBox), [])
        self.assertEqual(self.window.selected_mode(), "streamlabs")
        self.assertTrue(self.window.streamlabs_radio.isChecked())
        self.assertTrue(self.window.api_key.isHidden())
        self.assertFalse(self.window.streamlabs_browser_button.isHidden())
        self.window.pc_radio.click()
        self.assertEqual(self.window.selected_mode(), "pc")
        self.window.mobile_radio.click()
        self.assertEqual(self.window.selected_mode(), "mobile")
        self.window.busy(True)
        self.assertTrue(self.window.mobile_radio.isEnabled())
        self.assertTrue(self.window.pc_radio.isEnabled())
        self.assertFalse(self.window.generate_button.isEnabled())
        self.window.busy(False)
        self.assertTrue(self.window.generate_button.isEnabled())
        self.assertTrue(self.window.import_button.isEnabled())
        self.assertTrue(self.window.paste_button.isEnabled())

    def test_generate_captures_correct_mode(self):
        self.window.api_key.setText("api-key")
        self.window.pc_radio.click()
        with patch.object(self.window, "request") as request:
            self.window.generate()
            action = request.call_args.args[0]
        with patch("simple_android.get_credentials",
                   return_value={"server": "rtmp", "key": "key"}) as call:
            action()
        call.assert_called_once_with("TikTok LIVE", "api-key", "pc")

    def test_streamlabs_generate_and_end_never_require_api_key(self):
        self.assertEqual(self.window.selected_mode(), "streamlabs")
        with patch.object(self.window, "request") as request:
            self.window.generate()
            action = request.call_args.args[0]
        with patch("simple_android.get_credentials", return_value={}) as call:
            action()
        call.assert_called_once_with("TikTok LIVE", "", "streamlabs")
        self.window.last_mode = "streamlabs"
        self.window.pc_radio.click()
        with patch.object(self.window, "request") as request:
            self.window.finish_live()
            action = request.call_args.args[0]
        with patch("simple_android.end_live", return_value=True) as call:
            action()
        call.assert_called_once_with("", "streamlabs")

    def test_streamlabs_browser_login_opens_url_and_polls_success(self):
        class FakeSession:
            def __init__(self):
                self.closed = False
                self.finished = False
            def begin(self):
                return "https://streamlabs.com/slobs/login?code_flow=true"
            def ready(self):
                return True
            def expired(self):
                return False
            def exchange(self):
                return "mock-token"
            def close(self):
                self.closed = True

        session = FakeSession()
        with patch("simple_android.StreamlabsBrowserLogin", return_value=session), \
             patch.object(self.window, "open_streamlabs_browser", return_value=True) as opened:
            self.window.streamlabs_browser_button.click()
        self.assertTrue(self.window.streamlabs_timer.isActive())
        opened.assert_called_once()
        self.assertIs(self.window.streamlabs_login, session)
        with patch.object(self.window, "request") as request:
            self.window.poll_streamlabs_login()
            action, success = request.call_args.args[:2]
        with patch("simple_android.save_streamlabs_token", return_value={
            "username": "testuser", "can_be_live": True
        }) as save:
            result = action()
        save.assert_called_once_with("mock-token")
        success(result)
        self.assertIn("testuser", self.window.streamlabs_status.text())
        self.window.job = object()
        self.window.job_finished()
        self.assertTrue(session.closed)
        self.assertIsNone(self.window.streamlabs_login)

    def test_switching_modes_cancels_unneeded_login_pollers(self):
        class FakeLogin:
            def __init__(self):
                self.closed = False
            def close(self):
                self.closed = True

        streamlabs_session = FakeLogin()
        self.window.streamlabs_login = streamlabs_session
        self.window.streamlabs_timer.start()
        self.window.pc_radio.click()
        self.assertTrue(streamlabs_session.closed)
        self.assertFalse(self.window.streamlabs_timer.isActive())

        qr_session = FakeLogin()
        self.window.qr_session = qr_session
        self.window.qr_timer.start()
        self.window.streamlabs_radio.click()
        self.assertTrue(qr_session.closed)
        self.assertFalse(self.window.qr_timer.isActive())

    def test_streamlabs_token_paste_validates_before_success(self):
        self.application.clipboard().setText("private-test-token")
        with patch.object(self.window, "request") as request:
            self.window.streamlabs_paste_token_button.click()
            action, success = request.call_args.args[:2]
        with patch("simple_android.save_streamlabs_token", return_value={
            "username": "test", "can_be_live": False
        }) as save:
            result = action()
        save.assert_called_once_with("private-test-token")
        success(result)
        self.assertIn("belum tersedia", self.window.streamlabs_status.text())

    def test_end_live_preserves_mode_of_created_room(self):
        self.window.api_key.setText("api-key")
        self.window.last_mode = "mobile"
        self.window.pc_radio.click()
        with patch.object(self.window, "request") as request:
            self.window.finish_live()
            action = request.call_args.args[0]
        with patch("simple_android.end_live", return_value=True) as call:
            self.assertTrue(action())
        call.assert_called_once_with("api-key", "mobile")

    def test_qr_confirmation_cleans_up_only_after_finished(self):
        class FakeQr:
            def __init__(self):
                self.closed = False
            def close(self):
                self.closed = True

        session = FakeQr()
        self.window.qr_session = session
        self.window.job = object()
        self.window.handle_qr_status("confirmed")
        self.assertTrue(self.window.qr_complete)
        self.assertFalse(session.closed)
        self.window.job_finished()
        self.assertTrue(session.closed)
        self.assertIsNone(self.window.qr_session)
        self.assertFalse(self.window.qr_complete)

    def test_qr_poll_error_stops_retries_and_allows_cleanup(self):
        class FakeSession:
            def __init__(self):
                self.closed = False
            def close(self):
                self.closed = True

        session = FakeSession()
        self.window.qr_session = session
        self.window.qr_timer.start()
        self.window.job = object()
        self.window.handle_qr_poll_error("network unavailable")
        self.assertFalse(self.window.qr_timer.isActive())
        self.assertTrue(self.window.qr_complete)
        self.assertFalse(session.closed)
        self.window.job_finished()
        self.assertTrue(session.closed)
        self.assertIsNone(self.window.qr_session)
        self.assertIn("Coba login QR lagi", self.window.status.text())

    def test_login_qr_button_uses_rapidapi_and_renders_image(self):
        from Libs.simple_android_stream import qr_png_from_response
        png = qr_png_from_response({
            "qrcode_index_url": "https://www.tiktok.com/qr/login?next_url=test"
        })
        class FakeSession:
            def __init__(self):
                self.received_key = None
            def start(self, key):
                self.received_key = key
                return png
            def close(self):
                pass
        session = FakeSession()
        self.window.api_key.setText("private-api-key")
        with patch("simple_android.QrLoginSession", return_value=session), \
             patch.object(self.window, "request") as request:
            self.window.qr_button.click()
            action, on_success = request.call_args.args[:2]
        result = action()
        self.assertEqual(session.received_key, "private-api-key")
        on_success(result)
        self.assertFalse(self.window.qr_label.pixmap().isNull())
        self.assertEqual(self.window.qr_session, session)
        self.window.cancel_qr_login()

    def test_real_qr_image_renders_in_qt_label_without_popup(self):
        import base64
        from Libs.simple_android_stream import qr_png_from_response

        encoded = qr_png_from_response({
            "qrcode_index_url": "https://www.tiktok.com/qr/login?next_url=mock-valid"
        })
        class FakeSession:
            def __init__(self):
                self.closed = False
            def close(self):
                self.closed = True
        session = FakeSession()
        self.window.show_qr((session, encoded))
        shown = self.window.qr_label.pixmap()
        self.assertIsNotNone(shown)
        self.assertFalse(shown.isNull())
        self.assertGreater(shown.width(), 200)
        self.assertFalse(self.window.qr_label.isHidden())
        self.assertFalse(self.window.cancel_qr_button.isHidden())
        self.assertTrue(self.window.qr_timer.isActive())
        self.window.cancel_qr_login()
        self.assertTrue(session.closed)
        self.assertTrue(self.window.qr_label.isHidden())

    def test_show_qr_rejects_non_image_instead_of_fake_success(self):
        class FakeSession:
            def __init__(self):
                self.closed = False
            def close(self):
                self.closed = True
        session = FakeSession()
        self.window.show_qr((session, "cG5n"))
        self.assertTrue(session.closed)
        self.assertIsNone(self.window.qr_session)
        self.assertTrue(self.window.qr_label.isHidden())
        self.assertIn("tidak valid", self.window.status.text())

    def test_credentials_update_display_and_copy(self):
        payload = {"server": "rtmps://example.invalid/live", "key": "private-test",
                   "mode": "mobile", "resumed": False}
        self.window.show_credentials(payload)
        self.assertEqual(self.window.server.text(), payload["server"])
        self.assertTrue(self.window.copy_server.isEnabled())
        self.assertTrue(self.window.copy_key.isEnabled())
        self.window.copy_key.click()
        self.assertEqual(self.application.clipboard().text(), payload["key"])
        self.window.live_ended(True)
        self.assertFalse(self.window.copy_key.isEnabled())
        self.assertEqual(self.window.key.text(), "")

    def test_clipboard_cookie_import_is_available_without_file_picker(self):
        self.application.clipboard().setText('[{"name":"sessionid","value":"private"}]')
        with patch("simple_android.import_cookies_text", return_value="/private/cookies.json") as load:
            self.window.paste_cookies()
        load.assert_called_once()
        self.assertIn("Login tersedia", self.window.cookie_status.text())


if __name__ == "__main__":
    unittest.main()
