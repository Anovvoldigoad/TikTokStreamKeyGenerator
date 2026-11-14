import unittest
from scripts.configure_android_buildozer import configure, REQUIREMENTS, FFMPEG_LIB


class AndroidBuildSpecTests(unittest.TestCase):
    def test_preserves_qt_configuration(self):
        src = (
            "[app]\n"
            "requirements = python3,shiboken6,PySide6\n"
            "source.include_exts = py,png,jpg,kv,atlas,qml,js\n"
            "p4a.bootstrap = qt\n"
            "android.archs = aarch64\n"
            "android.permissions = INTERNET\n"
            "[buildozer]\n"
            "log_level = 2\n"
        )
        target = configure(src)
        self.assertIn("requirements = " + REQUIREMENTS, target)
        self.assertIn("android.add_libs_arm64_v8a = " + FFMPEG_LIB, target)
        self.assertIn("source.include_exts = py,png,jpg,kv,atlas,qml,js,json,svg,ttf,otf,ico,webp,pem", target)
        self.assertIn("p4a.bootstrap = qt", target)
        self.assertIn("android.permissions = INTERNET", target)
        self.assertLess(target.index("android.add_libs_arm64_v8a"), target.index("[buildozer]"))

    def test_rejects_missing_required_qt_settings(self):
        with self.assertRaisesRegex(ValueError, "missing expected keys"):
            configure("[app]\nrequirements = python3\n")

    def test_rejects_unexpected_preconfigured_native_library(self):
        with self.assertRaisesRegex(ValueError, "native library"):
            configure("[app]\nrequirements = python3\nsource.include_exts = py\nandroid.add_libs_arm64_v8a = something.so\n")


class AndroidFfmpegPathTests(unittest.TestCase):
    def test_find_ffmpeg_requires_executable(self):
        import os
        import tempfile
        from unittest import mock
        from Libs.android_ffmpeg import find_ffmpeg
        with tempfile.TemporaryDirectory() as root:
            candidate = os.path.join(root, "libffmpeg_exec.so")
            with open(candidate, "wb") as f:
                f.write(b"not a real binary; only path and permission test")
            with mock.patch.dict(os.environ, {"TIKTOK_ANDROID_FFMPEG": candidate}):
                with mock.patch("Libs.android_ffmpeg._native_library_directories", return_value=[]):
                    with self.assertRaises(FileNotFoundError):
                        find_ffmpeg()
                    os.chmod(candidate, 0o755)
                    self.assertEqual(find_ffmpeg(), candidate)



class AndroidContentImportTests(unittest.TestCase):
    def test_image_format_recognition(self):
        from Libs.android_file_import import _thumbnail_extension
        self.assertEqual(_thumbnail_extension(bytes.fromhex("89504e470d0a1a0a")), ".png")
        self.assertEqual(_thumbnail_extension(bytes.fromhex("ffd8ffe0")), ".jpg")
        with self.assertRaises(ValueError):
            _thumbnail_extension(b"not-an-image")

    def test_stream_copy_size_and_empty_guards(self):
        import io
        import tempfile
        from pathlib import Path
        from Libs.android_file_import import _copy_limited_stream
        with tempfile.TemporaryDirectory() as dirname:
            dst = str(Path(dirname) / "import.bin")
            self.assertEqual(_copy_limited_stream(io.BytesIO(b"hello"), dst, 5), b"hello")
            self.assertEqual(Path(dst).read_bytes(), b"hello")
            with self.assertRaisesRegex(ValueError, "exceeds"):
                _copy_limited_stream(io.BytesIO(b"toolarge"), dst, 4)
            with self.assertRaisesRegex(ValueError, "empty"):
                _copy_limited_stream(io.BytesIO(b""), dst, 10)

if __name__ == "__main__":
    unittest.main()
