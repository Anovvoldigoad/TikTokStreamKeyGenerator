"""Minimal Android credential flow using the existing TikTok LIVE backend.

This only retrieves credentials. It does not make direct third-party RTMP
ingestion supported or bypass TikTok account eligibility / RapidAPI signing.
"""
import json
import os
import tempfile
from pathlib import Path

from Libs.app_paths import user_data_dir
from Libs.cookie_payload import normalize_cookie_entries


def config_path():
    return Path(user_data_dir()) / "config.json"


def load_settings():
    try:
        result = json.loads(config_path().read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".settings-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(settings, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_cookies(path):
    with open(path, encoding="utf-8-sig") as file:
        entries = normalize_cookie_entries(json.load(file))
    names = {item["name"] for item in entries if item["value"]}
    if not names.intersection({"sessionid", "sessionid_ss", "sid_tt"}):
        raise ValueError("File JSON tidak memiliki cookie sesi login TikTok.")
    return entries


def import_cookies(selected_path):
    from Libs.android_file_import import import_selected_file
    path = import_selected_file(selected_path, "cookies", validator=validate_cookies)
    settings = load_settings()
    settings["cookies_path"] = path
    save_settings(settings)
    return path



def check_native_login_session():
    """Read-only TikTok WEB login check; never asserts LIVE Studio/RTMP access.

    The web account-info endpoint does not use the LIVE Studio RapidAPI signer.
    Web anti-bot responses are inconclusive, not proof that a user is logged out.
    """
    import requests

    cookie_path = load_settings().get("cookies_path")
    if not cookie_path:
        raise ValueError("Impor cookies JSON TikTok dulu untuk memeriksa sesi.")
    entries = validate_cookies(cookie_path)
    cookies = {}
    for item in entries:
        name = item["name"]
        domain = str(item.get("domain") or "").lstrip(".").lower()
        if (not domain or domain == "tiktok.com" or
                domain.endswith(".tiktok.com")):
            cookies[name] = item["value"]
    if not any(cookies.get(name) for name in ("sessionid", "sessionid_ss", "sid_tt")):
        raise ValueError("Cookies tidak berisi sesi TikTok dari domain tiktok.com.")

    try:
        response = requests.get(
            "https://www.tiktok.com/passport/web/account/info/",
            params={"aid": "1988", "app_language": "en", "app_name": "tiktok_web"},
            cookies=cookies,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
                ),
                "Accept": "application/json",
                "Referer": "https://www.tiktok.com/",
            },
            timeout=15,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise RuntimeError("Tidak dapat menghubungi TikTok untuk cek sesi.") from exc

    if response.status_code != 200:
        raise RuntimeError(
            "TikTok tidak mengizinkan pemeriksaan sesi (HTTP "
            + str(response.status_code) + "). Status login belum bisa dipastikan."
        )
    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "TikTok mengirim halaman non-JSON. Status login belum bisa dipastikan."
        ) from exc
    if not isinstance(result, dict):
        raise RuntimeError("Respons TikTok tidak dikenali. Status login belum bisa dipastikan.")
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if str(data.get("error_code") or "") == "13" or data.get("name") == "session_expired":
        return {"state": "expired", "username": ""}
    if result.get("message") != "success" or not (
        data.get("user_id_str") or data.get("sec_user_id")
    ):
        raise RuntimeError(
            "TikTok belum mengonfirmasi sesi login. Ini bukan bukti akun tidak bisa LIVE."
        )
    return {
        "state": "valid",
        "username": str(data.get("username") or data.get("screen_name") or ""),
    }


def _ready_settings(api_key):
    settings = load_settings()
    api_key = str(api_key or "").strip()
    if not api_key:
        raise ValueError("RapidAPI key wajib diisi untuk penandatanganan TikTok.")
    cookies_path = settings.get("cookies_path", "")
    if not cookies_path:
        raise ValueError("Impor cookies JSON akun TikTok terlebih dahulu.")
    validate_cookies(cookies_path)
    settings["rapidapi_key"] = api_key
    save_settings(settings)
    return settings, cookies_path


def _device_profile(settings, mode):
    from Libs.device_gen import (
        register_desktop_device_identifiers, register_mobile_device_identifiers,
    )
    from Libs.client_profiles import mobile_record_defaults
    if mode not in ("pc", "mobile"):
        raise ValueError("Mode TikTok tidak dikenal.")
    profile = (settings.get("devices") or {}).get(mode) or {}
    if mode == "mobile":
        profile = mobile_record_defaults(profile)
    if profile.get("device_id") and profile.get("install_id"):
        return profile
    register = (register_mobile_device_identifiers if mode == "mobile"
                else register_desktop_device_identifiers)
    profile = register(device_profile=profile, return_profile=True)
    settings.setdefault("devices", {})[mode] = profile
    save_settings(settings)
    return profile


