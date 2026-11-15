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
