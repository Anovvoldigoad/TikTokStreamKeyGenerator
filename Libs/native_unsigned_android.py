"""Experimental unsigned LIVE Studio protocol (no RapidAPI or Streamlabs).

Adapted from averagenative/tiktok-live-studio-linux (MIT):
  https://github.com/averagenative/tiktok-live-studio-linux
  src/tiktok.js, src/util.js, docs/PROTOCOL.md

Unverified for Android/Indonesian accounts. Only the user-triggered start
creates a room. Never report a valid RTMP/key until TikTok returns it.

Copyright and license of upstream protocol/client adaptation:
  MIT License
  
  Copyright (c) 2026 averagenative
  
  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:
  
  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.
  
  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
  SOFTWARE.
"""
import hashlib
from urllib.parse import quote, urlsplit

import requests

from Libs.simple_android_stream import load_settings, save_settings, validate_cookies

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
        region = str(cookies.get("store-country-code") or "").lower()
        preferred = HOST_BY_IDC.get(IDC_ALIASES.get(idc, idc))
        # Keep discovery narrow: region-appropriate TikTok hosts, then global.
        # Do not send session cookies to unrelated third-party domains.
        options = [preferred]
        if region in ("id", "sg", "my") and preferred != HOST_BY_IDC["alisg"]:
            options.append(HOST_BY_IDC["alisg"])
        options.append(DEFAULT_HOST)
        self.candidate_hosts = list(dict.fromkeys(host for host in options if host))
        self.host = self.candidate_hosts[0]
        self.params = {
            "aid": 8311, "app_name": "tiktok_live_studio",
            "channel": "studio", "device_platform": "mac",
            "version_code": "1.38.0", "webcast_sdk_version": 1380,
            "live_mode": 6, "language": "en", "app_language": "en",
            "webcast_language": "en", "device_id": "0", "install_id": "0",
            "timezone_name": "Asia/Jakarta",
            "browser_language": "en", "browser_platform": "MacIntel",
            "browser_name": "Mozilla", "browser_version": USER_AGENT[8:],
            **({"priority_region": region} if region else {}),
        }
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
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            raise RuntimeError(
                "TikTok menolak request LIVE Studio lewat HTTP "
                + (str(status) if status is not None else "tidak diketahui")
                + ". Jika 403, sesi atau proteksi server mungkin menolak klien ini."
            ) from None
        except requests.RequestException as exc:
            raise RuntimeError("Koneksi ke server LIVE Studio gagal atau timeout.") from exc
        except ValueError as exc:
            raise RuntimeError(
                "LIVE Studio mengembalikan respons bukan JSON "
                "(HTTP " + str(response.status_code) + "). "
                "Kemungkinan login ulang, redirect, atau proteksi bot."
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Format respons LIVE Studio tidak dikenal.")
        return payload

    def preflight(self):
        # A wrong regional data center often answers status_code=20003 even
        # when the session is valid on the account's actual webcast host.
        result = None
        last_error = None
        for host in self.candidate_hosts:
            self.host = host
            try:
                candidate = self.request(
                    "GET", "/webcast/room/create_info/",
                    query={"live_studio": "1"}
                )
            except RuntimeError as exc:
                last_error = exc
                continue
            result = candidate
            if str(candidate.get("status_code")) != "20003":
                break
        if result is None:
            raise last_error or RuntimeError("Tidak ada server TikTok yang menjawab.")
        code = result.get("status_code")
        data = result.get("data")
        data = data if isinstance(data, dict) else {}
        has_active_room = str(data.get("live_status") or "") == "2"
        return {
            "allowed": code == 0 and not has_active_room,
            "active_room": has_active_room,
            "status_code": code,
            "message": str(data.get("message") or result.get("message") or ""),
            "host": self.host.split("://", 1)[1],
        }

    def create(self, title):
        if not title or len(title) > 32:
            raise ValueError("Judul LIVE harus berisi 1–32 karakter.")
        preflight = self.preflight()
        if preflight["active_room"]:
            raise RuntimeError(
                "TikTok melaporkan room LIVE yang masih aktif. "
                "Akhiri LIVE lama sebelum mencoba membuat yang baru."
            )
        if not preflight["allowed"]:
            code = preflight["status_code"]
            hint = (
                "Sesi web belum diterima oleh server LIVE Studio."
                if str(code) == "20003" else
                "Akun belum diberikan izin LIVE Studio pada endpoint ini."
                if str(code) == "20800" else
                "Periksa izin akun atau respons server TikTok."
            )
            raise RuntimeError(
                f"Precheck LIVE Studio ditolak (status_code={code}, "
                f"host={preflight['host']}). {hint} Tidak ada room yang dibuat."
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
            hint = (
                "Sesi tidak diakui oleh endpoint pembuatan room."
                if str(code) == "20003" else
                "Akun tidak memiliki izin membuat LIVE Studio."
                if str(code) == "20800" else
                "LIVE lain mungkin masih aktif."
                if str(code) == "30005" else
                "TikTok menolak pembuatan room."
            )
            raise RuntimeError(
                f"Room LIVE Studio ditolak (status_code={code}, "
                f"host={self.host.split('://', 1)[1]}). {hint}"
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
            flags = (
                f"room_id={bool(room_id)}, stream_id={bool(stream_id)}, "
                f"rtmp_push_url={bool(push)}"
            )
            raise RuntimeError(
                "TikTok tidak mengembalikan kredensial RTMP lengkap ("
                + flags + "). Room telah dicoba diakhiri."
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
_streaming = False


def check_native_studio():
    """Read-only: can try without triggering a new LIVE room."""
    return UnsignedStudioClient().preflight()


def diagnose_native_studio():
    """Read-only permission diagnostic; never creates a LIVE or discloses secrets."""
    client = UnsignedStudioClient()
    result = client.preflight()
    result.update({
        "studio_enabled": None,
        "locale_restricted": None,
        "permission_status": None,
        "permission_code": None,
        "access_code": None,
        "unmet_requirements": None,
    })
    try:
        permission = client.request("GET", "/webcast/room/live_podcast/")
        result["permission_code"] = permission.get("status_code")
        data = permission.get("data")
        data = data if isinstance(data, dict) else {}
        scenario = data.get("live_scenario")
        scenario = scenario if isinstance(scenario, dict) else {}
        if isinstance(scenario.get("enable_live_studio"), bool):
            result["studio_enabled"] = scenario["enable_live_studio"]
        if isinstance(data.get("golive_locale_restricted"), bool):
            result["locale_restricted"] = data["golive_locale_restricted"]
        if isinstance(data.get("live_studio_permission_status"), (int, str)):
            result["permission_status"] = str(data["live_studio_permission_status"])[:32]
    except RuntimeError:
        pass  # An inconclusive permission endpoint is not automatically a denial.
    try:
        access = client.request("GET", "/webcast/eco/check_access/",
                                query={"permission_type": 1})
        result["access_code"] = access.get("status_code")
        data = access.get("data")
        data = data if isinstance(data, dict) else {}
        requirements = []
        for group in data.get("guidelines") or []:
            if isinstance(group, dict):
                for req in group.get("requirements") or []:
                    if isinstance(req, dict):
                        requirements.append(req.get("pass") is True)
        if requirements:
            result["unmet_requirements"] = sum(not x for x in requirements)
    except RuntimeError:
        pass
    return result


def start_native_studio(title):
    global _active
    if _active is not None:
        return {k: _active[k] for k in
                ("server", "key", "room_id", "mode")} | {"resumed": True}
    settings = load_settings()
    if settings.get("native_unsigned_room"):
        raise RuntimeError(
            "Ada room LIVE Studio dari sesi sebelumnya. "
            "Akhiri Room LIVE dahulu sebelum membuat room baru."
        )
    client = UnsignedStudioClient()
    result = client.create(title)
    settings["native_unsigned_room"] = {
        key: result[key] for key in ("room_id", "ping_room_id", "stream_id", "host")
    }
    try:
        save_settings(settings)
    except OSError:
        try:
            client.ping(result["ping_room_id"], result["stream_id"], 4)
        except RuntimeError:
            pass
        raise RuntimeError(
            "Tidak dapat menyimpan identitas room LIVE. "
            "Room telah dicoba diakhiri; cek status LIVE di TikTok."
        ) from None
    _active = result
    return {k: result[k] for k in
            ("server", "key", "room_id", "mode")} | {"resumed": False}


def heartbeat_native_studio():
    if _active is None:
        return False
    UnsignedStudioClient().ping(
        _active["ping_room_id"], _active["stream_id"], 2 if _streaming else 1
    )
    return True


def mark_native_studio_streaming():
    global _streaming
    if _active is None:
        raise RuntimeError("Belum ada room LIVE Studio aktif.")
    _streaming = True
    return True


def end_native_studio():
    global _active, _streaming
    settings = load_settings()
    room = _active or settings.get("native_unsigned_room")
    if not room:
        return False
    if room.get("host") not in {*HOST_BY_IDC.values(), DEFAULT_HOST}:
        raise RuntimeError("Host room LIVE lama tidak dikenali; tidak mengirim cookies.")
    client = UnsignedStudioClient()
    client.host = room["host"]
    client.ping(room["ping_room_id"], room["stream_id"], 4)
    settings.pop("native_unsigned_room", None)
    save_settings(settings)
    _active = None
    _streaming = False
    return True
