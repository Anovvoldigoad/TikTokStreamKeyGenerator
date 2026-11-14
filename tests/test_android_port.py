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


if __name__ == "__main__":
    unittest.main()
