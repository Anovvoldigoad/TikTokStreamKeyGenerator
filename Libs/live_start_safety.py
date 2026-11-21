"""Do not leave newly allocated TikTok LIVE rooms active after a local failure.

A resumed or previously existing room is never owned by the current create
operation and MUST NOT be ended by this helper.
"""


def end_new_room_if_allocated(stream, *, previous_room_id="", device_id="",
                              install_id="", priority_region=""):
    room_id = str(getattr(stream, "roomId", "") or "").strip()
    stream_id = str(getattr(stream, "streamId", "") or "").strip()
    previous = str(previous_room_id or "").strip()
    if room_id in ("", "0") or stream_id in ("", "0") or room_id == previous:
        return False
    stream.endStream(
        room_id=room_id,
        stream_id=stream_id,
        device_id=device_id,
        install_id=install_id,
        priority_region=priority_region,
    )
    return True
