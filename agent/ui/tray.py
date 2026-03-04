"""
agent/ui/tray.py — system tray icon for the capture agent (Windows).

State machine
─────────────
  IDLE      grey circle  menu: [👤 user (click→change)] [Activité ▶] [───] [▶ Démarrer] [───] [🌐 Dashboard] [Quitter]
  RECORDING red  circle  menu: [👤 user (disabled)]     [🔴 activity] [───] [⏹ Arrêter]  [───] [🌐 Dashboard] [Quitter]
"""

import threading
import webbrowser
import tkinter as tk
from tkinter import simpledialog

import pystray
from PIL import Image, ImageDraw

from .. import buffer, client, listeners, session

# ── Constants ─────────────────────────────────────────────────────────────────
ACTIVITIES = ("coding", "writing", "gaming")
DASHBOARD_URL = "http://127.0.0.1:5000"
ICON_SIZE = 64
COLOR_IDLE = "#6e7681"  # github grey
COLOR_REC = "#f85149"  # github red
COLOR_SERVER = "#3fb950"  # github green  (server OK dot)


# ── Icon helpers ──────────────────────────────────────────────────────────────


def _make_image(recording: bool, server_ok: bool = True) -> Image.Image:
    """64×64 RGBA: filled circle + tiny status dot in the corner."""
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Main circle
    fill = COLOR_REC if recording else COLOR_IDLE
    draw.ellipse([4, 4, ICON_SIZE - 4, ICON_SIZE - 4], fill=fill)

    # Small server-status dot (bottom-right)
    dot_color = COLOR_SERVER if server_ok else "#f85149"
    r = 9
    draw.ellipse(
        [ICON_SIZE - r * 2 - 2, ICON_SIZE - r * 2 - 2, ICON_SIZE - 2, ICON_SIZE - 2],
        fill=dot_color,
    )
    return img


# ── TrayApp ───────────────────────────────────────────────────────────────────


class TrayApp:
    def __init__(self) -> None:
        self._user = "anonymous"
        self._activity = ACTIVITIES[0]
        self._recording = False
        self._server_ok = False

        self._stop_event: threading.Event | None = None
        self._mouse_l = None
        self._kb_l = None

        self._icon: pystray.Icon | None = None

    # ── Menu ──────────────────────────────────────────────────────────────────

    def _make_menu(self) -> pystray.Menu:
        if self._recording:
            return pystray.Menu(
                pystray.MenuItem(f"👤  {self._user}", None, enabled=False),
                pystray.MenuItem(f"🔴  {self._activity}", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("⏹  Arrêter", self._on_stop),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("🌐  Ouvrir le dashboard", self._open_dashboard),
                pystray.MenuItem("Quitter", self._quit),
            )

        activity_submenu = pystray.Menu(
            *[
                pystray.MenuItem(
                    a,
                    self._activity_setter(a),
                    checked=lambda item, a=a: self._activity == a,
                    radio=True,
                )
                for a in ACTIVITIES
            ]
        )

        server_label = (
            "✅  Serveur OK" if self._server_ok else "❌  Serveur inaccessible"
        )

        return pystray.Menu(
            pystray.MenuItem(f"👤  {self._user}", self._ask_user),
            pystray.MenuItem("Activité", activity_submenu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("▶  Démarrer", self._on_start, enabled=self._server_ok),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(server_label, None, enabled=False),
            pystray.MenuItem("🌐  Ouvrir le dashboard", self._open_dashboard),
            pystray.MenuItem("Quitter", self._quit),
        )

    def _refresh(self) -> None:
        """Rebuild icon image + menu in place (thread-safe via pystray)."""
        if self._icon:
            self._icon.icon = _make_image(self._recording, self._server_ok)
            self._icon.menu = self._make_menu()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _activity_setter(self, activity: str):
        """Return a pystray action callback that sets the activity."""

        def _set(icon, item):
            self._activity = activity
            self._refresh()

        return _set

    def _ask_user(self, icon, item) -> None:
        """Open a minimal tkinter dialog to change the username."""

        def _dialog() -> None:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            name = simpledialog.askstring(
                "KeySentinel — Utilisateur",
                "Nom d'utilisateur :",
                initialvalue=self._user,
                parent=root,
            )
            root.destroy()
            if name and name.strip():
                self._user = name.strip()
                self._refresh()

        threading.Thread(target=_dialog, daemon=True).start()

    def _on_start(self, icon, item) -> None:
        """Menu → Démarrer."""
        if self._recording:
            return
        if not client.check_server():
            self._server_ok = False
            self._notify("Serveur inaccessible", "Lance run_server.py d'abord.")
            self._refresh()
            return

        self._recording = True
        self._stop_event = threading.Event()
        self._refresh()

        # Open session
        session.start(self._user, self._activity, client.post)

        # Flush thread
        threading.Thread(
            target=buffer.flush_loop,
            args=(session.get_id, client.post, self._stop_event),
            daemon=True,
        ).start()

        # Listeners
        self._mouse_l = listeners.make_mouse_listener(buffer.push, self._do_stop)
        self._kb_l = listeners.make_keyboard_listener(
            buffer.push, self._do_stop, self._stop_event
        )
        self._mouse_l.start()
        self._kb_l.start()

    def _do_stop(self) -> None:
        """Core stop logic — called from END key, menu, or quit."""
        if not self._recording:
            return
        if self._stop_event and self._stop_event.is_set():
            return
        if self._stop_event:
            self._stop_event.set()

        # Stop listeners cleanly
        if self._mouse_l:
            self._mouse_l.stop()
        if self._kb_l:
            self._kb_l.stop()

        session.stop(
            post_fn=client.post,
            flush_fn=lambda: buffer.flush(session.get_id(), client.post),
        )
        self._recording = False
        self._refresh()

    def _on_stop(self, icon, item) -> None:
        """Menu → Arrêter (runs stop in a thread to keep the UI responsive)."""
        threading.Thread(target=self._do_stop, daemon=True).start()

    def _open_dashboard(self, icon, item) -> None:
        webbrowser.open(DASHBOARD_URL)

    def _notify(self, title: str, message: str) -> None:
        if self._icon:
            try:
                self._icon.notify(message, title)  # pystray: message first, then title
            except Exception:
                pass

    def _quit(self, icon, item) -> None:
        self._do_stop()
        icon.stop()

    # ── Server polling ────────────────────────────────────────────────────────

    def _poll_server(self) -> None:
        """Background thread: check server reachability every 5 s."""
        import time

        while self._icon is None:
            time.sleep(0.1)
        while True:
            ok = client.check_server()
            if ok != self._server_ok:
                self._server_ok = ok
                self._refresh()
            time.sleep(5)

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._server_ok = client.check_server()

        self._icon = pystray.Icon(
            name="KeySentinel",
            icon=_make_image(recording=False, server_ok=self._server_ok),
            title="KeySentinel",
            menu=self._make_menu(),
        )

        threading.Thread(target=self._poll_server, daemon=True).start()
        self._icon.run()  # blocks the main thread (required by pystray on Windows)
