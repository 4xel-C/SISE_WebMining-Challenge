"""
Dashboard routes — GET only, consumed by frontend/index.html.

Reads live data directly from keysentinel.db (SQLite via SQLAlchemy).
Active session = most recent RecordingSession with ending_at IS NULL.
"""

import math
import time

from flask import Blueprint, jsonify, request

from app.models.schema import (
    KeyboardEvent,
    MouseEvent,
    RecordingSession,
    get_session,
)

dashboard = Blueprint("dashboard", __name__)

_GAMING_KEYS = {"w", "a", "s", "d", "Key.up", "Key.down", "Key.left", "Key.right"}
_WINDOW_S = 10.0  # sliding window for live features


def _active_session(db):
    """Return the most recent open RecordingSession (ending_at IS NULL), or None."""
    return (
        db.query(RecordingSession)
        .filter(RecordingSession.ending_at.is_(None))
        .order_by(RecordingSession.started_at.desc())
        .first()
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
@dashboard.get("/api/status")
def api_status():
    """
    Returns the current session state.

    Response shape:
        {
            "user":     str | null,
            "activity": "coding" | "writing" | "gaming" | null,
            "active":   bool
        }
    """
    try:
        with get_session() as db:
            sess = _active_session(db)
            if sess is None:
                return jsonify({"user": None, "activity": None, "active": False})
            user_name = sess.user.name if sess.user else None
            activity = sess.activity.label.value if sess.activity else None
        return jsonify({"user": user_name, "activity": activity, "active": True})
    except Exception:
        return jsonify({"user": None, "activity": None, "active": False})


# ---------------------------------------------------------------------------
# Live features  (last 10-second sliding window)
# ---------------------------------------------------------------------------
@dashboard.get("/api/features/live")
def api_features_live():
    """
    Computes features on the last 10 s of recorded events.

    Response shape:
        {
            "wpm":              float,
            "keys_per_sec":     float,
            "mouse_speed":      float,   # px/s average
            "click_rate":       float,   # clicks/s
            "gaming_key_ratio": float,   # WASD+arrows / total keys
            "mean_dwell":       float    # ms key held
        }
    """
    _empty = {
        "wpm": None,
        "keys_per_sec": None,
        "mouse_speed": None,
        "click_rate": None,
        "gaming_key_ratio": None,
        "mean_dwell": None,
    }
    now = time.time()
    cutoff = now - _WINDOW_S
    try:
        with get_session() as db:
            sess = _active_session(db)
            if sess is None:
                return jsonify(_empty)
            sid = sess.id

            key_presses = (
                db.query(KeyboardEvent)
                .filter(
                    KeyboardEvent.recording_session_id == sid,
                    KeyboardEvent.event_type == "key_press",
                    KeyboardEvent.timestamp >= cutoff,
                )
                .all()
            )
            key_releases = (
                db.query(KeyboardEvent)
                .filter(
                    KeyboardEvent.recording_session_id == sid,
                    KeyboardEvent.event_type == "key_release",
                    KeyboardEvent.timestamp >= cutoff,
                    KeyboardEvent.dwell.isnot(None),
                )
                .all()
            )
            mouse_moves = (
                db.query(MouseEvent)
                .filter(
                    MouseEvent.recording_session_id == sid,
                    MouseEvent.event_type == "move",
                    MouseEvent.timestamp >= cutoff,
                )
                .all()
            )
            mouse_click_count = (
                db.query(MouseEvent)
                .filter(
                    MouseEvent.recording_session_id == sid,
                    MouseEvent.event_type == "click",
                    MouseEvent.timestamp >= cutoff,
                )
                .count()
            )

            # All attribute accesses happen inside the session context
            wpm = (len(key_presses) / 5) / (_WINDOW_S / 60)
            kps = len(key_presses) / _WINDOW_S
            click_rate = mouse_click_count / _WINDOW_S
            gaming_keys = sum(1 for e in key_presses if e.key in _GAMING_KEYS)
            gaming_ratio = gaming_keys / len(key_presses) if key_presses else 0.0
            mean_dwell = (
                round(sum(e.dwell for e in key_releases) / len(key_releases) * 1000, 1)
                if key_releases
                else None
            )
            speeds = [e.speed for e in mouse_moves if e.speed is not None]
            mouse_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0.0

            payload = {
                "wpm": round(wpm, 2),
                "keys_per_sec": round(kps, 3),
                "mouse_speed": mouse_speed,
                "click_rate": round(click_rate, 3),
                "gaming_key_ratio": round(gaming_ratio, 3),
                "mean_dwell": mean_dwell,
            }

        return jsonify(payload)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Live prediction  (ground truth for now — ML in Phase 2)
# ---------------------------------------------------------------------------
@dashboard.get("/api/predict/live")
def api_predict_live():
    """
    Returns the activity label of the active session as ground truth.

    Response shape:
        {
            "activity":      "coding" | "writing" | "gaming" | null,
            "confidence":    float | null,
            "probabilities": { "coding": float, "writing": float, "gaming": float }
        }
    """
    _null = {
        "activity": None,
        "confidence": None,
        "probabilities": {"coding": None, "writing": None, "gaming": None},
    }
    try:
        with get_session() as db:
            sess = _active_session(db)
            if sess is None:
                return jsonify(_null)
            activity = sess.activity.label.value if sess.activity else None

        if activity is None:
            return jsonify(_null)

        probs = {"coding": 0.0, "writing": 0.0, "gaming": 0.0}
        if activity in probs:
            probs[activity] = 1.0

        return jsonify(
            {"activity": activity, "confidence": 1.0, "probabilities": probs}
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Recent raw events  (for live feed display)
# ---------------------------------------------------------------------------
@dashboard.get("/api/events/recent")
def api_events_recent():
    """
    Returns the N most recent raw input events for the active session.

    Query params: n (default 20), since (float epoch, default 0)

    Response shape:
        [{ "ts": float, "time": "HH:MM:SS", "device": str,
           "event_type": str, "detail": str }, ...]
    """
    n = request.args.get("n", 20, type=int)
    since = request.args.get("since", 0.0, type=float)
    try:
        with get_session() as db:
            sess = _active_session(db)
            if sess is None:
                return jsonify([])
            sid = sess.id

            kb_rows = (
                db.query(KeyboardEvent)
                .filter(
                    KeyboardEvent.recording_session_id == sid,
                    KeyboardEvent.timestamp > since,
                )
                .order_by(KeyboardEvent.timestamp.desc())
                .limit(n)
                .all()
            )
            mouse_rows = (
                db.query(MouseEvent)
                .filter(
                    MouseEvent.recording_session_id == sid,
                    MouseEvent.timestamp > since,
                )
                .order_by(MouseEvent.timestamp.desc())
                .limit(n)
                .all()
            )

            result = []
            for e in kb_rows:
                result.append(
                    {
                        "ts": e.timestamp,
                        "time": time.strftime("%H:%M:%S", time.localtime(e.timestamp)),
                        "device": "keyboard",
                        "event_type": (
                            "press" if e.event_type == "key_press" else "release"
                        ),
                        "detail": e.key,
                    }
                )
            for e in mouse_rows:
                if e.event_type == "move":
                    detail = f"({e.x}, {e.y})"
                elif e.event_type == "click":
                    detail = f"{e.button or ''} ({e.x}, {e.y})"
                elif e.event_type == "scroll":
                    detail = f"dy={e.scroll_dy} ({e.x}, {e.y})"
                else:
                    detail = f"({e.x}, {e.y})"
                result.append(
                    {
                        "ts": e.timestamp,
                        "time": time.strftime("%H:%M:%S", time.localtime(e.timestamp)),
                        "device": "mouse",
                        "event_type": e.event_type,
                        "detail": detail,
                    }
                )

        result.sort(key=lambda x: x["ts"], reverse=True)
        return jsonify(result[:n])
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Session history  (for future sessions list / replay selection)
# ---------------------------------------------------------------------------
@dashboard.get("/api/sessions")
def api_sessions():
    """
    Returns all recorded sessions.

    Response shape:
        [
            {
                "id":          str,
                "user":        str,
                "activity":    str,
                "started_at":  str (ISO),
                "ended_at":    str (ISO) | null,
                "event_count": int
            },
            …
        ]
    """
    return jsonify(store.get_sessions())
