"""Small, non-Fluent Android UI for TikTok LIVE RTMP credentials."""
import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from Libs.simple_android_stream import (
    end_live, get_credentials, import_cookies, load_settings,
)


class RequestThread(QThread):
    result_ready = Signal(object)
    error_ready = Signal(str)

    def __init__(self, action):
        super().__init__()
        self.action = action

    def run(self):
        try:
            self.result_ready.emit(self.action())
        except Exception as exc:
            # Never log credentials or session cookies to public CI output.
            self.error_ready.emit(str(exc))


class SimpleAndroidWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TikTok RTMP & Stream Key")
        self.setMinimumWidth(310)
        self.job = None
        self.server_value = ""
        self.key_value = ""

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        heading = QLabel("TikTok LIVE • RTMP & Stream Key")
        heading.setStyleSheet("font-size: 19px; font-weight: bold")
        layout.addWidget(heading)
        hint = QLabel("Hanya untuk akun yang punya akses LIVE. "
                      "RapidAPI signer diperlukan. Login lewat cookies JSON akun sendiri.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.cookie_status = QLabel("Cookies belum diimpor")
        self.cookie_status.setWordWrap(True)
        layout.addWidget(self.cookie_status)
        self.import_button = QPushButton("Impor Cookies TikTok (.json)")
        self.import_button.clicked.connect(self.choose_cookies)
        layout.addWidget(self.import_button)

        layout.addWidget(QLabel("RapidAPI Signer Key"))
        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText("Tempel RapidAPI key")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.api_key)

        layout.addWidget(QLabel("Judul LIVE"))
        self.title = QLineEdit("TikTok LIVE")
        self.title.setMaxLength(32)
        layout.addWidget(self.title)

        self.generate_button = QPushButton("Ambil RTMP & Stream Key")
        self.generate_button.clicked.connect(self.generate)
        layout.addWidget(self.generate_button)

        layout.addWidget(QLabel("RTMP Server (TikTok)"))
        self.server = QLineEdit()
        self.server.setReadOnly(True)
        self.server.setPlaceholderText("Belum tersedia")
        layout.addWidget(self.server)
        self.copy_server = QPushButton("Salin RTMP")
        self.copy_server.clicked.connect(lambda: self.copy_value(self.server_value))
        self.copy_server.setEnabled(False)
        layout.addWidget(self.copy_server)

        layout.addWidget(QLabel("Stream Key"))
        self.key = QLineEdit()
        self.key.setReadOnly(True)
        self.key.setPlaceholderText("Belum tersedia")
        layout.addWidget(self.key)
        self.copy_key = QPushButton("Salin Stream Key")
        self.copy_key.clicked.connect(lambda: self.copy_value(self.key_value))
        self.copy_key.setEnabled(False)
        layout.addWidget(self.copy_key)

        self.end_button = QPushButton("Akhiri Room LIVE")
        self.end_button.clicked.connect(self.finish_live)
        layout.addWidget(self.end_button)

        warning = QLabel(
            "PENTING: Ini kredensial asli yang diterima dari TikTok, "
            "bukan alamat proxy. Generator sumber menyatakan koneksi "
            "langsung OBS/encoder belum didukung dan bisa dibatasi TikTok."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        self.status = QLabel("Siap.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()

        settings = load_settings()
        if settings.get("cookies_path"):
            self.cookie_status.setText("Cookies telah disimpan di penyimpanan privat aplikasi.")
        if settings.get("rapidapi_key"):
            self.api_key.setText(settings["rapidapi_key"])

    def choose_cookies(self):
        if self.job is not None:
            return
        selected, _ = QFileDialog.getOpenFileName(self, "Pilih cookies TikTok", "", "JSON (*.json)")
        if not selected:
            return
        try:
            import_cookies(selected)
        except Exception as exc:
            self.status.setText("Gagal impor cookies: " + str(exc))
            return
        self.cookie_status.setText("Cookies TikTok berhasil diimpor.")
        self.status.setText("Cookies siap.")

    def busy(self, value):
        for button in (self.import_button, self.generate_button, self.end_button):
            button.setEnabled(not value)

    def request(self, action, on_success, message):
        if self.job is not None:
            return
        self.status.setText(message)
        self.busy(True)
        job = RequestThread(action)
        self.job = job
        job.result_ready.connect(on_success)
        job.error_ready.connect(lambda detail: self.status.setText("Gagal: " + detail))
        job.finished.connect(self.job_finished)
        job.start()

    def job_finished(self):
        self.job = None
        self.busy(False)

    def generate(self):
        # Do not retain an old key if a new room request fails.
        self.clear_credentials()
        title = self.title.text()
        api_key = self.api_key.text()
        self.request(lambda: get_credentials(title, api_key),
                     self.show_credentials, "Menghubungi TikTok…")

    def show_credentials(self, payload):
        self.server_value = payload["server"]
        self.key_value = payload["key"]
        self.server.setText(self.server_value)
        self.key.setText(self.key_value)
        self.copy_server.setEnabled(True)
        self.copy_key.setEnabled(True)
        self.status.setText(
            ("Room LIVE lama digunakan kembali." if payload["resumed"]
             else "Room LIVE baru dibuat.") + " Gunakan dengan hati-hati."
        )

    def finish_live(self):
        api_key = self.api_key.text()
        self.request(lambda: end_live(api_key), self.live_ended,
                     "Mengakhiri room LIVE…")

    def live_ended(self, ended):
        self.clear_credentials()
        self.status.setText("Room LIVE diakhiri." if ended else "Tidak ada room LIVE aktif.")

    def clear_credentials(self):
        self.server_value = ""
        self.key_value = ""
        self.server.clear()
        self.key.clear()
        self.copy_server.setEnabled(False)
        self.copy_key.setEnabled(False)

    def copy_value(self, value):
        if value:
            QApplication.clipboard().setText(value)
            self.status.setText("Berhasil disalin. Jangan bagikan stream key.")

    def closeEvent(self, event):
        if self.job is not None:
            event.ignore()
            self.status.setText("Selesaikan permintaan sebelum menutup aplikasi.")
            return
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = SimpleAndroidWindow()
    window.resize(400, 690)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
