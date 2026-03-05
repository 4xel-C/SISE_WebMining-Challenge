"""
run.py — point d'entrée unique KeySentinel.

Lance Flask dans un subprocess, puis démarre le tray sur le thread principal.
À la fermeture du tray, le subprocess Flask est arrêté proprement.

Usage:
    uv run run.py
"""

import subprocess
import sys
import threading
import time

import requests

from app.models.schema import _DB_URL

FLASK_URL = "http://127.0.0.1:5000/api/status"
BOOT_TIMEOUT = 15  # secondes max pour attendre Flask


def _wait_for_flask(timeout: float) -> bool:
    """Retourne True dès que Flask répond, False si timeout dépassé."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(FLASK_URL, timeout=1).raise_for_status()
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main() -> None:
    # ── 1) Lancer Flask en subprocess ────────────────────────────────────────
    flask_proc = subprocess.Popen(
        [sys.executable, "scripts/server.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print("[run] Démarrage de Flask…", flush=True)
    if not _wait_for_flask(BOOT_TIMEOUT):
        print(
            "[run] ERREUR : Flask n'a pas démarré dans le délai imparti.",
            file=sys.stderr,
        )
        flask_proc.terminate()
        sys.exit(1)

    print("[run] Flask prêt ✓", flush=True)

    # ── 2) Tray sur le thread principal (obligatoire sur Windows) ────────────
    from agent.ui.tray import TrayApp

    original_quit = TrayApp._quit

    def _quit_with_cleanup(self, icon, item) -> None:
        """Arrêter Flask après la fermeture du tray."""
        original_quit(self, icon, item)  # appelle déjà exit_hook

    TrayApp._quit = _quit_with_cleanup

    try:
        TrayApp(exit_hook=flask_proc.terminate).run()
    finally:
        if flask_proc.poll() is None:
            flask_proc.terminate()
        flask_proc.wait()


if __name__ == "__main__":
    main()
