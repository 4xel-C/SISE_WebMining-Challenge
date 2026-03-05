"""
agent/cli.py — entry point: prompts the user, wires all components together.

Single responsibility: orchestration only.
  - prompt for user / activity
  - start RegisterService (direct DB write, no Flask required)
  - wait for END key or Ctrl+C
  - stop service
"""

import threading
import time

from pynput import keyboard as kb

from app.services import RegisterService

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
    # 1) Prompts
    user, activity = _prompt_session()

    # 2) Créer le service
    service = RegisterService(username=user, activity_label=activity)

    print(f"\n[agent] user={user}  activity={activity}")

    # 3) Compte à rebours
    for i in (3, 2, 1):
        print(f"  Démarrage dans {i}…")
        time.sleep(1)
    print("[agent] Enregistrement en cours — appuie sur END pour arrêter.\n")

    # 4) Signal d'arrêt
    stop_event = threading.Event()

    def on_press(key):
        if key == kb.Key.end:
            stop_event.set()
            return False  # arrête ce listener

    stop_listener = kb.Listener(on_press=on_press)

    # 5) Démarrer service + listener de stop
    service.start()
    stop_listener.start()

    # 6) Attendre le signal d'arrêt
    try:
        stop_event.wait()
    except KeyboardInterrupt:
        pass

    # 7) Arrêter proprement
    stop_listener.stop()
    service.stop()
    print("[agent] Session terminée.")
