"""Service to fetch raw events from DB and compute features for a given user."""

import time

import pandas as pd
from sqlalchemy.orm import Session

from app.features.feature_engineering import FEATURE_NAMES, extract_features
from app.models.schema import (
    Activity,
    KeyboardEvent,
    MouseEvent,
    RecordingSession,
    User,
    _DB_URL,
    get_engine,
)

TARGET_ACTIVITIES = {"gaming", "coding", "writing"}


class FeatureService:
    """
    Two responsibilities:

    1. fetch_events(username, window_size) -> (kb_events, ms_events)
       Queries the DB for the last `window_size` seconds of events for a user.

    2. compute_features(kb_events, ms_events, window_size) -> pd.DataFrame
       Takes the raw event lists and returns a single-row DataFrame of features,
       ready for model prediction.

    Usage:
        service = FeatureService()

        kb, ms = service.fetch_events("axel", window_size=10)
        df = service.compute_features(kb, ms, window_size=10)

        prediction = model.predict(df[FEATURE_NAMES])
    """

    def __init__(self, db_url: str | None = None):
        self._engine = get_engine(db_url or _DB_URL)

    # ------------------------------------------------------------------
    # 1. Fetch raw events from DB
    # ------------------------------------------------------------------

    def fetch_events(
        self, username: str, window_size: float
    ) -> tuple[list[dict], list[dict]]:
        """
        Return keyboard and mouse events for `username` in the last `window_size` seconds.

        Args:
            username:    Name of the user to query.
            window_size: Duration of the lookback window in seconds (e.g. 5, 10, 15).

        Returns:
            (kb_events, ms_events) — two lists of plain dicts, ready for extract_features().
        """
        since = time.time() - window_size

        with Session(self._engine) as session:
            user = session.query(User).filter_by(name=username).first()
            if user is None:
                return [], []

            # Most recent open session for this user
            rec_session = (
                session.query(RecordingSession)
                .filter(
                    RecordingSession.user_id == user.id,
                    RecordingSession.ending_at.is_(None),
                )
                .order_by(RecordingSession.started_at.desc())
                .first()
            )
            if rec_session is None:
                return [], []

            kb_events = self._fetch_keyboard(session, rec_session.id, since=since)
            ms_events = self._fetch_mouse(session, rec_session.id, since=since)

        return kb_events, ms_events

    # ------------------------------------------------------------------
    # 2. Feature engineering -> DataFrame
    # ------------------------------------------------------------------

    def compute_features(
        self,
        kb_events: list[dict],
        ms_events: list[dict],
        window_size: float,
    ) -> pd.DataFrame:
        """
        Aggregate raw events into a single-row feature DataFrame.

        Args:
            kb_events:   Output of fetch_events()[0].
            ms_events:   Output of fetch_events()[1].
            window_size: Must match the window_size used in fetch_events().

        Returns:
            pd.DataFrame with one row and columns = FEATURE_NAMES.
        """
        all_events = kb_events + ms_events
        features = extract_features(all_events, window_size)
        return pd.DataFrame([features], columns=FEATURE_NAMES)

    # ------------------------------------------------------------------
    # 3. Training dataset — all labelled sessions aggregated by window
    # ------------------------------------------------------------------

    def build_training_dataframe(self, window_size: float = 10.0) -> pd.DataFrame:
        """
        Build a labelled feature DataFrame from all sessions in the DB whose
        activity is one of: gaming, coding, writing.

        Each row = one time window of `window_size` seconds.
        The last column is "label" (the activity of the RecordingSession).

        Args:
            window_size: Duration of each aggregation window in seconds.

        Returns:
            pd.DataFrame with columns = FEATURE_NAMES + ["label"].
            Empty DataFrame if no labelled sessions exist.

        Usage:
            df = service.build_training_dataframe(window_size=10)
            X = df[FEATURE_NAMES]
            y = df["label"]
        """
        rows = []

        with Session(self._engine) as session:
            labelled_sessions = (
                session.query(RecordingSession, Activity.label)
                .join(Activity, RecordingSession.activity_id == Activity.id)
                .filter(
                    Activity.label.in_(TARGET_ACTIVITIES),
                    RecordingSession.ending_at.isnot(None),
                )
                .all()
            )

            for rec_session, activity_label in labelled_sessions:
                kb_events = self._fetch_keyboard(session, rec_session.id, since=0.0)
                ms_events = self._fetch_mouse(session, rec_session.id, since=0.0)

                windows = self._slice_windows(
                    rec_session.started_at,
                    rec_session.ending_at,
                    kb_events,
                    ms_events,
                    window_size,
                )
                label = str(activity_label.value)
                for w in windows:
                    w["label"] = label
                    rows.append(w)

        return pd.DataFrame(rows, columns=FEATURE_NAMES + ["label"])

    def _slice_windows(
        self,
        started_at: float,
        ending_at: float,
        kb_events: list[dict],
        ms_events: list[dict],
        window_size: float,
    ) -> list[dict]:
        """Split events into fixed non-overlapping windows and extract features."""
        rows = []
        t = started_at
        while t + window_size <= ending_at:
            t_end = t + window_size
            kb_win = [e for e in kb_events if t <= e["time"] < t_end]
            ms_win = [e for e in ms_events if t <= e["time"] < t_end]
            features = extract_features(kb_win + ms_win, window_size)
            rows.append(features)
            t = t_end
        return rows

    # ------------------------------------------------------------------
    # Internal DB queries
    # ------------------------------------------------------------------

    def _fetch_keyboard(
        self, session: Session, session_id: int, since: float | None = None
    ) -> list[dict]:
        q = session.query(KeyboardEvent).filter(
            KeyboardEvent.recording_session_id == session_id
        )
        if since is not None:
            q = q.filter(KeyboardEvent.timestamp >= since)
        rows = q.order_by(KeyboardEvent.timestamp).all()
        return [
            {
                "type": r.event_type,
                "key": r.key,
                "time": r.timestamp,
                "flight_time": r.flight_time,
                "dwell": r.dwell,
            }
            for r in rows
        ]

    def _fetch_mouse(
        self, session: Session, session_id: int, since: float | None = None
    ) -> list[dict]:
        q = session.query(MouseEvent).filter(
            MouseEvent.recording_session_id == session_id
        )
        if since is not None:
            q = q.filter(MouseEvent.timestamp >= since)
        rows = q.order_by(MouseEvent.timestamp).all()
        return [
            {
                "type": r.event_type,
                "x": r.x,
                "y": r.y,
                "time": r.timestamp,
                "speed": r.speed,
            }
            for r in rows
        ]
