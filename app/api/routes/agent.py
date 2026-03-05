"""
Agent routes — POST only, called exclusively by run_capture.py (local CLI agent).

CES ROUTES NE SONT PAS EXPOSÉES AU NAVIGATEUR.
Elles servent à l'agent pynput pour pousser les événements et contrôler les
sessions.  Le frontend ne fait que lire (GET /api/…).

Endpoints
---------
POST /api/session/start   — ouvre une nouvelle session
POST /api/ingest          — reçoit un batch d'événements depuis l'agent
POST /api/session/stop    — ferme la session, extrait les features, re-entraîne
"""

from flask import Blueprint, jsonify, request

import app.api.store as store

agent = Blueprint("agent", __name__)


# ---------------------------------------------------------------------------
# Start session
# ---------------------------------------------------------------------------
@agent.post("/api/session/start")
def api_session_start():
    """
    Opens a new recording session.

    Request body:
        {
            "user":     str,   e.g. "alice"
            "activity": str    "coding" | "writing" | "gaming"
        }

    Response shape:
        {
            "ok":         bool,
            "session_id": int
        }
    """
    body = request.get_json(silent=True) or {}
    user = body.get("user", "anonymous")
    activity = body.get("activity") or None

    if activity is not None and activity not in ("coding", "writing", "gaming"):
        return jsonify({"ok": False, "error": f"unknown activity '{activity}'"}), 400

    session_id = store.session_start(user=user, activity=activity)
    return jsonify({"ok": True, "session_id": session_id})


# ---------------------------------------------------------------------------
# Ingest events
# ---------------------------------------------------------------------------
@agent.post("/api/ingest")
def api_ingest():
    """
    Receives a batch of mouse/keyboard events from the running pynput agent.
    Called roughly every 200 ms with whatever has accumulated since the last flush.

    Request body:
        {
            "session_id": int,
            "events": [
                {
                    "type":      "mouse" | "keyboard",
                    "ts":        float,          # epoch seconds
                    "data":      { ... }         # event-specific payload
                },
                ...
            ]
        }

    Response shape:
        {
            "ok":           bool,
            "inserted":     int
        }
    """
    body = request.get_json(silent=True) or {}
    events = body.get("events", [])

    inserted = store.ingest(events)
    return jsonify({"ok": True, "inserted": inserted})


# ---------------------------------------------------------------------------
# Stop session
# ---------------------------------------------------------------------------
@agent.post("/api/session/stop")
def api_session_stop():
    """
    Stops the current session, extracts sliding-window features, re-trains
    the RandomForest.  Called by run_capture.py on End key / Ctrl+C.

    Request body (optional):
        {
            "session_id": int
        }

    Response shape:
        {
            "ok":             bool,
            "event_count":    int,
            "model_trained":  bool
        }
    """
    result = store.session_stop()
    return jsonify(
        {"ok": True, "event_count": result["event_count"], "model_trained": False}
    )
