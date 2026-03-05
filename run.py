"""
run.py — point d'entrée unique KeySentinel.

Lance Flask dans un subprocess, puis démarre le tray sur le thread principal.
À la fermeture du tray, le subprocess Flask est arrêté proprement.

Usage:
    uv run run.py
"""

import os
import subprocess
import sys
import time
import threading

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


def _server_cmd() -> list[str]:
    """Returns the command to start the Flask server.
    When bundled with PyInstaller, uses the sibling server.exe.
    """
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
        return [os.path.join(base_dir, "server.exe")]
    return [sys.executable, "scripts/server.py"]


def main() -> None:
    # ── 1) Lancer Flask en subprocess ────────────────────────────────────────
    flask_proc = subprocess.Popen(
        _server_cmd(),
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
