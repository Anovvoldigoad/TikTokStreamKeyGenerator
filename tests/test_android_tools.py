"""Offline Android button-path coverage. No TikTok calls or real LIVE."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import TiktokStreamKeyGenerator as app
from Libs import fluent_ui


class AndroidToolButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patches = (
            patch.object(app, "CONFIG_PATH", str(Path(self.temp.name) / "config.json")),
            patch.object(app, "DEFAULT_COOKIES_PATH", str(Path(self.temp.name) / "cookies.json")),
            patch.object(app, "is_android_runtime", return_value=True),
            patch.object(fluent_ui, "is_android_runtime", return_value=True),
            patch.object(app.StreamKeyGeneratorWindow, "ensure_device_identifiers", return_value=False),
            patch.object(app, "fetch_game_tags", return_value={}),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.window = app.StreamKeyGeneratorWindow()
        self.window.show()
        self.addCleanup(self.window.close)

    def test_settings_button_opens_and_closes_in_activity(self):
        dialog = self.window.settings_dialog
        QTimer.singleShot(0, dialog.accept)
        self.window.settings_button.click()
        self.assertFalse(dialog.isWindow())

    def test_message_button_result_returns_without_new_window(self):
        QTimer.singleShot(0, lambda: next(
            child for child in self.window.findChildren(fluent_ui.AccentMessageBox)
            if child.isVisible()).accept())
        self.window.show_info("Android test message")

    def test_android_login_import_opens_picker_after_dialog_closes(self):
        with patch.object(app.LoginDialog, "load_qr_code"):
            dialog = app.LoginDialog(self.window)
        with patch.object(self.window, "browse_cookies_file") as browse:
            dialog.import_android_cookies()
            browse.assert_not_called()
            QTest.qWait(40)
            browse.assert_called_once()

    def test_file_buttons_cancel_without_mutating_paths(self):
        original = self.window.get_cookies_path()
        with patch.object(app.QFileDialog, "getOpenFileName", return_value=("", "")) as picker:
            self.window.browse_cookies_file()
            self.window.browse_image()
        self.assertEqual(picker.call_count, 2)
        self.assertEqual(self.window.get_cookies_path(), original)

    def test_device_settings_button_handles_cancel(self):
        with patch.object(app.DeviceSettingsDialog, "exec",
                          return_value=QDialog.DialogCode.Rejected):
            self.window.device_settings_button.setEnabled(True)
            self.window.device_settings_button.click()


if __name__ == "__main__":
    unittest.main()
