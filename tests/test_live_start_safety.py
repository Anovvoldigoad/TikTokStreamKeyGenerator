"""Offline contract tests for cleanup of failed Android LIVE starts."""
import unittest
from unittest.mock import Mock

from Libs.live_start_safety import end_new_room_if_allocated


class NewRoomSafetyTests(unittest.TestCase):
    def test_new_room_is_ended_with_exact_ids(self):
        stream = Mock(roomId="198765432109", streamId="738247")
        self.assertTrue(end_new_room_if_allocated(
            stream, previous_room_id="777", device_id="did", install_id="iid",
            priority_region="id"))
        stream.endStream.assert_called_once_with(
            room_id="198765432109", stream_id="738247",
            device_id="did", install_id="iid", priority_region="id")

    def test_preexisting_room_is_never_ended(self):
        stream = Mock(roomId="777", streamId="999")
        self.assertFalse(end_new_room_if_allocated(stream, previous_room_id="777"))
        stream.endStream.assert_not_called()

    def test_missing_or_zero_ids_do_not_send_finish(self):
        for room, stream_id in [("", "123"), ("123", ""), ("0", "123"), ("123", "0")]:
            with self.subTest(room=room, stream_id=stream_id):
                stream = Mock(roomId=room, streamId=stream_id)
                self.assertFalse(end_new_room_if_allocated(stream))
                stream.endStream.assert_not_called()

    def test_cleanup_error_is_not_hidden(self):
        stream = Mock(roomId="123", streamId="345")
        stream.endStream.side_effect = RuntimeError("TikTok denied closing")
        with self.assertRaisesRegex(RuntimeError, "denied closing"):
            end_new_room_if_allocated(stream)


if __name__ == "__main__":
    unittest.main()
