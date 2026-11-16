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
    names = {item["name"] for item in entries}
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


def get_credentials(title, api_key, mode="pc"):
    title = str(title or "").strip()
    if not title:
        raise ValueError("Judul LIVE tidak boleh kosong.")
    if len(title) > 32:
        raise ValueError("Judul LIVE maksimal 32 karakter.")
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
    settings, cookies_path = _ready_settings(api_key)
    profile = _device_profile(settings, mode)
    from TiktokStreamKeyGenerator import Stream
    with Stream(cookies_path=cookies_path, device_type="pc", device_profile=profile) as stream:
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
