import os
import unittest
from unittest import mock

from Libs.android_lifecycle import configure_android_background_events


class AndroidQtLifecycleTests(unittest.TestCase):
    def test_android_keeps_event_loop_alive_during_encoder_switch(self):
        with mock.patch.dict(os.environ, {
            "ANDROID_PRIVATE": "/tmp/test-app-private",
        }, clear=True):
            configure_android_background_events()
            self.assertEqual(os.environ["QT_BLOCK_EVENT_LOOPS_WHEN_SUSPENDED"], "0")

    def test_user_override_preserved(self):
        with mock.patch.dict(os.environ, {
            "ANDROID_PRIVATE": "/tmp/test-app-private",
            "QT_BLOCK_EVENT_LOOPS_WHEN_SUSPENDED": "1",
        }, clear=True):
            configure_android_background_events()
            self.assertEqual(os.environ["QT_BLOCK_EVENT_LOOPS_WHEN_SUSPENDED"], "1")

    def test_not_set_on_desktop(self):
        from Libs.app_paths import is_android_runtime
        with mock.patch.dict(os.environ, {}, clear=True):
            if not is_android_runtime():
                configure_android_background_events()
                self.assertNotIn("QT_BLOCK_EVENT_LOOPS_WHEN_SUSPENDED", os.environ)


if __name__ == "__main__":
    unittest.main()
