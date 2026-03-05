"""SQLAlchemy ORM schema for the SISE Monitor application."""

import enum
import os
import time
from contextlib import contextmanager
from typing import Generator
from urllib.parse import quote_plus

from dotenv import load_dotenv

from sqlalchemy import (
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


# ---------------------------------------------------------------------------
# DB URL helper — reads .env at project root, prefers PostgreSQL when available
# ---------------------------------------------------------------------------


def _find_env_file() -> str | None:
    """Locate .env next to the executable (frozen) or in the project root (dev)."""
    if getattr(__import__("sys"), "frozen", False):
        import sys

        return os.path.join(os.path.dirname(sys.executable), ".env")
    return None  # let load_dotenv() search upward from cwd


def get_db_url() -> str:
    """Return the database URL from .env (PostgreSQL) or fall back to SQLite."""
    load_dotenv(dotenv_path=_find_env_file())
    _user = os.getenv("DB_USER")
    _password = os.getenv("DB_PASSWORD")
    _host = os.getenv("DB_HOST")
    _port = os.getenv("DB_PORT", "5432")
    _name = os.getenv("DB_NAME", "postgres")
    if _user and _password and _host:
        return (
            f"postgresql+psycopg2://{quote_plus(_user)}:{quote_plus(_password)}"
            f"@{_host}:{_port}/{_name}"
        )
    return "sqlite:///keysentinel.db"


_DB_URL: str = get_db_url()


class ActivityCategory(enum.Enum):
    coding = "coding"
    writing = "writing"
    gaming = "gaming"


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class User(Base):
    """Registered user whose inputs are tracked."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    # Update if the user is online or not (for real-time monitoring)
    is_on_line: Mapped[bool] = mapped_column(default=False)
    on_going_activity: Mapped[ActivityCategory | None] = mapped_column(
        Enum(ActivityCategory), nullable=True
    )

    sessions: Mapped[list["RecordingSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"User(id={self.id}, name={self.name!r})"


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------
class Activity(Base):
    """Activity label used to tag training sessions (e.g. 'work', 'gaming')."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[ActivityCategory] = mapped_column(
        Enum(ActivityCategory), nullable=False, unique=True
    )

    sessions: Mapped[list["RecordingSession"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"Activity(id={self.id}, label={self.label!r})"


# ---------------------------------------------------------------------------
# Recording Session
# ---------------------------------------------------------------------------


class RecordingSession(Base):
    """Central session record linking a user, an activity, and all its events."""

    __tablename__ = "recording_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    activity_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("activities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    started_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)
    ending_at: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Time spent (in minutes) per activity category during this session
    coding_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    writing_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gaming_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    user: Mapped["User | None"] = relationship(back_populates="sessions")
    activity: Mapped["Activity | None"] = relationship(back_populates="sessions")

    keyboard_events: Mapped[list["KeyboardEvent"]] = relationship(
        back_populates="recording_session", cascade="all, delete-orphan"
    )
    mouse_events: Mapped[list["MouseEvent"]] = relationship(
        back_populates="recording_session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"RecordingSession(id={self.id}, uuid={self.uuid!r})"


# ---------------------------------------------------------------------------
# Keyboard events
# ---------------------------------------------------------------------------


class KeyboardEvent(Base):
    """
    One keyboard event as produced by KeyboardListener.

    Collector fields captured:
      key_press  → type, key, time, flight_time
      key_release → type, key, time, dwell
    """

    __tablename__ = "keyboard_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    recording_session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("recording_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recording_session: Mapped["RecordingSession"] = relationship(
        back_populates="keyboard_events"
    )

    # "key_press" or "key_release"
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # String representation of the key, e.g. 'a', 'Key.ctrl_l'
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    # Unix timestamp (float seconds)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False, index=True)

    # key_press only — time since last key_release (seconds), NULL if first event
    flight_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    # key_release only — time key was held down (seconds)
    dwell: Mapped[float | None] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return (
            f"KeyboardEvent(id={self.id}, session_id={self.recording_session_id}, "
            f"type={self.event_type!r}, key={self.key!r})"
        )


# ---------------------------------------------------------------------------
# Mouse events
# ---------------------------------------------------------------------------


class MouseEvent(Base):
    """
    One mouse event as produced by MouseListener.

    Collector fields captured:
      click  → type, x, y, button, time
      move   → type, x, y, speed, time
      scroll → type, x, y, dx, dy, time
    """

    __tablename__ = "mouse_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    recording_session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("recording_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recording_session: Mapped["RecordingSession"] = relationship(
        back_populates="mouse_events"
    )

    # "click", "move", or "scroll"
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # Cursor position at event time
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    # Unix timestamp (float seconds)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False, index=True)

    # click only — e.g. "Button.left", "Button.right"
    button: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # move only — instantaneous speed in px/s
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    # scroll only — horizontal / vertical scroll delta
    scroll_dx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scroll_dy: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"MouseEvent(id={self.id}, session_id={self.recording_session_id}, "
            f"type={self.event_type!r}, x={self.x}, y={self.y})"
        )


# ---------------------------------------------------------------------------
# Engine / table creation helper
# ---------------------------------------------------------------------------


def get_engine(db_url: str | None = None):
    # NullPool: no connection reuse — every checkout opens a fresh connection,
    # guaranteeing that concurrent writers (agent process) are always visible
    # to readers (Flask process).
    return create_engine(db_url or _DB_URL, echo=False, poolclass=NullPool)


def create_tables(db_url: str | None = None):
    """Create all tables in the target database (idempotent)."""
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def get_session(
    db_url: str | None = None,
) -> Generator[Session, None, None]:
    """
    Context manager that yields an open Session and handles commit/rollback/close.

    Usage:
        with get_session() as session:
            session.add(...)
    """
    engine = get_engine(db_url or _DB_URL)
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
