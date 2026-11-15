"""Real QR image generation with Android pure-Python encoder.

The returned QR must encode the patched TikTok URL, not an empty/base64
placeholder. No authentication request or credentials are involved.
"""
import base64
import io
import unittest
from unittest.mock import patch

import segno
import TiktokStreamKeyGenerator as app


class AndroidQrEncoderTests(unittest.TestCase):
    def test_generates_nonempty_png_for_patched_qr_login_url(self):
        url = "https://example.invalid/qr?next_url=tiktok&client_secret=mock-nonsecret"
        with patch.object(app, "is_android_runtime", return_value=True):
            encoded = app._qrcode_png_base64(url)
        raw = base64.b64decode(encoded)
        self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(raw), 100)

    def test_qr_png_writer_uses_pure_python(self):
        with patch.object(app, "is_android_runtime", return_value=True), \
             patch.object(segno, "make", wraps=segno.make) as encode:
            self.assertTrue(app._qrcode_png_base64("https://example.invalid/login"))
            encode.assert_called_once()


if __name__ == "__main__":
    unittest.main()
