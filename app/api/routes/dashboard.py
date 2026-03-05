"""
Dashboard routes — GET only, consumed by frontend/index.html.

Reads live data directly from the database (SQLAlchemy).
Active session = most recent RecordingSession with ending_at IS NULL.

Background prediction loop (every 10 s):
  - Extracts features from the last 10 s of events for the active session.
  - Runs the Random Forest model to get activity probabilities.
  - Increments coding_time / writing_time / gaming_time on the session row.
  - Caches the last prediction so /api/predict/live is instant (no DB query).
"""

import math
import threading
import time

from flask import Blueprint, jsonify, request

from app.models.schema import (
    KeyboardEvent,
    MouseEvent,
    RecordingSession,
    _DB_URL,
    get_session,
)

dashboard = Blueprint("dashboard", __name__)

_GAMING_KEYS = {"w", "a", "s", "d", "Key.up", "Key.down", "Key.left", "Key.right"}
_WINDOW_S = 10.0  # sliding window for live features
_PREDICT_INTERVAL = 10.0  # seconds between background predictions

# ---------------------------------------------------------------------------
# Background prediction state (written by bg thread, read by /api/predict/live)
# ---------------------------------------------------------------------------
_pred_lock = threading.Lock()
_last_pred: dict = {
    "activity": None,
    "confidence": None,
    "probabilities": {"coding": None, "writing": None, "gaming": None},
}


def _run_prediction_loop():
    """Background thread: predict every 10 s and accumulate activity time in DB."""
    # Lazy imports to avoid circular deps at module load time
    from app.services.feature_service import FeatureService
    from app.services.ml_service import load_model, predict_from_events

    load_model()
    feat_svc = FeatureService(db_url=_DB_URL)

    while True:
        time.sleep(_PREDICT_INTERVAL)
        try:
            # 1. Find the active session and its user
            with get_session() as db:
                sess = _active_session(db)
                if sess is None:
                    continue
                session_id = sess.id
                username = sess.user.name if sess.user else None

            if not username:
                continue

            # 2. Fetch last 10 s of events and run model
            kb, ms = feat_svc.fetch_events(username, window_size=_PREDICT_INTERVAL)
            result = predict_from_events(kb, ms, window_size=_PREDICT_INTERVAL)

            # 3. Cache prediction for /api/predict/live
            with _pred_lock:
                _last_pred.update(result)

            if result["activity"] is None:
                continue

            # 4. Increment the correct time bucket on the session row
            activity = result["activity"]
            with get_session() as db:
                rec = db.get(RecordingSession, session_id)
                if rec is not None and rec.ending_at is None:
                    if activity == "coding":
                        rec.coding_time = (
                            rec.coding_time or 0.0
                        ) + _PREDICT_INTERVAL / 60
                    elif activity == "writing":
                        rec.writing_time = (
                            rec.writing_time or 0.0
                        ) + _PREDICT_INTERVAL / 60
                    elif activity == "gaming":
                        rec.gaming_time = (
                            rec.gaming_time or 0.0
                        ) + _PREDICT_INTERVAL / 60

        except Exception as exc:
            print(f"[predict_loop] {exc}")


# Start background thread once when the blueprint is loaded
_bg_thread = threading.Thread(target=_run_prediction_loop, daemon=True)
_bg_thread.start()


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
# Live prediction  — served from cache written by background prediction loop
# ---------------------------------------------------------------------------
@dashboard.get("/api/predict/live")
def api_predict_live():
    """
    Returns the latest ML prediction for the active session.

    Response shape:
        {
            "activity":      "coding" | "writing" | "gaming" | null,
            "confidence":    float | null,
            "probabilities": { "coding": float, "writing": float, "gaming": float }
        }
    """
    with _pred_lock:
        return jsonify(dict(_last_pred))


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
