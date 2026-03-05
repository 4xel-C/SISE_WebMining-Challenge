"""Service d'enregistrement des événements clavier/souris en base de données."""

import queue
import threading
import time
import uuid
from typing import Literal

from app.collector.keyboard_listener import KeyboardListener
from app.collector.mouse_listener import MouseListener
from app.models.schema import (
    Activity,
    ActivityCategory,
    KeyboardEvent,
    MouseEvent,
    RecordingSession,
    User,
    create_tables,
    get_session,
)


class RegisterService:
    """
    Enregistre les événements clavier et souris en base de données.

    Usage:
        service = RegisterService(username="axel", activity_label=ActivityCategory.gaming)
        service.start()
        time.sleep(30)
        service.stop()
    """

    def __init__(
        self,
        username: str,
        activity_label: Literal["coding", "writing", "gaming", "train"],
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

        self._recording_session_id: int | None = None
        self._user_id: int | None = None

    def _init_session(self):
        """Crée ou récupère l'utilisateur, l'activité, et crée la RecordingSession."""
        with get_session(self.db_url) as session:
            user = session.query(User).filter_by(name=self.username).first()
            if user is None:
                user = User(name=self.username)
                session.add(user)
                session.flush()
            user.is_on_line = True
            user.on_going_activity = ActivityCategory(self.activity_label)
            user_id = user.id
            self._user_id = user_id

            activity = (
                session.query(Activity).filter_by(label=self.activity_label).first()
            )
            if activity is None:
                activity = Activity(label=self.activity_label)
                session.add(activity)
                session.flush()
            activity_id = activity.id

            recording_session = RecordingSession(
                uuid=self.session_id,
                user_id=user_id,
                activity_id=activity_id,
                started_at=time.time(),
            )
            session.add(recording_session)
            session.flush()
            self._recording_session_id = recording_session.id

    def _flush_loop(self):
        """Vide la queue et écrit les événements en base toutes les secondes."""
        while self._running:
            time.sleep(1.0)
            try:
                self._flush()
            except Exception as exc:
                print(f"[RegisterService] erreur flush : {exc}")
        # flush final après l'arrêt
        try:
            self._flush()
        except Exception as exc:
            print(f"[RegisterService] erreur flush final : {exc}")

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
                        recording_session_id=self._recording_session_id,
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
                        recording_session_id=self._recording_session_id,
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
        self._init_session()
        self._keyboard.start()
        self._mouse.start()
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def _close_session(self):
        """Renseigne ending_at sur la RecordingSession en base."""
        if self._recording_session_id is None:
            return
        with get_session(self.db_url) as session:
            rec = session.get(RecordingSession, self._recording_session_id)
            if rec is not None:
                rec.ending_at = time.time()
            if self._user_id is not None:
                user = session.get(User, self._user_id)
                if user is not None:
                    user.is_on_line = False
                    user.on_going_activity = None

    def stop(self):
        """Arrête les listeners et attend le flush final."""
        self._keyboard.stop()
        self._mouse.stop()
        self._running = False
        if self._flush_thread:
            self._flush_thread.join(timeout=5)
        self._close_session()
