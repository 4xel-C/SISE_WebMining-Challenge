"""
run_capture.py — agent local de capture.

Usage:
    uv run run_capture.py

Flux:
    1) Demande : nom d'utilisateur + activité (coding / writing / gaming)
    2) POST /api/session/start  → reçoit session_id
    3) Lance les listeners pynput (souris + clavier)
    4) Thread de flush : POST /api/ingest  toutes les 200 ms
    5) Touche END (ou Ctrl+C) → POST /api/session/stop → quitte
"""

import sys
import threading
import time
from collections import deque

import requests
from pynput import keyboard, mouse

API_BASE = "http://127.0.0.1:5000"
FLUSH_INTERVAL = 0.2  # secondes

# ── État global ───────────────────────────────────────────────────────────────
_event_buf: deque = deque()
_buf_lock = threading.Lock()
_session_id: int | None = None
_stopping = threading.Event()


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ts() -> float:
    return time.time()


def _post(path: str, payload: dict) -> dict | None:
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, timeout=3)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[capture] POST {path} échoué : {e}", file=sys.stderr)
        return None


# ── Callbacks souris ──────────────────────────────────────────────────────────
def on_mouse_move(x: float, y: float):
    with _buf_lock:
        _event_buf.append(
            {
                "type": "mouse",
                "ts": _ts(),
                "data": {"event_type": "move", "x": x, "y": y},
            }
        )


def on_mouse_click(x: float, y: float, button, pressed: bool):
    with _buf_lock:
        _event_buf.append(
            {
                "type": "mouse",
                "ts": _ts(),
                "data": {
                    "event_type": "click",
                    "x": x,
                    "y": y,
                    "button": str(button),
                    "pressed": pressed,
                },
            }
        )


def on_mouse_scroll(x: float, y: float, dx: float, dy: float):
    with _buf_lock:
        _event_buf.append(
            {
                "type": "mouse",
                "ts": _ts(),
                "data": {"event_type": "scroll", "x": x, "y": y, "dx": dx, "dy": dy},
            }
        )


# ── Callbacks clavier ─────────────────────────────────────────────────────────
def _key_str(key) -> str:
    if hasattr(key, "char") and key.char:
        return key.char
    return str(key)


def on_key_press(key):
    if _stopping.is_set():
        return
    if key == keyboard.Key.end:
        threading.Thread(target=stop, daemon=True).start()
        return
    with _buf_lock:
        _event_buf.append(
            {
                "type": "keyboard",
                "ts": _ts(),
                "data": {"event_type": "press", "key": _key_str(key)},
            }
        )


def on_key_release(key):
    if _stopping.is_set():
        return
    with _buf_lock:
        _event_buf.append(
            {
                "type": "keyboard",
                "ts": _ts(),
                "data": {"event_type": "release", "key": _key_str(key)},
            }
        )


# ── Thread de flush ───────────────────────────────────────────────────────────
def flush_loop():
    while not _stopping.is_set():
        time.sleep(FLUSH_INTERVAL)
        _flush()


def _flush():
    if not _event_buf:
        return
    with _buf_lock:
        batch = list(_event_buf)
        _event_buf.clear()
    _post("/api/ingest", {"session_id": _session_id, "events": batch})


# ── Arrêt ─────────────────────────────────────────────────────────────────────
def stop():
    if _stopping.is_set():
        return
    _stopping.set()
    print("\n[capture] Arrêt en cours…")
    _flush()  # vide le buffer restant
    resp = _post("/api/session/stop", {"session_id": _session_id})
    if resp:
        print(
            f"[capture] Session terminée."
            f"  Événements : {resp.get('event_count', '?')}"
            f"  Modèle entraîné : {resp.get('model_trained', '?')}"
        )
    # libère le main thread
    sys.exit(0)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global _session_id

    # 1) Vérifie que le serveur tourne
    try:
        requests.get(f"{API_BASE}/api/status", timeout=3).raise_for_status()
    except Exception:
        print("[capture] ERREUR : serveur Flask inaccessible sur http://127.0.0.1:5000")
        print("          Lance-le d'abord :  uv run run_server.py")
        sys.exit(1)

    # 2) Prompts
    user = input("Utilisateur : ").strip() or "anonymous"
    print("Activité :")
    print("  [1] coding")
    print("  [2] writing")
    print("  [3] gaming")
    choice = input("Choix (1/2/3) : ").strip().lower()
    activity = {"1": "coding", "2": "writing", "3": "gaming"}.get(choice) or (
        choice if choice in ("coding", "writing", "gaming") else "coding"
    )

    # 3) Ouvre la session
    resp = _post("/api/session/start", {"user": user, "activity": activity})
    _session_id = (resp or {}).get("session_id")
    print(f"\n[capture] user={user}  activity={activity}  session_id={_session_id}")

    # 4) Compte à rebours
    for i in (3, 2, 1):
        print(f"  Démarrage dans {i}…")
        time.sleep(1)
    print("[capture] Enregistrement en cours — appuie sur END pour arrêter.\n")

    # 5) Thread de flush
    threading.Thread(target=flush_loop, daemon=True).start()

    # 6) Listeners
    mouse_listener = mouse.Listener(
        on_move=on_mouse_move, on_click=on_mouse_click, on_scroll=on_mouse_scroll
    )
    kb_listener = keyboard.Listener(on_press=on_key_press, on_release=on_key_release)

    mouse_listener.start()
    kb_listener.start()

    try:
        while not _stopping.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        stop()


if __name__ == "__main__":
    main()
