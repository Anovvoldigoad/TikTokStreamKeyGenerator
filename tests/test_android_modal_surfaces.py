"""Android event loops: modal surfaces must remain child widgets.

Offscreen Qt verifies widget hierarchy and button results only. It cannot
prove that Android's native EGL compositor is crash-free.
"""
import os
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget, QPushButton

from Libs import fluent_ui


class AndroidModalSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.android = patch.object(fluent_ui, "is_android_runtime", return_value=True)
        self.android.start()
        self.host = QWidget()
        self.host.resize(400, 700)
        self.host.show()

    def tearDown(self):
        self.host.close()
        self.android.stop()

    def test_dialog_accept_is_embedded_and_returns_accepted(self):
        dialog = fluent_ui.AccentDialog(self.host)
        QTimer.singleShot(0, dialog.accept)
        self.assertEqual(dialog.exec(), dialog.Accepted)
        self.assertFalse(dialog.isWindow())

    def test_messagebox_button_result_without_native_popup(self):
        message = fluent_ui.AccentMessageBox(self.host)
        message.setStandardButtons(message.Yes | message.No)
        QTimer.singleShot(0, lambda: message.button(message.Yes).click())
        self.assertEqual(message.exec(), message.Yes)
        self.assertFalse(message.isWindow())

    def test_combo_item_still_updates_selection(self):
        combo = fluent_ui.ComboBox(self.host)
        combo.addItem("PC", "pc")
        combo.addItem("Android", "mobile")

        def choose():
            buttons = self.host.findChildren(QPushButton)
            next(button for button in buttons if button.text() == "Android").click()

        QTimer.singleShot(0, choose)
        combo._showComboMenu()
        self.assertEqual(combo.currentData(), "mobile")

    def test_menu_action_is_triggered_without_native_popup(self):
        menu = fluent_ui.RoundMenu("Actions", self.host)
        selected = []
        action = fluent_ui.Action("Inspect", self.host)
        action.triggered.connect(lambda: selected.append("inspect"))
        menu.addAction(action)

        QTimer.singleShot(0, lambda: next(
            button for button in self.host.findChildren(QPushButton)
            if button.text() == "Inspect").click())
        menu.exec(self.host.mapToGlobal(self.host.rect().center()))
        self.assertEqual(selected, ["inspect"])


if __name__ == "__main__":
    unittest.main()
