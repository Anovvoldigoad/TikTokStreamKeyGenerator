"""Offline Android-port checks. No credentials or live TikTok calls."""
import os
import tempfile
import unittest
from unittest import mock

from Libs import app_paths


class AndroidPathTests(unittest.TestCase):
    def test_private_storage_not_app_source(self):
        with tempfile.TemporaryDirectory() as private:
            with mock.patch.dict(os.environ, {"ANDROID_PRIVATE": private}):
                self.assertTrue(app_paths.is_android_runtime())
                self.assertEqual(app_paths.user_data_dir(), private)
                self.assertEqual(app_paths.logs_dir(), os.path.join(private, "logs"))

    def test_non_android_refuses_android_private_lookup(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            if not app_paths.is_android_runtime():
                with self.assertRaises(RuntimeError):
                    app_paths.android_data_dir()


class SignerFallbackTests(unittest.TestCase):
    def test_compat_transport_has_signing_request_interface(self):
        from Libs.signer_http import requests
        self.assertTrue(callable(requests.post))
        self.assertTrue(hasattr(requests, "exceptions"))


class ProxyLifecycleTests(unittest.TestCase):
    def test_parser_uses_same_arguments_as_desktop(self):
        from Libs.ffmpeg_sei_proxy import parse_proxy_args
        args = parse_proxy_args([
            "--ffmpeg", "/bin/ffmpeg", "--listen-url", "rtmp://127.0.0.1:19350/live/obs",
            "--output-url", "rtmps://example.invalid/secret", "--room-id", "123",
        ])
        self.assertEqual(args.room_id, "123")
        self.assertEqual(args.device_type, "pc")

    def test_stop_ends_relay_without_reopening_listener(self):
        import io
        import argparse
        import threading
        from Libs import ffmpeg_sei_proxy as proxy

        stop = threading.Event()
        args = argparse.Namespace(device_type="pc", input_flv="listen", uid="",
                                  device_id="", room_id="", aid="8311",
                                  width=1920, height=1080, fps=60)
        class FakeSigner:
            def __init__(self, **kwargs):
                pass
            def start_initial_prefetch(self):
                pass
        def one_session(*args, **kwargs):
            stop.set()
            return 0
        with mock.patch.object(proxy, "LocalSeiSigner", FakeSigner), \
             mock.patch.object(proxy, "_relay_once", side_effect=one_session):
            self.assertEqual(
                proxy._run_proxy_with_log(args, io.StringIO(), stop_event=stop),
                0,
            )


if __name__ == "__main__":
    unittest.main()
