"""Construct the real Qt window in Android mode without any network calls.

Offscreen Linux verifies Python/UI startup and first-run client selection, not
Android's native QPA or actual phone display.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

import TiktokStreamKeyGenerator as app_module


class AndroidGuiStartupContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_android_does_not_launch_timed_modal_startup_prompts(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(app_module, "CONFIG_PATH", str(Path(root) / "config.json")), \
                 patch.object(app_module, "DEFAULT_COOKIES_PATH", str(Path(root) / "cookies.json")), \
                 patch.object(app_module, "is_android_runtime", return_value=True), \
                 patch.object(app_module, "single_shot") as schedule, \
                 patch.object(app_module.StreamKeyGeneratorWindow,
                              "ensure_device_identifiers", return_value=False):
                window = app_module.StreamKeyGeneratorWindow()
                try:
                    named = {(call.args[1], getattr(call.args[2], "__name__", ""))
                             for call in schedule.call_args_list}
                    self.assertIn((0, "load_game_tags"), named)
                    self.assertNotIn((3000, "show_donation_reminder"), named)
                    self.assertNotIn((6000, "check_updates_on_startup"), named)
                finally:
                    window.close()

    def test_first_run_can_open_main_window_with_pc_signing_selected(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(app_module, "CONFIG_PATH", str(Path(root) / "config.json")), \
                 patch.object(app_module, "DEFAULT_COOKIES_PATH", str(Path(root) / "cookies.json")), \
                 patch.object(app_module.StreamKeyGeneratorWindow,
                              "ensure_device_identifiers", return_value=False):
                window = app_module.StreamKeyGeneratorWindow()
                try:
                    self.assertEqual(window.device_type, "pc")
                    self.assertEqual(window.device_type_combo.currentData(), "pc")
                    self.assertTrue(window.go_live_button is not None)
                    self.assertTrue(window.url_output is not None)
                    self.assertTrue(window.key_output is not None)
                finally:
                    window.close()


if __name__ == "__main__":
    unittest.main()
