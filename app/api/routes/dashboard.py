"""
Dashboard routes — GET only, consumed by frontend/index.html (visualisation).

CES ROUTES SONT EN LECTURE SEULE.
L'écriture (ingest, start/stop session) est dans agent.py, appelée uniquement
par l'agent Python local (run_capture.py), jamais par le navigateur.
"""

from flask import Blueprint, jsonify, request

import app.api.store as store

dashboard = Blueprint("dashboard", __name__)


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
    return jsonify(store.get_status())


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
    return jsonify(store.get_live_features())


# ---------------------------------------------------------------------------
# Live prediction
# ---------------------------------------------------------------------------
@dashboard.get("/api/predict/live")
def api_predict_live():
    """
    Runs the trained model on the last feature window.

    Response shape:
        {
            "activity":      "coding" | "writing" | "gaming",
            "confidence":    float,          # 0–1, max class prob
            "probabilities": {
                "coding":  float,
                "writing": float,
                "gaming":  float
            }
        }
    """
    return jsonify(store.get_live_prediction())


# ---------------------------------------------------------------------------
# Recent raw events  (for live feed display)
# ---------------------------------------------------------------------------
@dashboard.get("/api/events/recent")
def api_events_recent():
    """
    Returns the N most recent raw input events.

    Query param: n (default 20)

    Response shape:
        [
            {
                "time":       "HH:MM:SS",
                "device":     "keyboard" | "mouse",
                "event_type": "press" | "release" | "move" | "click" | "scroll",
                "detail":     str          # key name, coords, button…
            },
            …
        ]
    """
    n = request.args.get("n", 20, type=int)
    since = request.args.get("since", 0.0, type=float)
    return jsonify(store.get_recent_events(n, since))


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
