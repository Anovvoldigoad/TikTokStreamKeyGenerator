"""Experimental unsigned LIVE Studio protocol (no RapidAPI or Streamlabs).

Adapted from averagenative/tiktok-live-studio-linux (MIT):
  https://github.com/averagenative/tiktok-live-studio-linux
  src/tiktok.js, src/util.js, docs/PROTOCOL.md

Unverified for Android/Indonesian accounts. Only the user-triggered start
creates a room. Never report a valid RTMP/key until TikTok returns it.
"""
import hashlib
from urllib.parse import quote, urlsplit

import requests

from Libs.simple_android_stream import load_settings, validate_cookies

HOST_BY_IDC = {
    "alisg": "https://webcast16-normal-c-alisg.tiktokv.com",
    "useast5": "https://webcast16-normal-useast5.tiktokv.us",
    "useast8": "https://webcast16-normal-useast8.tiktokv.us",
    "useast1a": "https://webcast16-normal-c-useast1a.tiktokv.com",
    "no1a": "https://webcast16-normal-no1a.tiktokv.eu",
}
IDC_ALIASES = {
    "sg": "alisg", "my": "alisg", "va": "useast1a",
    "maliva": "useast1a", "ttp": "useast5", "ttp2": "useast8",
    "ie": "no1a", "eu": "no1a", "useast2a": "no1a",
}
DEFAULT_HOST = "https://webcast.tiktokv.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "TikTokLIVEStudio/1.38.0 Chrome/140.0.0.0 Electron/38.0.0 Safari/537.36"
)


def _encode_form(fields):
    return "&".join(
        quote(str(k), safe="~!*'()-._") + "="
        + quote(str(v).lower() if isinstance(v, bool) else str(v), safe="~!*'()-._")
        for k, v in fields.items() if v is not None
    )


def _parse_push_url(data):
    urls = data.get("stream_url") or {}
    if not isinstance(urls, dict):
        return None
    options = [urls.get("rtmp_push_url")]
    if isinstance(urls.get("push_urls"), list):
        options.extend(urls["push_urls"])
    for value in options:
        if not isinstance(value, str):
            continue
        parsed = urlsplit(value)
        if parsed.scheme not in ("rtmp", "rtmps") or not parsed.hostname:
            continue
        slash = value.rfind("/")
        if slash <= len(parsed.scheme) + 2 or not value[slash + 1:]:
            continue
        return {"server": value[:slash + 1], "key": value[slash + 1:]}
    return None


