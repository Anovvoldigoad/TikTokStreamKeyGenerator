"""Exercise the original signed-SEI FLV injection, without TikTok/network.

A real FFmpeg/OBS/Android stream must still be tested on device. This test
catches regressions in the exact FLV output passed to the RTMP publisher.
"""
import io
import struct
import unittest

from Libs.ffmpeg_sei_proxy import inject_stream


def flv_video_tag(timestamp_ms, payload):
    data_len = len(payload).to_bytes(3, "big")
    timestamp = timestamp_ms.to_bytes(4, "big")
    header = (b"\x09" + data_len + timestamp[1:]
              + timestamp[:1] + b"\x00\x00\x00")
    return header + payload + struct.pack(">I", len(payload) + 11)


class FakeSigner:
    def __init__(self):
        self.began = False

    def begin_session(self):
        self.began = True

    def startup_signed_payload(self, **_):
        return b'JSON{"signResult":{"signvalue":"test-startup"}}'

    def small_payload(self, **_):
        return b'JSON{"test":"small"}'

    def reused_signed_payload(self):
        return b'JSON{"test":"reuse"}'

    def should_refresh_signature(self, *_):
        return False

    def signed_payload(self, **_):
        return b'JSON{"test":"renew"}'


class AndroidFlvSeiContractTests(unittest.TestCase):
    def test_tiktok_sei_is_inserted_and_flv_tag_sizes_recomputed(self):
        # H264 AVC NALU packet: 0x17=keyframe/AVC, 0x01=NALU, 3-byte CTS.
        video = b"\x17\x01\x00\x00\x00" + struct.pack(">I", 2) + b"\x65\x88"
        raw = (b"FLV\x01\x01\x00\x00\x00\x09" + b"\x00" * 4
               + flv_video_tag(0, video))
        signer = FakeSigner()
        sink, log = io.BytesIO(), io.StringIO()
        inject_stream(io.BytesIO(raw), lambda: sink, signer, 30, log)
        output = sink.getvalue()
        self.assertTrue(signer.began)
        self.assertTrue(output.startswith(b"FLV"))
        self.assertIn(b"JSON", output)
        self.assertIn(b'"test":"small"', output)
        self.assertIn(b"test\\\"small", output)
        size = int.from_bytes(output[14:17], "big")
        self.assertGreater(size, len(video))
        self.assertEqual(len(output), 13 + 11 + size + 4)
        self.assertEqual(struct.unpack(">I", output[-4:])[0], size + 11)
        self.assertIn("injected total=", log.getvalue())


if __name__ == "__main__":
    unittest.main()
