"""Android event loops: modal surfaces must remain child widgets.

Offscreen Qt verifies widget hierarchy and button results only. It cannot
prove that Android's native EGL compositor is crash-free.
"""
import os
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QDialog, QMessageBox

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
        self.assertEqual(dialog.exec(), QDialog.DialogCode.Accepted)
        self.assertFalse(dialog.isWindow())

    def test_open_dialog_tracks_activity_resize(self):
        dialog = fluent_ui.AccentDialog(self.host)
        dialog.show()
        sheet = dialog._android_sheet
        self.assertEqual(sheet.geometry(), self.host.rect())
        self.host.resize(560, 910)
        QApplication.processEvents()
        self.assertEqual(sheet.geometry(), self.host.rect())
        dialog.hide()
        self.assertIsNone(dialog._android_resize_filter)

    def test_messagebox_button_result_without_native_popup(self):
        message = fluent_ui.AccentMessageBox(self.host)
        message.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        QTimer.singleShot(0, lambda: message.button(QMessageBox.Yes).click())
        self.assertEqual(message.exec(), QMessageBox.Yes)
        self.assertFalse(message.isWindow())

    def test_static_critical_uses_embedded_dialog(self):
        seen = []

        def choose():
            dialog = next(child for child in self.host.findChildren(fluent_ui.AccentMessageBox)
                          if child.isVisible())
            seen.append(dialog.isWindow())
            dialog.button(QMessageBox.Ok).click()

        QTimer.singleShot(0, choose)
        self.assertEqual(fluent_ui.AccentMessageBox.critical(self.host, "Error", "Test"), QMessageBox.Ok)
        self.assertEqual(seen, [False])

    def test_static_information_uses_embedded_dialog(self):
        seen = []

        def choose():
            dialog = next(child for child in self.host.findChildren(fluent_ui.AccentMessageBox)
                          if child.isVisible())
            seen.append(dialog.isWindow())
            dialog.button(QMessageBox.Ok).click()

        QTimer.singleShot(0, choose)
        self.assertEqual(fluent_ui.AccentMessageBox.information(self.host, "Info", "Test"), QMessageBox.Ok)
        self.assertEqual(seen, [False])

    def test_static_question_preserves_button_result(self):
        seen = []

        def choose():
            dialog = next(child for child in self.host.findChildren(fluent_ui.AccentMessageBox)
                          if child.isVisible())
            seen.append(dialog.isWindow())
            self.assertEqual(dialog.defaultButton(), dialog.button(QMessageBox.No))
            dialog.button(QMessageBox.No).click()

        QTimer.singleShot(0, choose)
        result = fluent_ui.AccentMessageBox.question(
            self.host, "End LIVE?", "Confirm?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        self.assertEqual(result, QMessageBox.No)
        self.assertEqual(seen, [False])

    def test_background_progress_dialog_does_not_make_native_window(self):
        from Libs.gui_tasks import BusyDialog
        progress = BusyDialog(self.host, "Loading")
        progress.show()
        self.assertFalse(progress.isWindow())
        self.assertIsNotNone(progress._android_sheet)
        self.assertTrue(progress._android_sheet.isVisible())
        self.assertNotIn(
            "Close", [button.text() for button in
                      progress._android_sheet.findChildren(QPushButton)]
        )
        progress.hide()
        self.assertIsNone(progress._android_sheet)

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

    def test_nested_workspace_menu_action_is_accessible(self):
        root = fluent_ui.RoundMenu("Workspace", self.host)
        submenu = fluent_ui.CheckableMenu("Views", root)
        selected = []
        action = fluent_ui.Action("Audience", self.host)
        action.setCheckable(True)
        action.setChecked(True)
        action.toggled.connect(lambda enabled: selected.append(enabled))
        submenu.addAction(action)
        root.addMenu(submenu)

        def choose_menu():
            QTimer.singleShot(0, lambda: next(
                child for child in self.host.findChildren(QPushButton)
                if child.text() == "Audience").click())
            next(child for child in self.host.findChildren(QPushButton)
                 if child.text() == "Views").click()

        QTimer.singleShot(0, choose_menu)
        root.exec(self.host.mapToGlobal(self.host.rect().center()))
        self.assertEqual(selected, [False])
        self.assertFalse(root.isVisible())

    def test_mixed_menu_preserves_submenu_and_action_order(self):
        root = fluent_ui.RoundMenu("Workspace", self.host)
        first = fluent_ui.Action("Settings", self.host)
        root.addAction(first)
        submenu = fluent_ui.CheckableMenu("Views", root)
        submenu.addAction(fluent_ui.Action("Audience", self.host))
        root.addMenu(submenu)
        last = fluent_ui.Action("Copy", self.host)
        root.addAction(last)

        observed = []

        def choose():
            buttons = [button.text() for button in self.host.findChildren(QPushButton)]
            observed.extend(name for name in buttons if name in {"Settings", "Views", "Copy"})
            next(button for button in self.host.findChildren(QPushButton)
                 if button.text() == "Copy").click()

        QTimer.singleShot(0, choose)
        root.exec(self.host.mapToGlobal(self.host.rect().center()))
        self.assertEqual(observed, ["Settings", "Views", "Copy"])

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
