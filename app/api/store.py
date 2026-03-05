"""
app/api/store.py — in-memory data store (no DB required for testing).

Shared between:
  - agent routes  (POST)  → writes via session_start / ingest / session_stop
  - dashboard routes (GET) → reads via get_* helpers

État remis à zéro au redémarrage du serveur Flask.
Remplacer par SQLAlchemy quand la base SQLite sera branchée.
"""

import math
import threading
import time
from collections import deque

import app.services.ml_service as ml_service

_lock = threading.Lock()

# ── Session courante ───────────────────────────────────────────────────────────
_session: dict = {
    "id": None,
    "user": None,
    "activity": None,  # "coding" | "gaming" | "writing"
    "active": False,
    "started_at": None,
}

# ── Ring buffer d'événements bruts (max 5 000) ─────────────────────────────────
_events: deque = deque(maxlen=5_000)

# ── Historique des sessions ────────────────────────────────────────────────────
_sessions: list[dict] = []
_next_id: int = 1

# ── Touches gaming (WASD + flèches) ───────────────────────────────────────────
_GAMING_KEYS = {"w", "a", "s", "d", "Key.up", "Key.down", "Key.left", "Key.right"}


# ──────────────────────────────────────────────────────────────────────────────
#  Écriture  (appelé par les routes agent)
# ──────────────────────────────────────────────────────────────────────────────


def session_start(user: str, activity: str | None) -> int:
    global _session, _next_id
    with _lock:
        sid = _next_id
        _next_id += 1
        _session = {
            "id": sid,
            "user": user,
            "activity": activity,
            "active": True,
            "started_at": time.time(),
        }
        _events.clear()
        return sid


def ingest(events: list[dict]) -> int:
    with _lock:
        for ev in events:
            _events.append(ev)
    return len(events)


def session_stop() -> dict:
    with _lock:
        _session["active"] = False
        count = len(_events)
        if _session["id"] is not None:
            _sessions.append(
                {
                    "id": str(_session["id"]),
                    "user": _session["user"],
                    "activity": _session["activity"],
                    "started_at": _session["started_at"],
                    "ended_at": time.time(),
                    "event_count": count,
                }
            )
        return {"event_count": count}


# ──────────────────────────────────────────────────────────────────────────────
#  Lecture  (appelé par les routes dashboard)
# ──────────────────────────────────────────────────────────────────────────────


def get_status() -> dict:
    with _lock:
        return {
            "user": _session["user"],
            "activity": _session["activity"],
            "active": _session["active"],
        }


def get_sessions() -> list[dict]:
    with _lock:
        return list(_sessions)


def get_recent_events(n: int = 20, since: float = 0.0) -> list[dict]:
    """Retourne au plus n événements avec ts > since, formatés pour le frontend."""
    with _lock:
        raw = [ev for ev in _events if ev.get("ts", 0) > since]

    # Prend les n derniers (les plus récents)
    raw = raw[-n:]

    result = []
    for ev in reversed(raw):  # du plus récent au plus ancien
        ts = ev.get("ts", 0)
        t = time.strftime("%H:%M:%S", time.localtime(ts))
        data = ev.get("data", {})
        etype = data.get("event_type", "")
        device = ev.get("type", "")

        if etype == "press":
            detail = data.get("key", "")
        elif etype in ("move", "click", "scroll"):
            x, y = int(data.get("x", 0)), int(data.get("y", 0))
            detail = f"({x}, {y})"
            if etype == "click":
                btn = data.get("button", "")
                pressed = data.get("pressed", True)
                detail = f"{btn} {'↓' if pressed else '↑'} {detail}"
            elif etype == "scroll":
                detail = f"dy={data.get('dy', 0):.1f} {detail}"
        else:
            detail = ""

        result.append(
            {
                "ts": ts,
                "time": t,
                "device": device,
                "event_type": etype,
                "detail": detail,
            }
        )
    return result


def get_live_features() -> dict:
    """Calcule les features sur la dernière fenêtre de 10 s."""
    now = time.time()
    window = 10.0
    cutoff = now - window

    with _lock:
        recent = [ev for ev in _events if ev.get("ts", 0) >= cutoff]

    key_presses = [
        ev
        for ev in recent
        if ev["type"] == "keyboard" and ev["data"]["event_type"] == "press"
    ]
    mouse_moves = [
        ev
        for ev in recent
        if ev["type"] == "mouse" and ev["data"]["event_type"] == "move"
    ]
    mouse_clicks = [
        ev
        for ev in recent
        if ev["type"] == "mouse"
        and ev["data"]["event_type"] == "click"
        and ev["data"].get("pressed", False)
    ]

    # WPM  (hypothèse : 5 frappes = 1 mot)
    wpm = (len(key_presses) / 5) / (window / 60)

    # Frappes / seconde
    kps = len(key_presses) / window

    # Vitesse souris (px/s)
    speed_sum = 0.0
    for i in range(1, len(mouse_moves)):
        dx = mouse_moves[i]["data"]["x"] - mouse_moves[i - 1]["data"]["x"]
        dy = mouse_moves[i]["data"]["y"] - mouse_moves[i - 1]["data"]["y"]
        dt = mouse_moves[i]["ts"] - mouse_moves[i - 1]["ts"]
        if dt > 0:
            speed_sum += math.hypot(dx, dy) / dt
    mouse_speed = (speed_sum / (len(mouse_moves) - 1)) if len(mouse_moves) > 1 else 0.0

    # Taux de clics / s
    click_rate = len(mouse_clicks) / window

    # Ratio touches gaming (WASD + flèches)
    gaming_keys = sum(1 for ev in key_presses if ev["data"]["key"] in _GAMING_KEYS)
    gaming_ratio = gaming_keys / len(key_presses) if key_presses else 0.0

    return {
        "wpm": round(wpm, 2),
        "keys_per_sec": round(kps, 3),
        "mouse_speed": round(mouse_speed, 1),
        "click_rate": round(click_rate, 3),
        "gaming_key_ratio": round(gaming_ratio, 3),
        "mean_dwell": None,  # corrélation press↔release — futur
    }


def get_live_prediction() -> dict:
    with _lock:
        recent = list(_events)
    return ml_service.predict(recent)
