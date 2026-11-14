"""Patch Qt-generated Buildozer configuration without changing Qt's recipes.

This runs after `pyside6-android-deploy --init`. Keep its generated Qt,
NDK and Java options unchanged; add only Python app dependencies and
the pre-audited Android ARM64 FFmpeg payload.
"""
from pathlib import Path
import sys

REQUIREMENTS = (
    "python3,shiboken6,PySide6,requests,websockets,"
    "PySide6-Fluent-Widgets,PySideSix-Frameless-Window,darkdetect,"
    "pytz,python-dotenv,packaging,tzdata,pycryptodome"
)
FFMPEG_LIB = "android-native/arm64-v8a/libffmpeg_exec.so"


def configure(original):
    output = []
    replaced = set()
    for line in original.splitlines(keepends=True):
        stripped = line.lstrip()
        if not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key == "requirements":
                line = "requirements = " + REQUIREMENTS + "\n"
                replaced.add(key)
            elif key == "source.include_exts":
                old = stripped.partition("=")[2].strip().split("#", 1)[0]
                exts = [x.strip() for x in old.split(",") if x.strip()]
                for ext in ("json", "svg", "ttf", "otf", "ico", "webp", "pem"):
                    if ext not in exts:
                        exts.append(ext)
                line = "source.include_exts = " + ",".join(exts) + "\n"
                replaced.add(key)
        output.append(line)
    if replaced != {"requirements", "source.include_exts"}:
        raise ValueError("Qt-generated Buildozer config is missing expected keys")
    # Must be an actual active option, not a commented example.
    if any(line.strip().startswith("android.add_libs_arm64_v8a =") for line in output):
        raise ValueError("Existing Android native library configuration must be reviewed")
    output.append("\n# Pinned 16 KiB-compatible ARM64 FFmpeg executable.\n")
    output.append(f"android.add_libs_arm64_v8a = {FFMPEG_LIB}\n")
    return "".join(output)


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "buildozer.spec")
    if not Path(FFMPEG_LIB).is_file():
        raise SystemExit(f"Missing pinned Android FFmpeg: {FFMPEG_LIB}")
    path.write_text(configure(path.read_text(encoding="utf-8")), encoding="utf-8")
    print("Configured Android app requirements and pinned ARM64 FFmpeg native asset")
