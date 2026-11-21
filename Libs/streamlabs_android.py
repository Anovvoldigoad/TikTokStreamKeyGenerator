"""Small Streamlabs OAuth/RTMP client for Android. No RapidAPI signer.

Interoperability based on the GPL-3.0 project:
https://github.com/Loukious/StreamLabsTikTokStreamKeyGenerator
Only calls Streamlabs endpoints using the user's own authorized account.
The browser login flow is a Streamlabs Desktop compatibility flow, not an
official Android SDK; actual service/device acceptance requires live tests.
"""
import base64
import hashlib
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import requests

API = "https://streamlabs.com/api/v5/slobs"
DESKTOP_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) StreamlabsDesktop/1.20.4 Chrome/122.0.6261.156 "
    "Electron/29.3.1 Safari/537.36"
)


class StreamlabsClient:
    def __init__(self, token):
        if not isinstance(token, str) or not token.strip():
            raise ValueError("Login Streamlabs terlebih dahulu.")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DESKTOP_AGENT,
            "Authorization": "Bearer " + token.strip(),
        })

    def close(self):
        self.session.close()

    def _json(self, method, endpoint, **kwargs):
        try:
            response = self.session.request(
                method, API + endpoint, timeout=25, **kwargs
            )
            response.raise_for_status()
            result = response.json()
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            if code in (401, 403):
                raise RuntimeError(
                    "Token Streamlabs ditolak atau izin TikTok LIVE tidak tersedia. "
                    f"HTTP {code}."
                ) from exc
            raise RuntimeError(f"Permintaan Streamlabs gagal (HTTP {code}).") from exc
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError("Tidak dapat mengambil respons valid dari Streamlabs.") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Format respons Streamlabs tidak dikenali.")
        return result

    def info(self):
        result = self._json("GET", "/tiktok/info")
        if "can_be_live" not in result:
            raise RuntimeError("Streamlabs tidak mengembalikan status izin TikTok LIVE.")
        return result

    def start(self, title, category=""):
        response = self._json("POST", "/tiktok/stream/start", files=(
            ("title", (None, title)),
            ("device_platform", (None, "win32")),
            ("category", (None, category)),
            ("audience_type", (None, "0")),
        ))
        room_id = str(response.get("id") or "")
        server = str(response.get("rtmp") or "")
        key = str(response.get("key") or "")
        if not (room_id and server and key):
            raise RuntimeError(
                "Streamlabs tidak memberikan room, RTMP dan Stream Key lengkap. "
                "Periksa izin TikTok LIVE melalui Streamlabs."
            )
        return {"room_id": room_id, "server": server, "key": key}

    def end(self, room_id):
        if not room_id:
            raise ValueError("ID room Streamlabs tidak tersedia.")
        result = self._json("POST", "/tiktok/stream/" + str(room_id) + "/end")
        if result.get("success") is not True:
            raise RuntimeError("Streamlabs tidak mengonfirmasi room LIVE telah diakhiri.")
        return True


class StreamlabsBrowserLogin:
    """Loopback PKCE login matching Streamlabs Desktop's browser flow.

    Begin on Qt's GUI thread, open URL with QDesktopServices, then exchange
    the one-time auth code in an existing background worker.
    """

    def __init__(self):
        self.verifier = os.urandom(64).hex()
        digest = hashlib.sha256(self.verifier.encode("ascii")).digest()
        self.challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        self.server = None
        self._server_thread = None
        self._code = None
        self._error = None
        self._received = threading.Event()
        self._consumed = False
        self.started = 0

    def begin(self):
        if self.server is not None:
            raise RuntimeError("Login Streamlabs sedang berlangsung.")
        flow = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = urlsplit(self.path)
                args = parse_qs(query.query)
                good = (args.get("success") == ["true"] and
                        bool(args.get("code", [""])[0]))
                if not flow._received.is_set():
                    if good:
                        flow._code = args["code"][0]
                    else:
                        flow._error = "Otorisasi Streamlabs ditolak atau dibatalkan."
                    flow._received.set()
                message = (b"Login Streamlabs diterima. Kembali ke aplikasi." if good
                           else b"Login gagal. Kembali ke aplikasi.")
                self.send_response(200 if good else 400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(message)))
                self.end_headers()
                self.wfile.write(message)

            def log_message(self, *_):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        self.server = server
        self.started = time.monotonic()
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.1},
            name="streamlabs-auth-callback", daemon=True,
        )
        thread.start()
        self._server_thread = thread
        params = (
            f"skip_splash=true&external=electron&tiktok&force_verify"
            f"&origin=slobs&port={server.server_port}"
            f"&code_challenge={self.challenge}&code_flow=true"
        )
        return "https://streamlabs.com/slobs/login?" + params

    def ready(self):
        return self._received.is_set()

    def exchange(self):
        if self.server is None or not self.ready():
            raise RuntimeError("Belum ada respons login Streamlabs.")
        if self._consumed:
            raise RuntimeError("Kode login sudah diproses.")
        self._consumed = True
        if self._error:
            raise RuntimeError(self._error)
        if not self._code or time.monotonic() - self.started > 300:
            raise RuntimeError("Login Streamlabs sudah kedaluwarsa.")
        try:
            response = requests.get(
                API + "/auth/data",
                params={"code_verifier": self.verifier, "code": self._code},
                headers={"User-Agent": DESKTOP_AGENT},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError("Gagal menukar otorisasi menjadi token Streamlabs.") from exc
        token = (data.get("data") or {}).get("oauth_token") if isinstance(data, dict) and data.get("success") else None
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError("Streamlabs tidak memberikan token login.")
        return token

    def expired(self):
        return self.server is not None and time.monotonic() - self.started > 300

    def close(self):
        if self.server is not None:
            server, self.server = self.server, None
            if self._server_thread is not None and self._server_thread.is_alive():
                server.shutdown()
            server.server_close()
        self._server_thread = None
        self._code = None
        self.verifier = ""
