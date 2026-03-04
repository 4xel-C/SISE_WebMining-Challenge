"""
agent/cli.py — entry point: prompts the user, wires all components together.

Single responsibility: orchestration only.
  - prompt for user / activity
  - start session
  - start buffer flush thread
  - start listeners
  - wait for stop signal
"""

import sys
import threading
import time

from . import buffer, client, listeners, session

ACTIVITIES = ("coding", "writing", "gaming")


# ── Prompts ───────────────────────────────────────────────────────────────────


def _prompt_session() -> tuple[str, str]:
    user = input("Utilisateur : ").strip() or "anonymous"
    print("Activité :")
    for i, a in enumerate(ACTIVITIES, 1):
        print(f"  [{i}] {a}")
    choice = input("Choix (1/2/3) : ").strip().lower()
    activity = {str(i): a for i, a in enumerate(ACTIVITIES, 1)}.get(choice) or (
        choice if choice in ACTIVITIES else ACTIVITIES[0]
    )
    return user, activity


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    # 1) Vérifier que le serveur tourne
    if not client.check_server():
        print("[agent] ERREUR : serveur Flask inaccessible sur http://127.0.0.1:5000")
        print("        Lance-le d'abord :  uv run run_server.py")
        sys.exit(1)

    # 2) Prompts
    user, activity = _prompt_session()

    # 3) Ouvrir la session
    sid = session.start(user, activity, client.post)
    print(f"\n[agent] user={user}  activity={activity}  session_id={sid}")

    # 4) Compte à rebours
    for i in (3, 2, 1):
        print(f"  Démarrage dans {i}…")
        time.sleep(1)
    print("[agent] Enregistrement en cours — appuie sur END pour arrêter.\n")

    # 5) Signal d'arrêt + callback stop (one-shot)
    stop_event = threading.Event()

    def stop() -> None:
        if stop_event.is_set():
            return
        stop_event.set()
        session.stop(
            post_fn=client.post,
            flush_fn=lambda: buffer.flush(session.get_id(), client.post),
        )
        sys.exit(0)

    # 6) Thread de flush
    threading.Thread(
        target=buffer.flush_loop,
        args=(session.get_id, client.post, stop_event),
        daemon=True,
    ).start()

    # 7) Listeners
    mouse_l = listeners.make_mouse_listener(buffer.push, stop)
    kb_l = listeners.make_keyboard_listener(buffer.push, stop, stop_event)
    mouse_l.start()
    kb_l.start()

    # 8) Boucle principale
    try:
        while not stop_event.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        stop()
