"""Pure feature extraction from a list of raw keyboard/mouse events."""

import numpy as np

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

FEATURE_NAMES = [
    "keys_per_sec",
    "wpm",
    "mean_dwell",
    "std_dwell",
    "mean_flight",
    "std_flight",
    "special_key_ratio",
    "gaming_key_ratio",
    "burst_count",
    "pause_ratio",
    "clicks_per_sec",
    "mean_move_speed",
    "scroll_events",
    "double_click_count",
]


def extract_features(events: list[dict], window_size: float) -> dict[str, float]:
    """
    Compute behavioral features from a flat list of raw events.

    Each event is a dict with at minimum:
        - "type": "key_press" | "key_release" | "click" | "move" | "scroll"
        - "time" or "timestamp": Unix timestamp (float)

    Args:
        events:      Raw events from keyboard/mouse listeners or DB rows.
        window_size: Duration of the window in seconds (used to compute rates).

    Returns:
        Dict mapping feature name -> float value.
    """
    if not events or window_size <= 0:
        return _zero_features()

    def ts(e: dict) -> float:
        return e.get("time") or e.get("timestamp") or 0.0

    key_presses = [e for e in events if e["type"] == "key_press"]
    key_releases = [e for e in events if e["type"] == "key_release"]
    clicks = [e for e in events if e["type"] == "click"]
    moves = [e for e in events if e["type"] == "move"]
    scrolls = [e for e in events if e["type"] == "scroll"]

    total_keys = len(key_presses)
    ws = window_size

    # --- Keyboard ---
    keys_per_sec = total_keys / ws

    char_count = sum(1 for e in key_presses if len(e["key"]) == 3)  # 'x' format
    wpm = char_count / ws * 12

    dwells = [e["dwell"] for e in key_releases if e.get("dwell") is not None]
    mean_dwell = float(np.mean(dwells) * 1000) if dwells else 0.0
    std_dwell = float(np.std(dwells) * 1000) if len(dwells) > 1 else 0.0

    flights = [
        e["flight_time"] for e in key_presses if e.get("flight_time") is not None
    ]
    mean_flight = float(np.mean(flights) * 1000) if flights else 0.0
    std_flight = float(np.std(flights) * 1000) if len(flights) > 1 else 0.0

    gaming_count = sum(1 for e in key_presses if e["key"].lower() in GAMING_KEYS)
    special_count = sum(1 for e in key_presses if e["key"] in SPECIAL_KEYS)
    gaming_key_ratio = gaming_count / total_keys if total_keys else 0.0
    special_key_ratio = special_count / total_keys if total_keys else 0.0

    burst_count = 0
    total_gap_time = 0.0
    if len(key_presses) >= 2:
        times = sorted(ts(e) for e in key_presses)
        gaps = [times[i] - times[i - 1] for i in range(1, len(times))]
        burst_count = sum(1 for g in gaps if g > 0.5)
        total_gap_time = sum(g for g in gaps if g > 0.5)
    pause_ratio = total_gap_time / ws

    # --- Mouse ---
    clicks_per_sec = len(clicks) / ws

    move_speeds = [e["speed"] for e in moves if e.get("speed", 0) > 0]
    mean_move_speed = float(np.mean(move_speeds)) if move_speeds else 0.0

    scroll_events = len(scrolls)

    double_click_count = 0
    if len(clicks) >= 2:
        click_times = sorted(ts(e) for e in clicks)
        double_click_count = sum(
            1
            for i in range(1, len(click_times))
            if click_times[i] - click_times[i - 1] < 0.3
        )

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


def _zero_features() -> dict[str, float]:
    return {name: 0.0 for name in FEATURE_NAMES}
