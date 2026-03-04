"""Service d'enregistrement des événements clavier/souris en base de données."""

import queue
import threading
import time
import uuid

from app.collector.keyboard_listener import KeyboardListener
from app.collector.mouse_listener import MouseListener
from app.models.schema import (
    Activity,
    KeyboardEvent,
    MouseEvent,
    User,
    create_tables,
    get_session,
)


class RegisterService:
    """
    Enregistre les événements clavier et souris en base de données.

    Usage:
        service = RegisterService(username="axel", activity_label="gaming")
        service.start()
        time.sleep(30)
        service.stop()
    """

    def __init__(
        self,
        username: str,
        activity_label: str,
        db_url: str = "sqlite:///keysentinel.db",
        session_id: str | None = None,
    ):
        self.username = username
        self.activity_label = activity_label
        self.db_url = db_url
        self.session_id = session_id or str(uuid.uuid4())

        self._event_queue: queue.Queue = queue.Queue()
        self._keyboard = KeyboardListener(self._event_queue)
        self._mouse = MouseListener(self._event_queue)
        self._running = False
        self._flush_thread: threading.Thread | None = None

        # IDs résolus au démarrage
        self._user_id: int | None = None
        self._activity_id: int | None = None

    def _resolve_user_and_activity(self):
        """Crée ou récupère l'utilisateur et le label d'activité en base."""
        with get_session(self.db_url) as session:
            user = session.query(User).filter_by(name=self.username).first()
            if user is None:
                user = User(name=self.username)
                session.add(user)
                session.flush()
            self._user_id = user.id

            activity = (
                session.query(Activity).filter_by(label=self.activity_label).first()
            )
            if activity is None:
                activity = Activity(label=self.activity_label)
                session.add(activity)
                session.flush()
            self._activity_id = activity.id

    def _flush_loop(self):
        """Vide la queue et écrit les événements en base toutes les secondes."""
        while self._running:
            time.sleep(1.0)
            self._flush()
        # flush final après l'arrêt
        self._flush()

    def _flush(self):
        events = []
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except queue.Empty:
                break

        if not events:
            return

        keyboard_rows = []
        mouse_rows = []

        for e in events:
            etype = e["type"]
            if etype in ("key_press", "key_release"):
                keyboard_rows.append(
                    KeyboardEvent(
                        session=self.session_id,
                        user_id=self._user_id,
                        activity_id=self._activity_id,
                        event_type=etype,
                        key=e["key"],
                        timestamp=e["time"],
                        flight_time=e.get("flight_time"),
                        dwell=e.get("dwell"),
                    )
                )
            elif etype in ("click", "move", "scroll"):
                mouse_rows.append(
                    MouseEvent(
                        session=self.session_id,
                        user_id=self._user_id,
                        activity_id=self._activity_id,
                        event_type=etype,
                        x=e["x"],
                        y=e["y"],
                        timestamp=e["time"],
                        button=e.get("button"),
                        speed=e.get("speed"),
                        scroll_dx=e.get("dx"),
                        scroll_dy=e.get("dy"),
                    )
                )

        with get_session(self.db_url) as session:
            session.add_all(keyboard_rows + mouse_rows)

    def start(self):
        """Démarre les listeners et le thread de flush."""
        create_tables(self.db_url)
        self._resolve_user_and_activity()
        self._keyboard.start()
        self._mouse.start()
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def stop(self):
        """Arrête les listeners et attend le flush final."""
        self._keyboard.stop()
        self._mouse.stop()
        self._running = False
        if self._flush_thread:
            self._flush_thread.join(timeout=5)
