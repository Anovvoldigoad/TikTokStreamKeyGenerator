"""Android-managed signed RTMP relay.

Desktop launches Libs.ffmpeg_sei_proxy in child CPython. Embedded Android
Python cannot be spawned as sys.executable, so run that *same* relay code in
a thread while its FFmpeg listen/push commands remain subprocesses.

The interface intentionally matches only the Popen calls the GUI uses.
"""
import subprocess
import threading

from Libs.error_reporting import write_proxy_error
from Libs.ffmpeg_sei_proxy import parse_proxy_args, _run_proxy


class AndroidProxyProcess:
    def __init__(self, proxy_arguments):
        self.args = parse_proxy_args(proxy_arguments)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._processes = []
        self._exit_code = None
        self._thread = threading.Thread(
            target=self._run, name="android-signed-rtmp-proxy", daemon=True
        )
        self._thread.start()

    def _track(self, process):
        with self._lock:
            self._processes.append(process)
            stopped = self._stop.is_set()
        if stopped:
            self._terminate_child(process)

    @staticmethod
    def _terminate_child(process):
        try:
            if process.poll() is None:
                process.terminate()
        except (OSError, ValueError):
            pass

    def _run(self):
        try:
            self._exit_code = _run_proxy(
                self.args, stop_event=self._stop, on_process_start=self._track
            )
        except Exception as exc:
            write_proxy_error(self.args.error_report, exc)
            self._exit_code = 1

    def poll(self):
        return None if self._thread.is_alive() else self._exit_code

    def terminate(self):
        self._stop.set()
        with self._lock:
            processes = tuple(self._processes)
        for process in processes:
            self._terminate_child(process)

    def kill(self):
        self.terminate()
        with self._lock:
            processes = tuple(self._processes)
        for process in processes:
            try:
                if process.poll() is None:
                    process.kill()
            except (OSError, ValueError):
                pass

    def wait(self, timeout=None):
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            raise subprocess.TimeoutExpired("android-signed-rtmp-proxy", timeout)
        return self._exit_code