def save_streamlabs_token(token):
    """Validate and retain only the user's own Streamlabs bearer token."""
    from Libs.streamlabs_android import StreamlabsClient
    value = str(token or "").strip()
    if not value or len(value) > 4096 or any(c.isspace() for c in value):
        raise ValueError("Token Streamlabs tidak valid.")
    settings = load_settings()
    client = StreamlabsClient(value)
    try:
        info = client.info()
    finally:
        client.close()
    user = info.get("user") if isinstance(info.get("user"), dict) else {}
    username = str(user.get("username") or "")
    if settings.get("streamlabs_active") and settings.get("streamlabs_token") != value:
        previous = str(settings.get("streamlabs_username") or "")
        if not previous or not username or previous != username:
            raise RuntimeError("Akhiri room Streamlabs sebelum mengganti akun.")
    settings["streamlabs_token"] = value
    settings["streamlabs_username"] = username
    save_settings(settings)
    return {
        "username": username,
        "can_be_live": info.get("can_be_live") is True,
    }


def streamlabs_credentials(title):
    """Start only a single Streamlabs room or reuse existing private output."""
    from Libs.streamlabs_android import StreamlabsClient
    settings = load_settings()
    token = str(settings.get("streamlabs_token") or "")
    if not token:
        raise ValueError("Login Streamlabs lewat browser atau tempel token dahulu.")
    active = settings.get("streamlabs_active") or {}
    if all(active.get(key) for key in ("room_id", "server", "key")):
        return {
            "server": active["server"], "key": active["key"],
            "room_id": active["room_id"], "mode": "streamlabs", "resumed": True,
        }
    if active:
        raise RuntimeError("Room Streamlabs sebelumnya tidak lengkap. Akhiri room dahulu.")
    client = StreamlabsClient(token)
    try:
        info = client.info()
        if info.get("can_be_live") is not True:
            status = info.get("application_status")
            status = status.get("status") if isinstance(status, dict) else ""
            raise RuntimeError(
                "Akun belum memiliki izin TikTok LIVE melalui Streamlabs. "
                + (f"Status: {status}." if status else "Periksa akses Streamlabs TikTok LIVE.")
            )
        result = client.start(title, category="")
    finally:
        client.close()
    settings["streamlabs_active"] = result
    save_settings(settings)
    return {
        "server": result["server"], "key": result["key"],
        "room_id": result["room_id"], "mode": "streamlabs", "resumed": False,
    }


def end_streamlabs_live():
    from Libs.streamlabs_android import StreamlabsClient
    settings = load_settings()
    active = settings.get("streamlabs_active") or {}
    if not active:
        return False
    token = settings.get("streamlabs_token") or ""
    client = StreamlabsClient(token)
    try:
        client.end(active.get("room_id"))
    finally:
        client.close()
    settings.pop("streamlabs_active", None)
    save_settings(settings)
    return True


def get_credentials(title, api_key, mode="pc"):
    title = str(title or "").strip()
    if not title:
        raise ValueError("Judul LIVE tidak boleh kosong.")
    if len(title) > 32:
        raise ValueError("Judul LIVE maksimal 32 karakter.")
    if mode == "streamlabs":
        return streamlabs_credentials(title)
    settings, cookies_path = _ready_settings(api_key)
    profile = _device_profile(settings, mode)

    # Import the already audited LIVE request and signed-room implementation.
    from TiktokStreamKeyGenerator import Stream
    with Stream(cookies_path=cookies_path, device_type=mode, device_profile=profile) as stream:
        args = {"device_id": profile["device_id"], "install_id": profile["install_id"]}
        existing = stream.getContinuableStreamInfo(**args)
        if existing.get("has_room"):
            if not existing.get("can_resume"):
                raise RuntimeError(
                    "Ada room LIVE aktif tanpa RTMP yang bisa dipakai. "
                    "Akhiri room itu melalui TikTok sebelum mencoba lagi."
                )
            resumed = True
        else:
            # A LIVE status without a continuable URL must not be overwritten.
            create_info = stream.getCreateRoomInfo(last_time_hashtag_id="42", **args)
            create_data = create_info.get("data", {}) if isinstance(create_info, dict) else {}
            if str(create_data.get("live_status")) == "2":
                raise RuntimeError(
                    "TikTok melaporkan LIVE aktif, tetapi tidak memberikan RTMP untuk dipakai. "
                    "Akhiri LIVE lama dari TikTok terlebih dahulu."
                )
            # "42" is the Chat & Interview topic; no game lookup is required.
            if not stream.createStream(title, "42", device_id=args["device_id"],
                                       install_id=args["install_id"]):
                raise RuntimeError("TikTok menolak pembuatan room LIVE.")
            resumed = False
        if not stream.baseStreamUrl or not stream.streamKey:
            raise RuntimeError("TikTok tidak mengembalikan RTMP dan stream key.")
        return {
            "server": stream.baseStreamUrl,
            "key": stream.streamKey,
            "room_id": stream.roomId,
            "mode": mode,
            "resumed": resumed,
        }


