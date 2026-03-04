"""Keyboard event listener using pynput."""

import queue
import threading
import time

from pynput import keyboard


class KeyboardListener:
    """Listens for keyboard events and pushes them to a shared queue."""

    def __init__(self, event_queue: queue.Queue):
        self._queue = event_queue
        self._press_times: dict[str, float] = {}
        self._last_release_time: float | None = None
        self._listener: keyboard.Listener | None = None
        self._thread: threading.Thread | None = None

    def _key_str(self, key) -> str:
        try:
            return key.char if key.char else str(key)
        except AttributeError:
            return str(key)

    def _on_press(self, key):
        now = time.time()
        key_name = self._key_str(key)
        self._press_times[key_name] = now
        self._queue.put(
            {
                "type": "key_press",
                "key": key_name,
                "time": now,
                "flight_time": (now - self._last_release_time)
                if self._last_release_time
                else None,
            }
        )

    def _on_release(self, key):
        now = time.time()
        key_name = self._key_str(key)
        press_time = self._press_times.pop(key_name, None)
        dwell = (now - press_time) if press_time else None
        self._last_release_time = now
        self._queue.put(
            {
                "type": "key_release",
                "key": key_name,
                "time": now,
                "dwell": dwell,
            }
        )

    def start(self):
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
