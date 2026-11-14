"""Import Android SAF selections using Qt's content-URI-aware QFile.

Plain Python `open("content://...")` does not work. Qt's Android QFile
engine can read the URI granted by the native QFileDialog; copy the result
to app-private storage before the temporary permission is lost.
"""
import os
from pathlib import Path
import tempfile

from Libs.app_paths import user_data_dir


def _thumbnail_extension(first_bytes):
    if first_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if first_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    raise ValueError("Thumbnail must be a PNG or JPEG image")


def _copy_limited_stream(source, target, byte_limit):
    size = 0
    first_chunk = b""
    with open(target, "wb") as output:
        while True:
            data = bytes(source.read(64 * 1024))
            if not data:
                break
            if not first_chunk:
                first_chunk = data[:16]
            size += len(data)
            if size > byte_limit:
                raise ValueError("Selected file exceeds maximum size")
            output.write(data)
        output.flush()
        os.fsync(output.fileno())
    if not size:
        raise ValueError("Selected file is empty")
    return first_chunk


def import_selected_file(file_path, purpose):
    """Return durable private pathname; `file_path` comes from user picker."""
    if purpose not in ("cookies", "thumbnail"):
        raise ValueError("Unsupported file import purpose")
    from PySide6.QtCore import QFile, QIODevice

    source = QFile(str(file_path))
    if not source.open(QIODevice.OpenModeFlag.ReadOnly):
        raise OSError(f"Android could not read the selected {purpose} file")
    directory = Path(user_data_dir())
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".import-", dir=directory)
    os.close(descriptor)
    try:
        maximum = 16 * 1024 * 1024 if purpose == "cookies" else 20 * 1024 * 1024
        first_chunk = _copy_limited_stream(source, temporary_path, maximum)
        if purpose == "cookies":
            dest = directory / "selected-cookies.json"
        else:
            ext = _thumbnail_extension(first_chunk)
            dest = directory / f"selected-thumbnail{ext}"
        os.replace(temporary_path, dest)
        return str(dest)
    finally:
        source.close()
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
