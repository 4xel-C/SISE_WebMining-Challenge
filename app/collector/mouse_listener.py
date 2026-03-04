"""Mouse event listener using pynput."""

import queue
import time

from pynput import mouse


class MouseListener:
    """Listens for mouse events and pushes them to a shared queue."""

    def __init__(self, event_queue: queue.Queue):
        self._queue = event_queue
        self._listener: mouse.Listener | None = None
        self._last_pos: tuple[int, int] | None = None
        self._last_move_time: float | None = None

    def _on_click(self, x, y, button, pressed):
        if pressed:
            self._queue.put(
                {
                    "type": "click",
                    "x": x,
                    "y": y,
                    "button": str(button),
                    "time": time.time(),
                }
            )

    def _on_move(self, x, y):
        now = time.time()
        if self._last_pos and self._last_move_time:
            dx = x - self._last_pos[0]
            dy = y - self._last_pos[1]
            dt = now - self._last_move_time
            speed = ((dx**2 + dy**2) ** 0.5 / dt) if dt > 0 else 0
        else:
            speed = 0
        self._last_pos = (x, y)
        self._last_move_time = now
        self._queue.put(
            {
                "type": "move",
                "x": x,
                "y": y,
                "speed": speed,
                "time": now,
            }
        )

    def _on_scroll(self, x, y, dx, dy):
        self._queue.put(
            {
                "type": "scroll",
                "x": x,
                "y": y,
                "dx": dx,
                "dy": dy,
                "time": time.time(),
            }
        )

    def start(self):
        self._listener = mouse.Listener(
            on_click=self._on_click,
            on_move=self._on_move,
            on_scroll=self._on_scroll,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
