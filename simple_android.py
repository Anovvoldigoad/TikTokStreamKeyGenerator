"""Minimal Android UI for TikTok LIVE credentials, with no popup mode selector."""
import base64
import sys

from PySide6.QtCore import QThread, QTimer, Signal, Qt, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QLabel, QLineEdit,
    QPushButton, QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from Libs.simple_android_stream import (
    QrLoginSession, end_live, get_credentials, import_cookies,
    import_cookies_text, load_settings, save_streamlabs_token,
    check_native_login_session,
)
from Libs.streamlabs_android import StreamlabsBrowserLogin
from Libs.native_unsigned_android import (
    check_native_studio, heartbeat_native_studio, mark_native_studio_streaming,
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
            # Account credentials never go to the debug console.
            self.error_ready.emit(str(exc))


class SimpleAndroidWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TikTok RTMP & Stream Key")
        self.setMinimumWidth(300)
        self.job = None
        self.qr_session = None
        self.qr_complete = False
        self.streamlabs_login = None
        self.streamlabs_login_url = ""
        self.streamlabs_complete = False
        self.server_value = ""
        self.key_value = ""
        self.last_mode = None
        self.native_room_active = False

        outer = QVBoxLayout(self)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setSpacing(10)

        heading = QLabel("TikTok LIVE • RTMP & Stream Key")
        heading.setStyleSheet("font-size: 19px; font-weight: bold")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.hint = QLabel(
            "Pakai akun TikTok yang pernah LIVE Studio. Cek sesi web bisa "
            "tanpa RapidAPI, tetapi membuat RTMP/key masih memerlukan signer."
        )
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        self.streamlabs_status = QLabel("Streamlabs belum login.")
        self.streamlabs_status.setWordWrap(True)
        layout.addWidget(self.streamlabs_status)

        self.streamlabs_browser_button = QPushButton("Login Streamlabs lewat Browser")
        self.streamlabs_browser_button.clicked.connect(self.begin_streamlabs_login)
        layout.addWidget(self.streamlabs_browser_button)
        self.streamlabs_copy_link_button = QPushButton("Salin Link Login Streamlabs")
        self.streamlabs_copy_link_button.clicked.connect(self.copy_streamlabs_login_url)
        self.streamlabs_copy_link_button.hide()
        layout.addWidget(self.streamlabs_copy_link_button)
        self.streamlabs_cancel_button = QPushButton("Batalkan Login Streamlabs")
        self.streamlabs_cancel_button.clicked.connect(self.cancel_streamlabs_login)
        self.streamlabs_cancel_button.hide()
        layout.addWidget(self.streamlabs_cancel_button)
        self.streamlabs_paste_token_button = QPushButton(
            "Tempel Token Streamlabs dari Clipboard"
        )
        self.streamlabs_paste_token_button.clicked.connect(self.paste_streamlabs_token)
        layout.addWidget(self.streamlabs_paste_token_button)

        self.cookie_status = QLabel("Belum login TikTok.")
        self.cookie_status.setWordWrap(True)
        layout.addWidget(self.cookie_status)
        self.native_check_button = QPushButton("Cek Sesi TikTok (tanpa RapidAPI)")
        self.native_check_button.clicked.connect(self.check_native_login)
        layout.addWidget(self.native_check_button)
        self.native_check_status = QLabel("Sesi akun TikTok belum diperiksa.")
        self.native_check_status.setWordWrap(True)
        layout.addWidget(self.native_check_status)
        self.studio_check_button = QPushButton("Cek Izin LIVE Studio (tanpa RapidAPI)")
        self.studio_check_button.clicked.connect(self.check_unsigned_studio)
        layout.addWidget(self.studio_check_button)
        self.studio_check_status = QLabel("Izin LIVE Studio belum diperiksa.")
        self.studio_check_status.setWordWrap(True)
        layout.addWidget(self.studio_check_status)

        self.api_label = QLabel("RapidAPI Signer Key")
        layout.addWidget(self.api_label)
        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText("Tempel RapidAPI key")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.api_key)

        self.qr_button = QPushButton("Login TikTok lewat QR")
        self.qr_button.clicked.connect(self.start_qr_login)
        layout.addWidget(self.qr_button)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setMinimumHeight(240)
        self.qr_label.hide()
        layout.addWidget(self.qr_label)
        self.qr_help = QLabel("Scan QR dari aplikasi TikTok di perangkat lain. "
                              "Kalau hanya punya satu HP, impor cookies JSON di bawah.")
        self.qr_help.setWordWrap(True)
        self.qr_help.hide()
        layout.addWidget(self.qr_help)
        self.cancel_qr_button = QPushButton("Batalkan login QR")
        self.cancel_qr_button.clicked.connect(self.cancel_qr_login)
        self.cancel_qr_button.hide()
        layout.addWidget(self.cancel_qr_button)

        self.import_button = QPushButton("Impor Cookies TikTok (.json)")
        self.import_button.clicked.connect(self.choose_cookies)
        layout.addWidget(self.import_button)
        self.paste_button = QPushButton("Tempel Cookies JSON dari Clipboard")
        self.paste_button.clicked.connect(self.paste_cookies)
        layout.addWidget(self.paste_button)

        layout.addWidget(QLabel("Sumber izin LIVE"))
        # Avoid QComboBox's separate popup surface on Qt Android; it can trap
        # input after selecting an item on certain Android 16 builds.
        self.unsigned_radio = QRadioButton(
            "LIVE Studio tanpa RapidAPI (eksperimental)"
        )
        self.streamlabs_radio = QRadioButton("Streamlabs (opsional)")
        self.mobile_radio = QRadioButton("Android LIVE (memerlukan signer)")
        self.pc_radio = QRadioButton("PC LIVE Studio (memerlukan signer)")
        self.mode_buttons = QButtonGroup(self)
        self.mode_buttons.setExclusive(True)
        self.mode_buttons.addButton(self.streamlabs_radio)
        self.mode_buttons.addButton(self.mobile_radio)
        self.mode_buttons.addButton(self.pc_radio)
        self.mode_buttons.addButton(self.unsigned_radio)
        self.unsigned_radio.setChecked(True)
        layout.addWidget(self.unsigned_radio)
        layout.addWidget(self.pc_radio)
        layout.addWidget(self.mobile_radio)
        layout.addWidget(self.streamlabs_radio)
        for button in (
            self.unsigned_radio, self.streamlabs_radio, self.mobile_radio, self.pc_radio
        ):
            button.toggled.connect(self.update_mode_visibility)

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
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Belum tersedia")
        layout.addWidget(self.key)
        self.copy_key = QPushButton("Salin Stream Key")
        self.copy_key.clicked.connect(lambda: self.copy_value(self.key_value))
        self.copy_key.setEnabled(False)
        layout.addWidget(self.copy_key)

        self.end_button = QPushButton("Akhiri Room LIVE")
        self.end_button.clicked.connect(self.finish_live)
        layout.addWidget(self.end_button)
        self.native_streaming_button = QPushButton("Encoder sudah mengirim video")
        self.native_streaming_button.clicked.connect(self.mark_native_streaming)
        self.native_streaming_button.hide()
        layout.addWidget(self.native_streaming_button)

        self.warning = QLabel(
            "Mode Android/PC asli mengembalikan key yang mungkin memerlukan "
            "metadata dan proxy untuk streaming. Mode Streamlabs memakai "
            "RTMP/key dari API Streamlabs bila akun diizinkan."
        )
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)

        self.status = QLabel("Siap.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()

        self.qr_timer = QTimer(self)
        self.qr_timer.setInterval(3000)
        self.qr_timer.timeout.connect(self.poll_qr_login)
        self.streamlabs_timer = QTimer(self)
        self.streamlabs_timer.setInterval(1000)
        self.streamlabs_timer.timeout.connect(self.poll_streamlabs_login)
        self.native_heartbeat_timer = QTimer(self)
        self.native_heartbeat_timer.setInterval(5000)
        self.native_heartbeat_timer.timeout.connect(self.send_native_heartbeat)

        settings = load_settings()
        if settings.get("cookies_path"):
            self.cookie_status.setText("Cookies tersimpan di penyimpanan privat aplikasi.")
        if settings.get("rapidapi_key"):
            self.api_key.setText(settings["rapidapi_key"])
        if settings.get("streamlabs_token"):
            self.streamlabs_status.setText("Token Streamlabs tersimpan privat.")
        if settings.get("native_unsigned_room"):
            # Only room IDs/host survive a restart; never invent old RTMP keys.
            self.native_room_active = True
            self.last_mode = "native_unsigned"
            self.status.setText(
                "Room LIVE Studio lama terdeteksi setelah aplikasi dibuka ulang. "
                "Tekan 'Akhiri Room LIVE' sebelum membuat room baru. "
                "RTMP/key lama tidak disimpan."
            )
        self.update_mode_visibility()

    def selected_mode(self):
        if self.unsigned_radio.isChecked():
            return "native_unsigned"
        if self.streamlabs_radio.isChecked():
            return "streamlabs"
        return "mobile" if self.mobile_radio.isChecked() else "pc"

    def update_mode_visibility(self):
        streamlabs = self.selected_mode() == "streamlabs"
        self.streamlabs_status.setVisible(streamlabs)
        for widget in (self.streamlabs_browser_button, self.streamlabs_paste_token_button):
            widget.setVisible(streamlabs)
        self.streamlabs_copy_link_button.setVisible(streamlabs and bool(self.streamlabs_login))
        self.streamlabs_cancel_button.setVisible(streamlabs and bool(self.streamlabs_login))
        unsigned = self.selected_mode() == "native_unsigned"
        for widget in (self.cookie_status, self.native_check_button,
                       self.native_check_status, self.import_button, self.paste_button):
            widget.setVisible(not streamlabs)
        for widget in (self.studio_check_button, self.studio_check_status):
            widget.setVisible(unsigned)
        for widget in (self.api_label, self.api_key, self.qr_button):
            widget.setVisible(not streamlabs and not unsigned)
        if streamlabs:
            # Do not keep consuming RapidAPI quota after switching to Streamlabs.
            self.qr_timer.stop()
            if self.qr_session is not None:
                if self.job is None:
                    self.cancel_qr_login(clear_status=False)
                else:
                    self.qr_complete = True
            self.qr_label.hide()
            self.qr_help.hide()
            self.cancel_qr_button.hide()
        elif self.streamlabs_login is not None:
            self.streamlabs_timer.stop()
            if self.job is None:
                self.cancel_streamlabs_login(clear_status=False)
            else:
                self.streamlabs_complete = True
        if not streamlabs and self.qr_session is not None:
            self.qr_label.show()
            self.qr_help.show()
            self.cancel_qr_button.show()
        self.hint.setText(
            "Mode eksperimen: memakai cookies TikTok dan LIVE Studio API "
            "tanpa RapidAPI. Server bisa menolak request pada akun Indonesia."
            if unsigned else (
                "Streamlabs opsional, tidak memerlukan RapidAPI."
                if streamlabs else
                "Mode LIVE Studio asli ini masih membutuhkan signer RapidAPI."
            )
        )

    def check_unsigned_studio(self):
        if self.job is not None:
            return
        self.request(
            check_native_studio, self.show_studio_preflight,
            "Memeriksa izin LIVE Studio tanpa RapidAPI…",
        )

    def show_studio_preflight(self, result):
        if result.get("allowed"):
            self.studio_check_status.setText(
                "Precheck TikTok diterima (" + str(result.get("host")) + ")."
            )
            self.status.setText(
                "Precheck diterima. Ini belum menjamin server akan mengizinkan "
                "pembuatan room atau menerima stream video."
            )
        else:
            self.studio_check_status.setText(
                "Precheck ditolak (status_code="
                + str(result.get("status_code")) + ")."
            )
            self.status.setText("Akses LIVE Studio belum diterima pada jalur tanpa RapidAPI.")

    def send_native_heartbeat(self):
        if self.job is None and self.native_room_active:
            self.request(
                heartbeat_native_studio, self.native_heartbeat_sent,
                "Menjaga room LIVE Studio tetap aktif…",
                on_error=self.native_heartbeat_error,
            )

    def native_heartbeat_sent(self, ok):
        if ok:
            self.status.setText("Room LIVE Studio terhubung. Heartbeat diterima.")

    def native_heartbeat_error(self, message):
        self.status.setText(
            "Heartbeat gagal: " + message + ". Segera akhiri LIVE jika tidak bisa dipulihkan."
        )

    def mark_native_streaming(self):
        if not self.native_room_active:
            return
        try:
            mark_native_studio_streaming()
        except RuntimeError as exc:
            self.status.setText(str(exc))
            return
        self.native_streaming_button.setEnabled(False)
        self.status.setText("Encoder ditandai aktif. TikTok akan menerima heartbeat LIVE.")
        self.send_native_heartbeat()

    def begin_streamlabs_login(self):
        if self.job is not None:
            return
        self.cancel_streamlabs_login(clear_status=False)
        session = StreamlabsBrowserLogin()
        try:
            url = session.begin()
        except Exception as exc:
            self.status.setText("Tidak dapat membuka login Streamlabs: " + str(exc))
            session.close()
            return
        self.streamlabs_login = session
        self.streamlabs_login_url = url
        self.streamlabs_copy_link_button.show()
        self.streamlabs_cancel_button.show()
        self.streamlabs_timer.start()
        opened = self.open_streamlabs_browser(url)
        if opened:
            self.status.setText(
                "Login di browser, pilih TikTok dan izinkan Streamlabs. "
                "Kembali ke aplikasi setelah selesai."
            )
        else:
            self.status.setText(
                "Browser tidak terbuka. Tekan 'Salin Link Login Streamlabs' "
                "dan buka URL di browser Android."
            )

    def open_streamlabs_browser(self, url):
        return QDesktopServices.openUrl(QUrl(url))

    def copy_streamlabs_login_url(self):
        if self.streamlabs_login_url:
            QApplication.clipboard().setText(self.streamlabs_login_url)
            self.status.setText("Link login disalin. Buka di browser HP ini.")

    def cancel_streamlabs_login(self, clear_status=True):
        if self.job is not None:
            return
        self.streamlabs_timer.stop()
        if self.streamlabs_login is not None:
            self.streamlabs_login.close()
            self.streamlabs_login = None
        self.streamlabs_login_url = ""
        self.streamlabs_copy_link_button.hide()
        self.streamlabs_cancel_button.hide()
        if clear_status:
            self.status.setText("Login Streamlabs dibatalkan.")

    def poll_streamlabs_login(self):
        session = self.streamlabs_login
        if session is None or self.job is not None:
            return
        if session.expired():
            self.cancel_streamlabs_login(clear_status=False)
            self.status.setText("Login Streamlabs kedaluwarsa. Mulai login lagi.")
            return
        if session.ready():
            self.streamlabs_timer.stop()
            self.request(
                lambda: save_streamlabs_token(session.exchange()),
                self.streamlabs_logged_in,
                "Memeriksa izin TikTok LIVE melalui Streamlabs…",
                on_error=self.streamlabs_login_error,
            )

    def paste_streamlabs_token(self):
        if self.job is not None:
            return
        token = QApplication.clipboard().text().strip()
        self.request(
            lambda: save_streamlabs_token(token),
            self.streamlabs_logged_in,
            "Memvalidasi token Streamlabs…",
        )

    def streamlabs_logged_in(self, info):
        username = info.get("username") or "akun TikTok"
        allowed = bool(info.get("can_be_live"))
        self.streamlabs_status.setText(
            ("Siap LIVE melalui Streamlabs: " if allowed else
             "Login berhasil; izin LIVE belum tersedia: ") + username
        )
        self.status.setText(
            "Login Streamlabs berhasil. Kamu bisa ambil RTMP & Stream Key."
            if allowed else
            "Login berhasil, tetapi TikTok belum mengizinkan LIVE melalui Streamlabs."
        )
        if self.streamlabs_login is not None:
            self.streamlabs_complete = True

    def streamlabs_login_error(self, message):
        self.status.setText("Login Streamlabs gagal: " + message)
        self.streamlabs_complete = True

    def check_native_login(self):
        if self.job is not None:
            return
        self.request(
            check_native_login_session,
            self.show_native_login_result,
            "Memeriksa sesi akun TikTok (tanpa RapidAPI)…",
        )

    def show_native_login_result(self, result):
        if result.get("state") == "valid":
            username = result.get("username") or "akun TikTok"
            self.native_check_status.setText(
                "Sesi web TikTok aktif: " + username
            )
            self.status.setText(
                "Sesi web terverifikasi. Ini BELUM memastikan izin LIVE Studio "
                "atau tersedianya Stream Key."
            )
        elif result.get("state") == "expired":
            self.native_check_status.setText("Sesi TikTok kedaluwarsa.")
            self.status.setText("Login TikTok sudah kedaluwarsa. Impor cookies baru.")
        else:
            self.native_check_status.setText("Status sesi tidak dapat dipastikan.")

    def choose_cookies(self):
        if self.job is not None:
            return
        selected, _ = QFileDialog.getOpenFileName(
            self, "Pilih cookies TikTok", "", "JSON (*.json)"
        )
        if not selected:
            return
        try:
            import_cookies(selected)
        except Exception as exc:
            self.status.setText("Gagal impor cookies: " + str(exc))
            return
        self.cookie_status.setText("Login tersedia melalui cookies JSON.")
        self.status.setText("Cookies siap dipakai.")

    def paste_cookies(self):
        if self.job is not None:
            return
        try:
            import_cookies_text(QApplication.clipboard().text())
        except Exception as exc:
            self.status.setText("Gagal tempel cookies: " + str(exc))
            return
        self.cookie_status.setText("Login tersedia melalui cookies JSON.")
        self.status.setText("Cookies disimpan secara privat.")

    def busy(self, value):
        for button in (self.import_button, self.paste_button, self.qr_button,
                       self.native_check_button, self.studio_check_button,
                       self.native_streaming_button, self.generate_button,
                       self.end_button, self.cancel_qr_button,
                       self.streamlabs_browser_button, self.streamlabs_paste_token_button,
                       self.streamlabs_cancel_button, self.streamlabs_copy_link_button):
            button.setEnabled(not value)
        # Radio buttons remain interactive while requests run. The request
        # already captures the selected mode on the GUI thread.

    def request(self, action, on_success, message, on_error=None):
        if self.job is not None:
            return
        self.status.setText(message)
        self.busy(True)
        job = RequestThread(action)
        self.job = job
        job.result_ready.connect(on_success)
        job.error_ready.connect(on_error or self.show_request_error)
        job.finished.connect(self.job_finished)
        job.finished.connect(job.deleteLater)
        job.start()

    def show_request_error(self, message):
        self.status.setText("Gagal: " + message)

    def job_finished(self):
        self.job = None
        self.busy(False)
        if self.qr_complete:
            self.qr_complete = False
            self.cancel_qr_login(clear_status=False)
        if self.streamlabs_complete:
            self.streamlabs_complete = False
            self.cancel_streamlabs_login(clear_status=False)

    def prepare_native_backend(self):
        # Backend imports other Qt components, so never first-import in QThread.
        try:
            import TiktokStreamKeyGenerator  # noqa: F401
            return True
        except Exception as exc:
            self.status.setText("Backend TikTok LIVE asli gagal dimuat: " + str(exc))
            return False

    def start_qr_login(self):
        if self.job is not None:
            return
        api_key = self.api_key.text().strip()
        if not api_key:
            self.status.setText(
                "Login QR LIVE Studio native memerlukan signer RapidAPI. "
                "Cek Sesi TikTok tersedia tanpa key setelah impor cookies."
            )
            return
        if not self.prepare_native_backend():
            return
        self.cancel_qr_login()
        session = QrLoginSession()
        self.request(lambda: (session, session.start(api_key)),
                     self.show_qr, "Menyiapkan login QR TikTok…")

    def show_qr(self, result):
        session, encoded = result
        image = QPixmap()
        try:
            valid = image.loadFromData(base64.b64decode(encoded))
        except (ValueError, TypeError):
            valid = False
        if not valid:
            session.close()
            self.status.setText("Gagal: gambar QR dari TikTok tidak valid.")
            return
        self.qr_session = session
        # Keep QR modules sharp. A 235px smooth-scale distorted long login URLs.
        # The backend creates a compact PNG with whole-pixel modules already.
        available = max(260, self.width() - 42)
        if image.width() > available:
            image = image.scaled(
                available, available, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        self.qr_label.setMinimumHeight(image.height())
        self.qr_label.setPixmap(image)
        self.qr_label.show()
        self.qr_help.show()
        self.cancel_qr_button.show()
        self.qr_timer.start()
        self.status.setText("Scan QR dan konfirmasi login dari aplikasi TikTok.")

    def poll_qr_login(self):
        if self.job is not None or self.qr_session is None:
            return
        session = self.qr_session
        self.request(session.poll, self.handle_qr_status, "Memeriksa login TikTok…",
                     on_error=self.handle_qr_poll_error)

    def handle_qr_poll_error(self, message):
        self.qr_timer.stop()
        self.qr_complete = True
        self.status.setText("Login QR gagal: " + message + ". Coba login QR lagi.")

    def handle_qr_status(self, status):
        if status == "confirmed":
            self.qr_timer.stop()
            self.qr_complete = True
            self.cookie_status.setText("Berhasil login TikTok. Cookies tersimpan privat.")
            self.status.setText("Login berhasil. Sekarang ambil RTMP & Stream Key.")
        elif status == "scanned":
            self.status.setText("QR dipindai. Konfirmasi login di aplikasi TikTok.")
        elif status in ("expired", "timeout"):
            self.qr_timer.stop()
            self.qr_complete = True
            self.status.setText("QR sudah kedaluwarsa. Tekan Login TikTok lewat QR lagi.")
        elif status == "new":
            self.status.setText("Menunggu QR dipindai oleh TikTok.")
        else:
            self.status.setText("Status login TikTok: " + status)

    def cancel_qr_login(self, clear_status=True):
        # This is invoked only while no QR network worker is running.
        if self.job is not None:
            return
        self.qr_timer.stop()
        if self.qr_session is not None:
            self.qr_session.close()
            self.qr_session = None
        self.qr_label.clear()
        self.qr_label.hide()
        self.qr_help.hide()
        self.cancel_qr_button.hide()
        if clear_status:
            self.status.setText("Login QR dibatalkan.")

    def generate(self):
        mode = self.selected_mode()
        if self.native_room_active and mode != "native_unsigned":
            self.status.setText("Akhiri room LIVE Studio eksperimen sebelum pindah mode.")
            return
        api_key = self.api_key.text().strip()
        if mode not in ("streamlabs", "native_unsigned") and not api_key:
            self.status.setText(
                "TikTok native belum dapat membuat RTMP/Stream Key tanpa signer. "
                "Cek Sesi TikTok bisa digunakan tanpa RapidAPI."
            )
            return
        if mode not in ("streamlabs", "native_unsigned") and not self.prepare_native_backend():
            return
        self.clear_credentials()
        title = self.title.text()
        self.request(lambda: get_credentials(title, api_key, mode),
                     self.show_credentials, "Menghubungi TikTok…")

    def show_credentials(self, payload):
        self.last_mode = payload["mode"]
        self.server_value = payload["server"]
        self.key_value = payload["key"]
        self.server.setText(self.server_value)
        self.key.setText(self.key_value)
        self.copy_server.setEnabled(True)
        self.copy_key.setEnabled(True)
        self.status.setText(
            ("Room LIVE lama dipakai kembali." if payload["resumed"]
             else "Room LIVE dibuat.") + " Kredensial berhasil diterima."
        )
        if payload["mode"] == "native_unsigned":
            self.native_room_active = True
            self.native_streaming_button.show()
            self.native_streaming_button.setEnabled(True)
            self.native_heartbeat_timer.start()
            self.status.setText(
                "TikTok mengembalikan RTMP/key tanpa RapidAPI. Jalankan encoder, "
                "lalu tekan 'Encoder sudah mengirim video'. "
                "Jangan tutup aplikasi sebelum mengakhiri room."
            )

    def finish_live(self):
        api_key = self.api_key.text().strip()
        mode = self.last_mode or self.selected_mode()
        if mode not in ("streamlabs", "native_unsigned") and not api_key:
            self.status.setText(
                "Tidak dapat mengakhiri room TikTok native tanpa signer. "
                "Akhiri LIVE dari aplikasi TikTok bila masih aktif."
            )
            return
        if mode not in ("streamlabs", "native_unsigned") and not self.prepare_native_backend():
            return
        self.native_heartbeat_timer.stop()
        self.request(
            lambda: end_live(api_key, mode), self.live_ended,
            "Mengakhiri room LIVE…",
            on_error=self.native_end_error if mode == "native_unsigned"
            else None,
        )

    def native_end_error(self, message):
        if self.native_room_active:
            self.native_heartbeat_timer.start()
        self.show_request_error(message)


    def live_ended(self, ended):
        self.native_heartbeat_timer.stop()
        self.native_room_active = False
        self.native_streaming_button.hide()
        self.clear_credentials()
        self.last_mode = None
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
        if self.native_room_active:
            event.ignore()
            self.status.setText(
                "Akhiri Room LIVE sebelum keluar agar TikTok tidak meninggalkan room aktif."
            )
            return
        if self.job is not None:
            event.ignore()
            self.status.setText("Selesaikan permintaan sebelum menutup aplikasi.")
            return
        self.cancel_qr_login(clear_status=False)
        self.cancel_streamlabs_login(clear_status=False)
        super().closeEvent(event)


def main():
    # Streamlabs starts without loading the desktop TikTok signer and Fluent UI.
    # The native backend is loaded on Qt's GUI thread only when selected.
    app = QApplication.instance() or QApplication(sys.argv)
    window = SimpleAndroidWindow()
    window.resize(390, 680)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
