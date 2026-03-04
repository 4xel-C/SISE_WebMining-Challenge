"""
Mouse & Keyboard listener — saves captured events to Parquet files.

Output files (written on exit):
  mouse_events.parquet    — move / click / scroll rows
  keyboard_events.parquet — press / release rows

Stop recording:  Ctrl+C  (or press End)
"""

import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pynput import keyboard, mouse

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
mouse_events: list[dict] = []
keyboard_events: list[dict] = []

START_TS = time.perf_counter()
_stopping = threading.Event()


def _ts() -> float:
    """Seconds since the recording started (high-resolution)."""
    return round(time.perf_counter() - START_TS, 6)


def _wall() -> str:
    """Wall-clock ISO timestamp (UTC)."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


# ---------------------------------------------------------------------------
# Mouse callbacks
# ---------------------------------------------------------------------------
def on_move(x: int, y: int) -> None:
    mouse_events.append(
        {
            "wall_time": _wall(),
            "elapsed_s": _ts(),
            "event": "move",
            "x": x,
            "y": y,
            "button": None,
            "pressed": None,
            "scroll_dx": None,
            "scroll_dy": None,
        }
    )


def on_click(x: int, y: int, button: mouse.Button, pressed: bool) -> None:
    mouse_events.append(
        {
            "wall_time": _wall(),
            "elapsed_s": _ts(),
            "event": "click",
            "x": x,
            "y": y,
            "button": str(button),
            "pressed": pressed,
            "scroll_dx": None,
            "scroll_dy": None,
        }
    )


def on_scroll(x: int, y: int, dx: int, dy: int) -> None:
    mouse_events.append(
        {
            "wall_time": _wall(),
            "elapsed_s": _ts(),
            "event": "scroll",
            "x": x,
            "y": y,
            "button": None,
            "pressed": None,
            "scroll_dx": dx,
            "scroll_dy": dy,
        }
    )


# ---------------------------------------------------------------------------
# Keyboard callbacks
# ---------------------------------------------------------------------------
def _key_name(key) -> str:
    """Return a clean string representation of a key."""
    try:
        return key.char  # printable character
    except AttributeError:
        return str(key)  # special key like Key.space


def on_press(key) -> None:
    key_str = _key_name(key)
    print(f"[KEY PRESS] {key_str}", flush=True)
    # Stop on End
    if key == keyboard.Key.end:
        save_and_exit(reason="End key pressed")
    keyboard_events.append(
        {
            "wall_time": _wall(),
            "elapsed_s": _ts(),
            "event": "press",
            "key": key_str,
        }
    )


def on_release(key) -> None:
    keyboard_events.append(
        {
            "wall_time": _wall(),
            "elapsed_s": _ts(),
            "event": "release",
            "key": _key_name(key),
        }
    )


def on_keyboard_error(exc) -> None:
    """Called by pynput when the keyboard listener thread crashes."""
    print(f"[KEYBOARD LISTENER ERROR] {type(exc).__name__}: {exc}", flush=True)
    save_and_exit(reason=f"keyboard listener error: {exc}")


# ---------------------------------------------------------------------------
# Save & exit
# ---------------------------------------------------------------------------
def save_and_exit(*_, reason: str = "unknown") -> None:
    if _stopping.is_set():
        return
    _stopping.set()
    print(f"\nStopping listeners … (triggered by: {reason})", flush=True)

    out_dir = Path(__file__).parent

    # Mouse
    mouse_path = out_dir / "mouse_events.parquet"
    if mouse_events:
        df_mouse = pd.DataFrame(mouse_events)
        df_mouse["wall_time"] = pd.to_datetime(df_mouse["wall_time"], utc=True)
        df_mouse.to_parquet(mouse_path, index=False)
        print(f"Mouse  → {mouse_path}  ({len(df_mouse):,} rows)")
    else:
        print("Mouse  → no events recorded.")

    # Keyboard
    kb_path = out_dir / "keyboard_events.parquet"
    if keyboard_events:
        df_kb = pd.DataFrame(keyboard_events)
        df_kb["wall_time"] = pd.to_datetime(df_kb["wall_time"], utc=True)
        df_kb.to_parquet(kb_path, index=False)
        print(f"Keybd  → {kb_path}  ({len(df_kb):,} rows)")
    else:
        print("Keybd  → no events recorded.")

    sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: save_and_exit(reason="SIGINT (Ctrl+C)"))
    signal.signal(signal.SIGTERM, lambda *_: save_and_exit(reason="SIGTERM (kill)"))

    print("Recording …  (press End or Ctrl+C to stop and save)")

    mouse_listener = mouse.Listener(
        on_move=on_move,
        on_click=on_click,
        on_scroll=on_scroll,
    )
    kb_listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release,
    )

    mouse_listener.start()
    kb_listener.start()

    # Keep the main thread alive; if either listener dies unexpectedly, report it
    while mouse_listener.is_alive() and kb_listener.is_alive():
        mouse_listener.join(timeout=0.5)
        kb_listener.join(timeout=0.5)

    # Check if a listener thread stored an exception (attribute may not exist on all pynput builds)
    kb_exc = getattr(kb_listener, "exception", None)
    mouse_exc = getattr(mouse_listener, "exception", None)
    if not kb_listener.is_alive() and kb_exc:
        save_and_exit(reason=f"keyboard listener crashed: {kb_exc}")
    elif not mouse_listener.is_alive() and mouse_exc:
        save_and_exit(reason=f"mouse listener crashed: {mouse_exc}")
    else:
        save_and_exit(reason="listener(s) exited unexpectedly (no exception)")
