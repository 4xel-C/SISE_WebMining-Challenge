"""
agent/listeners.py — pynput listener factories.

Single responsibility: translate raw pynput events into dicts and push them
to a callback.  No HTTP, no state, no threading decisions here.
"""

import threading
import time
from typing import Callable

from pynput import keyboard, mouse


def _ts() -> float:
    return time.time()


def _key_str(key) -> str:
    if hasattr(key, "char") and key.char:
        return key.char
    return str(key)


def make_mouse_listener(push: Callable, stop: Callable) -> mouse.Listener:
    """Return a mouse.Listener that pushes normalised event dicts."""

    def on_move(x, y):
        push(
            {
                "type": "mouse",
                "ts": _ts(),
                "data": {"event_type": "move", "x": x, "y": y},
            }
        )

    def on_click(x, y, button, pressed):
        if not pressed:
            return  # ignore button-release events; only count button-down
        push(
            {
                "type": "mouse",
                "ts": _ts(),
                "data": {
                    "event_type": "click",
                    "x": x,
                    "y": y,
                    "button": str(button),
                    "pressed": pressed,
                },
            }
        )

    def on_scroll(x, y, dx, dy):
        push(
            {
                "type": "mouse",
                "ts": _ts(),
                "data": {"event_type": "scroll", "x": x, "y": y, "dx": dx, "dy": dy},
            }
        )

    return mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)


def make_keyboard_listener(
    push: Callable,
    stop: Callable,
    stop_event: threading.Event,
) -> keyboard.Listener:
    """Return a keyboard.Listener; END key triggers stop()."""

    def on_press(key):
        if stop_event.is_set():
            return
        if key == keyboard.Key.end:
            threading.Thread(target=stop, daemon=True).start()
            return
        push(
            {
                "type": "keyboard",
                "ts": _ts(),
                "data": {"event_type": "press", "key": _key_str(key)},
            }
        )

    def on_release(key):
        if stop_event.is_set():
            return
        push(
            {
                "type": "keyboard",
                "ts": _ts(),
                "data": {"event_type": "release", "key": _key_str(key)},
            }
        )

    return keyboard.Listener(on_press=on_press, on_release=on_release)
