"""
agent/ui/tray.py — system tray icon for the capture agent (Windows).

State machine
─────────────
  IDLE      grey circle  menu: [👤 user (click→change)] [Activité ▶] [───] [▶ Démarrer] [───] [🌐 Dashboard] [Quitter]
  RECORDING red  circle  menu: [👤 user (disabled)]     [🔴 activity] [───] [⏹ Arrêter]  [───] [🌐 Dashboard] [Quitter]
"""

import signal
import threading
import webbrowser

import pystray
from PIL import Image, ImageDraw

from .. import client
from app.services import RegisterService
from .home import ask_profile

# ── Constants ─────────────────────────────────────────────────────────────────
ACTIVITIES = ("coding", "writing", "gaming")
DASHBOARD_URL = "http://127.0.0.1:5000"
SENTINEL_URL = "http://127.0.0.1:5000/sentinel"
ICON_SIZE = 64
COLOR_IDLE = "#6e7681"  # github grey
COLOR_REC = "#f85149"  # github red
COLOR_SENTINEL = "#bc8cff"  # purple (sentinel mode)
COLOR_SERVER = "#3fb950"  # github green  (server OK dot)


# ── Icon helpers ──────────────────────────────────────────────────────────────


def _make_image(
    recording: bool, server_ok: bool = True, sentinel: bool = False
) -> Image.Image:
    """64×64 RGBA: filled circle + tiny status dot in the corner."""
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Main circle
    if sentinel:
        fill = COLOR_SENTINEL
    elif recording:
        fill = COLOR_REC
    else:
        fill = COLOR_IDLE
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
    def __init__(self, exit_hook=None) -> None:
        """
        exit_hook : callable appelé juste avant os._exit (ex: flask_proc.terminate).
        """
        self._exit_hook = exit_hook
        self._user = "anonymous"
        self._activity = ACTIVITIES[0]
        self._labelled = True
        self._mode = "base"  # "base" | "sentinel"
        self._recording = False
        self._server_ok = False

        self._service: RegisterService | None = None

        self._icon: pystray.Icon | None = None

    # ── Menu ──────────────────────────────────────────────────────────────────

    def _make_menu(self) -> pystray.Menu:
        if self._mode == "sentinel":
            server_label = (
                "✅  Serveur OK" if self._server_ok else "❌  Serveur inaccessible"
            )
            return pystray.Menu(
                pystray.MenuItem("🟣  Mode Sentinel", self._ask_user),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(server_label, None, enabled=False),
                pystray.MenuItem("🌐  Ouvrir l'interface web", self._open_dashboard),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quitter", self._quit),
            )

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

        if self._labelled:
            activity_item = pystray.MenuItem(
                "Activité",
                pystray.Menu(
                    *[
                        pystray.MenuItem(
                            a,
                            self._activity_setter(a),
                            checked=lambda item, a=a: self._activity == a,
                            radio=True,
                        )
                        for a in ACTIVITIES
                    ]
                ),
            )
        else:
            activity_item = pystray.MenuItem(
                "Activité : Auto (ML)", None, enabled=False
            )

        server_label = (
            "✅  Serveur OK" if self._server_ok else "❌  Serveur inaccessible"
        )

        return pystray.Menu(
            pystray.MenuItem(f"👤  {self._user}", self._ask_user),
            activity_item,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("▶  Démarrer", self._on_start),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(server_label, None, enabled=False),
            pystray.MenuItem("🌐  Ouvrir le dashboard", self._open_dashboard),
            pystray.MenuItem("Quitter", self._quit),
        )

    def _refresh(self) -> None:
        """Rebuild icon image + menu in place (thread-safe via pystray)."""
        if self._icon:
            self._icon.icon = _make_image(
                self._recording,
                self._server_ok,
                sentinel=self._mode == "sentinel",
            )
            self._icon.menu = self._make_menu()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _activity_setter(self, activity: str):
        """Return a pystray action callback that sets the activity."""

        def _set(icon, item):
            self._activity = activity
            self._refresh()

        return _set

    def _ask_user(self, icon, item) -> None:
        """Open the home window to change mode / user / activity / labelling."""

        def _dialog() -> None:
            result = ask_profile(
                initial_user=self._user,
                initial_activity=self._activity,
                initial_labelled=self._labelled,
                initial_mode=self._mode,
            )
            if result:
                self._mode = result["mode"]
                self._user = result["user"] or "anonymous"
                self._labelled = result["labelled"]
                self._activity = result["activity"] or ACTIVITIES[0]
                self._refresh()

        threading.Thread(target=_dialog, daemon=True).start()

    def _on_start(self, icon, item) -> None:
        """Menu → Démarrer."""
        if self._recording:
            return

        _activity = self._activity if self._labelled else "coding"
        self._service = RegisterService(username=self._user, activity_label=_activity)
        self._service.start()
        self._recording = True
        self._refresh()

    def _do_stop(self) -> None:
        """Core stop logic — called from menu or quit."""
        if not self._recording:
            return
        self._recording = False
        if self._service:
            self._service.stop()
            self._service = None
        self._refresh()

    def _on_stop(self, icon, item) -> None:
        """Menu → Arrêter (runs stop in a thread to keep the UI responsive)."""
        threading.Thread(target=self._do_stop, daemon=True).start()

    def _open_dashboard(self, icon, item) -> None:
        url = SENTINEL_URL if self._mode == "sentinel" else DASHBOARD_URL
        webbrowser.open(url)

    def _notify(self, title: str, message: str) -> None:
        if self._icon:
            try:
                self._icon.notify(message, title)  # pystray: message first, then title
            except Exception:
                pass

    def _quit(self, icon, item) -> None:
        self._do_stop()
        if self._exit_hook:
            self._exit_hook()
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
        # ── Fenêtre de login au démarrage ─────────────────────────────────
        result = ask_profile(
            initial_user=self._user,
            initial_activity=self._activity,
            initial_labelled=self._labelled,
            initial_mode=self._mode,
        )
        if result is None:
            return  # utilisateur a annulé → on ne démarre pas
        self._mode = result["mode"]
        self._user = result["user"] or "anonymous"
        self._labelled = result["labelled"]
        self._activity = result["activity"] or ACTIVITIES[0]

        # ── Tray ──────────────────────────────────────────────────────────
        self._server_ok = client.check_server()

        self._icon = pystray.Icon(
            name="KeySentinel",
            icon=_make_image(
                recording=False,
                server_ok=self._server_ok,
                sentinel=self._mode == "sentinel",
            ),
            title="KeySentinel",
            menu=self._make_menu(),
        )

        threading.Thread(target=self._poll_server, daemon=True).start()

        # Ctrl+C dans le terminal est ignoré — utiliser le menu tray pour quitter.
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        self._icon.run()  # blocks the main thread (required by pystray on Windows)
