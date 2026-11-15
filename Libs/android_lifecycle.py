"""Keep the Qt event loop active while an Android LIVE app is not visible.

Qt 6's QT_BLOCK_EVENT_LOOPS_WHEN_SUSPENDED=0 opt-out is equivalent to
android.app.background_running=true. This does NOT replace an Android
foreground service and cannot prevent the OS from killing the process.
"""
import os

from Libs.app_paths import is_android_runtime


def configure_android_background_events():
    if is_android_runtime():
        os.environ.setdefault("QT_BLOCK_EVENT_LOOPS_WHEN_SUSPENDED", "0")


def configure_android_widget_rendering():
    """Avoid forcing Qt Widgets' RHI/OpenGL backing store on Android.

    These must be set before importing Qt; native Android surface recreation
    during startup dialogs can otherwise abort in QOpenGLContext::makeCurrent.
    """
    if is_android_runtime():
        os.environ["QT_WIDGETS_RHI"] = "0"
        os.environ["QT_WIDGETS_HIGHDPI_DOWNSCALE"] = "0"
