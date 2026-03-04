"""
agent/session.py — session lifecycle (start / stop).

Single responsibility: own the session_id state and talk to the API
to open / close a session.
"""

from typing import Callable

_session_id: int | None = None


def get_id() -> int | None:
    return _session_id


def start(user: str, activity: str | None, post_fn: Callable) -> int | None:
    """Open a new session on the server; store and return the session_id.

    activity=None  →  mode ML-only, le serveur recevra activity=null et
                       le modèle annotera les événements en différé.
    """
    global _session_id
    resp = post_fn("/api/session/start", {"user": user, "activity": activity})
    _session_id = (resp or {}).get("session_id")
    return _session_id


def stop(post_fn: Callable, flush_fn: Callable) -> None:
    """Flush remaining events, then close the session on the server."""
    flush_fn()
    resp = post_fn("/api/session/stop", {"session_id": _session_id})
    if resp:
        print(
            f"\n[agent] Session terminée."
            f"  Événements : {resp.get('event_count', '?')}"
            f"  Modèle entraîné : {resp.get('model_trained', '?')}"
        )
