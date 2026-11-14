"""Locate an immutable, executable Android native FFmpeg payload.

Android 10+ disallows execution from writable application directories. The
packaged PIE executable is installed under nativeLibraryDir as
`libffmpeg_exec.so`, not extracted into app-private cache.
"""
import os


FFMPEG_FILENAME = "libffmpeg_exec.so"


def _native_library_directories():
    """Infer the running app's library dir from Qt/CPython ELF mappings."""
    seen = set()
    try:
        with open("/proc/self/maps", "r", encoding="utf-8") as fh:
            for line in fh:
                path = line.rstrip().rsplit(maxsplit=1)[-1]
                if "!" in path or not path.startswith("/"):
                    continue  # APK-internal mappings are not exec() paths.
                filename = os.path.basename(path)
                if not (filename.startswith("libQt6Core_") or
                        filename.startswith("libpython3.")):
                    continue
                directory = os.path.dirname(path)
                if directory not in seen:
                    seen.add(directory)
                    yield directory
    except OSError:
        return


def find_ffmpeg():
    """Return a packaged executable, or raise instead of creating a broken LIVE."""
    override = os.environ.get("TIKTOK_ANDROID_FFMPEG", "")
    candidates = [override] if override else []
    candidates.extend(os.path.join(root, FFMPEG_FILENAME) for root in _native_library_directories())
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError(
        "Android FFmpeg is not available as an executable native library. "
        "The APK must install libffmpeg_exec.so to its native library directory."
    )
