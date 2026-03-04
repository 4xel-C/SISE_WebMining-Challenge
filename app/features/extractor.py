"""Feature extraction from raw keyboard/mouse events."""

import queue
import time
from collections import deque
from typing import Any

import numpy as np

WINDOW_SECONDS = 5
GAMING_KEYS = {
    "'a'",
    "'w'",
    "'s'",
    "'d'",
    "'z'",
    "'q'",
    "Key.up",
    "Key.down",
    "Key.left",
    "Key.right",
}
SPECIAL_KEYS = {
    "Key.ctrl",
    "Key.ctrl_l",
    "Key.ctrl_r",
    "Key.alt",
    "Key.alt_l",
    "Key.alt_r",
    "Key.shift",
    "Key.shift_l",
    "Key.shift_r",
    "Key.cmd",
    "Key.f1",
    "Key.f2",
    "Key.f3",
    "Key.f4",
    "Key.f5",
    "Key.f6",
    "Key.f7",
    "Key.f8",
    "Key.f9",
    "Key.f10",
    "Key.f11",
    "Key.f12",
}


class FeatureExtractor:
    """Consumes events from a queue and computes behavioral features over a sliding window."""

    def __init__(self, event_queue: queue.Queue):
        self._queue = event_queue
        self._window: deque[dict[str, Any]] = deque()

    def _drain_queue(self):
        """Pull all available events from queue into the window."""
        while True:
            try:
                event = self._queue.get_nowait()
                self._window.append(event)
            except queue.Empty:
                break

    def _evict_old(self):
        """Remove events older than WINDOW_SECONDS."""
        cutoff = time.time() - WINDOW_SECONDS
        while self._window and self._window[0]["time"] < cutoff:
            self._window.popleft()

    def extract(self) -> dict[str, float]:
        """Drain the queue, evict old events, and compute features."""
        self._drain_queue()
        self._evict_old()

        events = list(self._window)
        if not events:
            return self._zero_features()

        now = time.time()
        window_duration = (
            min(WINDOW_SECONDS, now - events[0]["time"]) if events else WINDOW_SECONDS
        )
        if window_duration <= 0:
            window_duration = WINDOW_SECONDS

        key_presses = [e for e in events if e["type"] == "key_press"]
        key_releases = [e for e in events if e["type"] == "key_release"]
        clicks = [e for e in events if e["type"] == "click"]
        moves = [e for e in events if e["type"] == "move"]
        scrolls = [e for e in events if e["type"] == "scroll"]

        # Keyboard features
        keys_per_sec = len(key_presses) / window_duration
        char_count = sum(1 for e in key_presses if len(e["key"]) == 3)  # 'x' format
        wpm = char_count / WINDOW_SECONDS * 12  # chars/5s * 12 = wpm

        dwells = [e["dwell"] for e in key_releases if e.get("dwell") is not None]
        mean_dwell = float(np.mean(dwells) * 1000) if dwells else 0.0  # ms
        std_dwell = float(np.std(dwells) * 1000) if dwells else 0.0

        flights = [
            e["flight_time"] for e in key_presses if e.get("flight_time") is not None
        ]
        mean_flight = float(np.mean(flights) * 1000) if flights else 0.0  # ms
        std_flight = float(np.std(flights) * 1000) if flights else 0.0

        total_keys = len(key_presses)
        special_count = sum(1 for e in key_presses if e["key"] in SPECIAL_KEYS)
        gaming_count = sum(1 for e in key_presses if e["key"].lower() in GAMING_KEYS)
        special_key_ratio = special_count / total_keys if total_keys else 0.0
        gaming_key_ratio = gaming_count / total_keys if total_keys else 0.0

        # Burst: consecutive key events with gap > 500ms
        burst_count = 0
        if len(key_presses) >= 2:
            for i in range(1, len(key_presses)):
                if key_presses[i]["time"] - key_presses[i - 1]["time"] > 0.5:
                    burst_count += 1

        # Pause ratio: fraction of window time spent in gaps > 500ms
        total_gap_time = 0.0
        if len(key_presses) >= 2:
            for i in range(1, len(key_presses)):
                gap = key_presses[i]["time"] - key_presses[i - 1]["time"]
                if gap > 0.5:
                    total_gap_time += gap
        pause_ratio = total_gap_time / window_duration if window_duration else 0.0

        # Mouse features
        clicks_per_sec = len(clicks) / window_duration

        move_speeds = [e["speed"] for e in moves if e.get("speed", 0) > 0]
        mean_move_speed = float(np.mean(move_speeds)) if move_speeds else 0.0

        scroll_events = len(scrolls)

        double_click_count = 0
        if len(clicks) >= 2:
            for i in range(1, len(clicks)):
                if clicks[i]["time"] - clicks[i - 1]["time"] < 0.3:
                    double_click_count += 1

        return {
            "keys_per_sec": keys_per_sec,
            "wpm": wpm,
            "mean_dwell": mean_dwell,
            "std_dwell": std_dwell,
            "mean_flight": mean_flight,
            "std_flight": std_flight,
            "special_key_ratio": special_key_ratio,
            "gaming_key_ratio": gaming_key_ratio,
            "burst_count": float(burst_count),
            "pause_ratio": pause_ratio,
            "clicks_per_sec": clicks_per_sec,
            "mean_move_speed": mean_move_speed,
            "scroll_events": float(scroll_events),
            "double_click_count": float(double_click_count),
        }

    def get_recent_events(self, n: int = 10) -> list[dict]:
        """Return the n most recent raw events for display."""
        return list(self._window)[-n:]

    def _zero_features(self) -> dict[str, float]:
        return {
            "keys_per_sec": 0.0,
            "wpm": 0.0,
            "mean_dwell": 0.0,
            "std_dwell": 0.0,
            "mean_flight": 0.0,
            "std_flight": 0.0,
            "special_key_ratio": 0.0,
            "gaming_key_ratio": 0.0,
            "burst_count": 0.0,
            "pause_ratio": 0.0,
            "clicks_per_sec": 0.0,
            "mean_move_speed": 0.0,
            "scroll_events": 0.0,
            "double_click_count": 0.0,
        }
