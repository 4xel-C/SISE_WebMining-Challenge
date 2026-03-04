"""
Sentinel routes — GET only, consumed by frontend/sentinel.html.

Reads directly from keysentinel.db (SQLite) via SQLAlchemy ORM.

Endpoints
---------
GET /api/sentinel/users                     — liste tous les utilisateurs
GET /api/sentinel/sessions?user_id=         — sessions d'un utilisateur (ou toutes)
GET /api/sentinel/session/<id>/stats        — métriques agrégées d'une session
"""

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from app.models.schema import (
    KeyboardEvent,
    MouseEvent,
    RecordingSession,
    User,
    get_session,
)

sentinel_bp = Blueprint("sentinel", __name__)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@sentinel_bp.get("/api/sentinel/users")
def sentinel_users():
    """
    Returns all users with basic info.

    Response shape:
        [
            {
                "id":               int,
                "name":             str,
                "is_on_line":       bool,
                "on_going_activity": str | null,
                "session_count":    int
            },
            ...
        ]
    """
    try:
        with get_session() as db:
            users = db.query(User).order_by(User.name).all()
            result = []
            for u in users:
                session_count = (
                    db.query(func.count(RecordingSession.id))
                    .filter(RecordingSession.user_id == u.id)
                    .scalar()
                    or 0
                )
                result.append(
                    {
                        "id": u.id,
                        "name": u.name,
                        "is_on_line": bool(u.is_on_line),
                        "on_going_activity": (
                            u.on_going_activity.value if u.on_going_activity else None
                        ),
                        "session_count": session_count,
                    }
                )
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@sentinel_bp.get("/api/sentinel/sessions")
def sentinel_sessions():
    """
    Returns sessions, optionally filtered by user_id.

    Query param: user_id (optional int)

    Response shape:
        [
            {
                "id":              int,
                "uuid":            str,
                "user_id":         int | null,
                "activity":        str | null,
                "started_at":      float,
                "ending_at":       float | null,
                "duration_s":      float | null,
                "coding_time":     float,
                "writing_time":    float,
                "gaming_time":     float,
                "keyboard_events": int,
                "mouse_events":    int
            },
            ...
        ]
    """
    user_id = request.args.get("user_id", type=int)
    try:
        with get_session() as db:
            q = db.query(RecordingSession)
            if user_id is not None:
                q = q.filter(RecordingSession.user_id == user_id)
            sessions = q.order_by(RecordingSession.started_at.desc()).all()

            result = []
            for s in sessions:
                kb_count = (
                    db.query(func.count(KeyboardEvent.id))
                    .filter(KeyboardEvent.recording_session_id == s.id)
                    .scalar()
                    or 0
                )
                mouse_count = (
                    db.query(func.count(MouseEvent.id))
                    .filter(MouseEvent.recording_session_id == s.id)
                    .scalar()
                    or 0
                )
                activity_label = s.activity.label.value if s.activity else None
                duration = (
                    s.ending_at - s.started_at if s.ending_at and s.started_at else None
                )
                result.append(
                    {
                        "id": s.id,
                        "uuid": s.uuid,
                        "user_id": s.user_id,
                        "activity": activity_label,
                        "started_at": s.started_at,
                        "ending_at": s.ending_at,
                        "duration_s": duration,
                        "coding_time": s.coding_time,
                        "writing_time": s.writing_time,
                        "gaming_time": s.gaming_time,
                        "keyboard_events": kb_count,
                        "mouse_events": mouse_count,
                    }
                )
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Session detail / stats
# ---------------------------------------------------------------------------


@sentinel_bp.get("/api/sentinel/session/<int:session_id>/stats")
def sentinel_session_stats(session_id: int):
    """
    Aggregated metrics for one session.

    Response shape:
        {
            "id":                    int,
            "uuid":                  str,
            "duration_s":            float | null,
            "coding_time":           float,
            "writing_time":          float,
            "gaming_time":           float,
            "keyboard_events":       int,
            "mouse_events":          int,
            "avg_dwell_ms":          float | null,
            "avg_flight_ms":         float | null,
            "click_count":           int,
            "avg_mouse_speed_px_s":  float | null
        }
    """
    try:
        with get_session() as db:
            s = db.get(RecordingSession, session_id)
            if s is None:
                return jsonify({"error": "session not found"}), 404

            kb_count = (
                db.query(func.count(KeyboardEvent.id))
                .filter(KeyboardEvent.recording_session_id == session_id)
                .scalar()
                or 0
            )
            mouse_count = (
                db.query(func.count(MouseEvent.id))
                .filter(MouseEvent.recording_session_id == session_id)
                .scalar()
                or 0
            )
            avg_dwell = (
                db.query(func.avg(KeyboardEvent.dwell))
                .filter(
                    KeyboardEvent.recording_session_id == session_id,
                    KeyboardEvent.dwell.isnot(None),
                )
                .scalar()
            )
            avg_flight = (
                db.query(func.avg(KeyboardEvent.flight_time))
                .filter(
                    KeyboardEvent.recording_session_id == session_id,
                    KeyboardEvent.flight_time.isnot(None),
                )
                .scalar()
            )
            click_count = (
                db.query(func.count(MouseEvent.id))
                .filter(
                    MouseEvent.recording_session_id == session_id,
                    MouseEvent.event_type == "click",
                )
                .scalar()
                or 0
            )
            avg_speed = (
                db.query(func.avg(MouseEvent.speed))
                .filter(
                    MouseEvent.recording_session_id == session_id,
                    MouseEvent.event_type == "move",
                    MouseEvent.speed.isnot(None),
                )
                .scalar()
            )

            duration = (
                s.ending_at - s.started_at if s.ending_at and s.started_at else None
            )

            # Build the response dict *inside* the session context to avoid
            # "Instance is not bound to a Session" lazy-load errors after close.
            payload = {
                "id": s.id,
                "uuid": s.uuid,
                "duration_s": duration,
                "coding_time": s.coding_time,
                "writing_time": s.writing_time,
                "gaming_time": s.gaming_time,
                "keyboard_events": kb_count,
                "mouse_events": mouse_count,
                "avg_dwell_ms": round(avg_dwell * 1000, 2) if avg_dwell else None,
                "avg_flight_ms": round(avg_flight * 1000, 2) if avg_flight else None,
                "click_count": click_count,
                "avg_mouse_speed_px_s": round(avg_speed, 1) if avg_speed else None,
            }

        return jsonify(payload)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
