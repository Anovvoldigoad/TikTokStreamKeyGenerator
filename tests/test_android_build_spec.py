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
        )
        target = configure(src)
        self.assertIn("requirements = " + REQUIREMENTS, target)
        self.assertIn("android.add_libs_arm64_v8a = " + FFMPEG_LIB, target)
        self.assertIn("source.include_exts = py,png,jpg,kv,atlas,qml,js,json,svg,ttf,otf,ico,webp,pem", target)
        self.assertIn("p4a.bootstrap = qt", target)
        self.assertIn("android.permissions = INTERNET", target)

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


if __name__ == "__main__":
    unittest.main()