class UnsignedStudioClient:
    def __init__(self):
        settings = load_settings()
        path = settings.get("cookies_path")
        if not path:
            raise ValueError("Impor cookies akun TikTok terlebih dahulu.")
        entries = validate_cookies(path)
        cookies = {}
        for item in entries:
            domain = str(item.get("domain") or "").lstrip(".").lower()
            if domain and domain != "tiktok.com" and not domain.endswith(".tiktok.com"):
                continue
            cookies[item["name"]] = item["value"]
        if not (cookies.get("sessionid") or cookies.get("sessionid_ss")):
            raise ValueError("Diperlukan cookie sesi TikTok yang masih berlaku.")
        if not cookies.get("sessionid") and cookies.get("sessionid_ss"):
            cookies["sessionid"] = cookies["sessionid_ss"]
        idc = str(cookies.get("tt-target-idc") or cookies.get("store-idc") or "").lower()
        self.host = HOST_BY_IDC.get(IDC_ALIASES.get(idc, idc), DEFAULT_HOST)
        region = str(cookies.get("store-country-code") or "").lower()
        self.params = {
            "aid": 8311, "app_name": "tiktok_live_studio",
            "channel": "studio", "device_platform": "mac",
            "version_code": "1.38.0", "webcast_sdk_version": 1380,
            "live_mode": 6, "language": "en", "app_language": "en",
            "webcast_language": "en", "device_id": "0", "install_id": "0",
            "timezone_name": "Asia/Jakarta",
            "browser_language": "en", "browser_platform": "MacIntel",
            "browser_name": "Mozilla",
        }
        if region:
            self.params["priority_region"] = region
        self.headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "sdk_aid": "8311", "Referer": "https://www.tiktok.com/",
            "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        }
        if region:
            self.headers["x-tt-store-region"] = region

    def request(self, method, path, *, query=None, form=None):
        if not path.startswith("/webcast/"):
            raise ValueError("Path LIVE Studio tidak diizinkan.")
        headers = dict(self.headers)
        encoded = None
        if method == "POST":
            encoded = _encode_form(form or {})
            headers["x-ss-stub"] = hashlib.md5(encoded.encode("utf-8")).hexdigest()
        elif method != "GET":
            raise ValueError("Metode request tidak diizinkan.")
        try:
            response = requests.request(
                method, self.host + path,
                params={**self.params, **(query or {})},
                data=encoded, headers=headers, timeout=20,
                allow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise RuntimeError("Request LIVE Studio ditolak atau koneksi gagal.") from exc
        except ValueError as exc:
            raise RuntimeError("LIVE Studio tidak mengembalikan JSON valid.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Format respons LIVE Studio tidak dikenal.")
        return payload

    def preflight(self):
        result = self.request("GET", "/webcast/room/create_info/",
                              query={"live_studio": "1"})
        code = result.get("status_code")
        data = result.get("data")
        data = data if isinstance(data, dict) else {}
        return {
            "allowed": code == 0,
            "status_code": code,
            "message": str(data.get("message") or result.get("message") or ""),
            "host": self.host.split("://", 1)[1],
        }

    def create(self, title):
        if not title or len(title) > 32:
            raise ValueError("Judul LIVE harus berisi 1–32 karakter.")
        preflight = self.preflight()
        if not preflight["allowed"]:
            raise RuntimeError(
                "TikTok menolak akses LIVE Studio tanpa RapidAPI "
                f"(status_code={preflight['status_code']}). "
                "Tidak ada room yang dibuat."
            )
        result = self.request("POST", "/webcast/room/create/", form={
            "title": title, "live_studio": 1, "gen_replay": True,
            "chat_auth": 1, "gift_auth": 1, "chat_l2": 1,
            "star_comment_switch": True, "cover_uri": "",
            "close_room_when_close_stream": False,
            "hashtag_id": 0, "game_tag_id": 0,
            "multi_stream_scene": 0, "multi_stream_source": 1,
        })
        code = result.get("status_code")
        if code != 0:
            raise RuntimeError(
                f"TikTok menolak membuat room tanpa RapidAPI (status_code={code})."
            )
        data = result.get("data") or {}
        room_id = str(data.get("id_str") or data.get("id") or "")
        ping_room_id = str((data.get("living_room_attrs") or {}).get("room_id_str")
                           or room_id)
        stream_id = str(data.get("stream_id_str") or data.get("stream_id") or "")
        push = _parse_push_url(data)
        if not (room_id and ping_room_id and stream_id and push):
            if ping_room_id and stream_id:
                try:
                    self.ping(ping_room_id, stream_id, 4)
                except RuntimeError:
                    pass
            raise RuntimeError(
                "Respons TikTok tidak lengkap (room/stream/RTMP). "
                "Room diakhiri jika memungkinkan."
            )
        return {
            **push, "room_id": room_id, "ping_room_id": ping_room_id,
            "stream_id": stream_id, "host": self.host,
            "mode": "native_unsigned", "resumed": False,
        }

    def ping(self, room_id, stream_id, status):
        if not room_id or not stream_id or status not in (1, 2, 4):
            raise ValueError("Status/ID room LIVE tidak valid.")
        result = self.request("POST", "/webcast/room/ping/anchor/", form={
            "status": status, "room_id": room_id, "stream_id": stream_id,
        })
        code = result.get("status_code")
        if code not in (0, 4003150, 30003):
            raise RuntimeError(f"Heartbeat TikTok ditolak (status_code={code}).")
        return True


_active = None


def check_native_studio():
    """Read-only: can try without triggering a new LIVE room."""
    return UnsignedStudioClient().preflight()


def start_native_studio(title):
    global _active
    if _active is not None:
        return {k: _active[k] for k in
                ("server", "key", "room_id", "mode")} | {"resumed": True}
    client = UnsignedStudioClient()
    result = client.create(title)
    _active = result
    return {k: result[k] for k in
            ("server", "key", "room_id", "mode")} | {"resumed": False}


def heartbeat_native_studio():
    if _active is None:
        return False
    UnsignedStudioClient().ping(_active["ping_room_id"], _active["stream_id"], 1)
    return True


def end_native_studio():
    global _active
    if _active is None:
        return False
    UnsignedStudioClient().ping(_active["ping_room_id"], _active["stream_id"], 4)
    _active = None
    return True
