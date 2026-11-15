"""Android deployment entrypoint; preserve the existing desktop application."""
import os

# Never load local development signing algorithms into a release APK.
os.environ["TIKTOK_SIGNER_MODE"] = "api"

from Libs.android_lifecycle import configure_android_background_events

# Qt stops its event loop when an Android activity is suspended unless this
# policy is set before importing Qt. The local RTMP encoder may run in another
# app, so heartbeats cannot depend on an always-visible GUI.
configure_android_background_events()

from TiktokStreamKeyGenerator import main


if __name__ == "__main__":
    main()