def end_live(api_key, mode="pc"):
    if mode == "streamlabs":
        return end_streamlabs_live()
    settings, cookies_path = _ready_settings(api_key)
    profile = _device_profile(settings, mode)
    from TiktokStreamKeyGenerator import Stream
    with Stream(cookies_path=cookies_path, device_type=mode, device_profile=profile) as stream:
        args = {"device_id": profile["device_id"], "install_id": profile["install_id"]}
        existing = stream.getContinuableStreamInfo(**args)
        if not existing.get("has_room"):
            return False
        room_id, stream_id = existing.get("room_id"), existing.get("stream_id")
        if not room_id or not stream_id:
            raise RuntimeError("TikTok tidak memberikan ID room yang bisa diakhiri.")
        stream.endStream(room_id=room_id, stream_id=stream_id,
                         priority_region=existing.get("priority_region", ""), **args)
        return True


def import_cookies_text(text):
    """Accept an existing browser JSON export without a Qt Android file picker."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Clipboard belum berisi cookies JSON TikTok.")
    if len(text.encode("utf-8")) > 16 * 1024 * 1024:
        raise ValueError("Cookies JSON terlalu besar (maksimal 16 MB).")
    entries = normalize_cookie_entries(json.loads(text))
    if not any(item["name"] in {"sessionid", "sessionid_ss", "sid_tt"}
               and item["value"] for item in entries):
        raise ValueError("Cookies JSON tidak mengandung sesi login TikTok.")
    target = Path(user_data_dir()) / "selected-cookies.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".cookies-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(entries, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    settings = load_settings()
    settings["cookies_path"] = str(target)
    save_settings(settings)
    return str(target)


def qr_png_from_response(payload):
    """Produce a sharp, validated PNG from TikTok's login URL or image.

    QR modules are rendered at an integer pixel scale with a quiet zone.
    This avoids Android Qt downsampling a large QR to a blurry 235px preview.
    """
    import base64
    import io
    from urllib.parse import urlsplit

    if not isinstance(payload, dict):
        raise ValueError("TikTok tidak mengembalikan data QR yang valid.")
    url = str(payload.get("qrcode_index_url") or "").strip()
    if url:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Alamat QR login TikTok tidak valid.")
        import segno
        code = segno.make_qr(url, error="L", boost_error=False)
        modules = code.symbol_size(scale=1, border=4)[0]
        # This normally yields a 260-340px QR, which fits an Android phone.
        scale = max(1, min(8, 330 // modules))
        buffer = io.BytesIO()
        code.save(buffer, kind="png", scale=scale, border=4)
        image = buffer.getvalue()
    else:
        encoded = str(payload.get("qrcode") or "").strip()
        if encoded.startswith("data:image/png;base64,"):
            encoded = encoded.partition(",")[2]
        try:
            image = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("TikTok mengembalikan QR Base64 yang tidak valid.") from exc
    if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) < 100:
        raise ValueError("QR login bukan gambar PNG yang valid.")
    return base64.b64encode(image).decode("ascii")


class QrLoginSession:
    """Standalone TikTok Live Studio QR login using the existing signed client.

    The UI drives start() and poll() on its network worker; no nested Qt dialog.
    QR login is separate from Mobile LIVE entitlement.
    """

    def __init__(self):
        self.client = None
        self.token = ""

    def start(self, api_key):
        api_key = str(api_key or "").strip()
        if not api_key:
            raise ValueError("Isi RapidAPI Signer Key sebelum login QR.")
        settings = load_settings()
        settings["rapidapi_key"] = api_key
        save_settings(settings)
        profile = _device_profile(settings, "pc")
        from TiktokStreamKeyGenerator import LiveStudioBrowserLoginClient
        client = LiveStudioBrowserLoginClient(profile["device_id"], profile["install_id"])
        try:
            result = client.get_qrcode()
            token = str(result.get("token") or "")
            if not token:
                raise RuntimeError("TikTok tidak mengembalikan token QR login.")
            image = qr_png_from_response(result)
        except Exception:
            client.close()
            raise
        self.client = client
        self.token = token
        return image

    def poll(self):
        if self.client is None or not self.token:
            raise RuntimeError("Mulai login QR terlebih dahulu.")
        payload = self.client.check_qrconnect(self.token)
        data = payload.get("data") if isinstance(payload, dict) else {}
        data = data if isinstance(data, dict) else {}
        status = str(data.get("status") or data.get("qr_status")
                     or data.get("state") or "new")
        if status == "confirmed":
            expected = str(getattr(self.client, "qr_client_secret", "") or "")
            returned = str(data.get("client_secret") or "")
            if expected and not (returned == expected or data.get("client_secret_match")):
                return "scanned"
            target = Path(user_data_dir()) / "qr-cookies.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".qr-cookies-", dir=target.parent)
            os.close(fd)
            try:
                self.client.save_cookies(temporary)
                validate_cookies(temporary)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            settings = load_settings()
            settings["cookies_path"] = str(target)
            save_settings(settings)
            return "confirmed"
        return status

    def close(self):
        client, self.client = self.client, None
        self.token = ""
        if client is not None:
            client.close()
