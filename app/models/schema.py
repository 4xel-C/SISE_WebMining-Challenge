"""SQLAlchemy ORM schema for the SISE Monitor application."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import (
    BigInteger,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


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

    keyboard_events: Mapped[list["KeyboardEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    mouse_events: Mapped[list["MouseEvent"]] = relationship(
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
    label: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    keyboard_events: Mapped[list["KeyboardEvent"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )
    mouse_events: Mapped[list["MouseEvent"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"Activity(id={self.id}, label={self.label!r})"


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

    # Recording session identifier (e.g. UUID or ISO timestamp string)
    session: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # FK to the user who generated this event (nullable → unknown user)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user: Mapped["User | None"] = relationship(back_populates="keyboard_events")

    # FK to the activity label for training data annotation
    activity_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("activities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activity: Mapped["Activity | None"] = relationship(back_populates="keyboard_events")

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
            f"KeyboardEvent(id={self.id}, session={self.session!r}, "
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
      scroll_events → type, x, y, dx, dy, time
    """

    __tablename__ = "mouse_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Recording session identifier
    session: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # FK to the user who generated this event (nullable → unknown user)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user: Mapped["User | None"] = relationship(back_populates="mouse_events")

    # FK to the activity label for training data annotation
    activity_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("activities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activity: Mapped["Activity | None"] = relationship(back_populates="mouse_events")

    # "click", "move", or "scroll_events"
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
    # scroll_events only — horizontal / vertical scroll_events delta
    scroll_events_dx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scroll_events_dy: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"MouseEvent(id={self.id}, session={self.session!r}, "
            f"type={self.event_type!r}, x={self.x}, y={self.y})"
        )

# ---------------------------------------------------------------------------
# Activity log (predictions)
# ---------------------------------------------------------------------------

class ActivityLog(Base):
    """Predicted activity for a time window."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    window_start: Mapped[float] = mapped_column(Float, nullable=False)
    window_end: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_label: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model_used: Mapped[str] = mapped_column(String(32), nullable=False, default="heuristic")

# ---------------------------------------------------------------------------
# Engine / table creation helper
# ---------------------------------------------------------------------------


def get_engine(db_url: str = "sqlite:///keysentinel.db"):
    return create_engine(db_url, echo=False)


def create_tables(db_url: str = "sqlite:///keysentinel.db"):
    """Create all tables in the target database (idempotent)."""
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def get_session(
    db_url: str = "sqlite:///keysentinel.db",
) -> Generator[Session, None, None]:
    """
    Context manager that yields an open Session and handles commit/rollback/close.

    Usage:
        with get_session() as session:
            session.add(...)
    """
    engine = get_engine(db_url)
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
