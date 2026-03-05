"""Service d'enregistrement clavier alimenté par les events Pygame (sans pynput)."""

import time
import uuid

from app.models.schema import (
    Activity,
    KeyboardEvent,
    RecordingSession,
    User,
    _DB_URL,
    create_tables,
    get_session,
)


class PygameRecordService:
    """
    Enregistre les frappes clavier en base à partir d'events Pygame.

    Usage:
        service = PygameRecordService(username="axel", activity_label="training")
        service.start()

        # Dans la boucle pygame :
        for event in pygame.event.get():
            service.feed(event)

        service.stop()  # flush final
    """

    def __init__(
        self,
        username: str,
        activity_label: str,
        db_url: str | None = None,
        session_id: str | None = None,
    ):
        self.username = username
        self.activity_label = activity_label
        self.db_url = db_url or _DB_URL
        self.session_id = session_id or str(uuid.uuid4())

        self._recording_session_id: int | None = None

        self._press_times: dict[str, float] = {}
        self._last_release_time: float | None = None
        self._pending: list[KeyboardEvent] = []

    def _init_session(self):
        """Crée ou récupère l'utilisateur, l'activité, et crée la RecordingSession."""
        with get_session(self.db_url) as session:
            user = session.query(User).filter_by(name=self.username).first()
            if user is None:
                user = User(name=self.username)
                session.add(user)
                session.flush()
            user_id = user.id

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

    def start(self):
        create_tables(self.db_url)
        self._init_session()
        self._press_times.clear()
        self._last_release_time = None
        self._pending.clear()

    def feed(self, event):
        """Passe un event pygame.event au service. Appeler dans la boucle d'events."""
        import pygame

        now = time.time()

        if event.type == pygame.KEYDOWN:
            key_name = event.unicode if event.unicode else pygame.key.name(event.key)
            self._press_times[event.key] = now
            self._pending.append(
                KeyboardEvent(
                    recording_session_id=self._recording_session_id,
                    event_type="key_press",
                    key=key_name,
                    timestamp=now,
                    flight_time=(
                        (now - self._last_release_time)
                        if self._last_release_time
                        else None
                    ),
                    dwell=None,
                )
            )

        elif event.type == pygame.KEYUP:
            key_name = event.unicode if event.unicode else pygame.key.name(event.key)
            press_time = self._press_times.pop(event.key, None)
            dwell = (now - press_time) if press_time else None
            self._last_release_time = now
            self._pending.append(
                KeyboardEvent(
                    recording_session_id=self._recording_session_id,
                    event_type="key_release",
                    key=key_name,
                    timestamp=now,
                    flight_time=None,
                    dwell=dwell,
                )
            )

    def stop(self):
        """Flush tous les events en attente et clôture la RecordingSession."""
        with get_session(self.db_url) as session:
            if self._pending:
                session.add_all(self._pending)
                self._pending.clear()
            if self._recording_session_id is not None:
                rec = session.get(RecordingSession, self._recording_session_id)
                if rec is not None:
                    rec.ending_at = time.time()
