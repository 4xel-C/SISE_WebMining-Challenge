"""Fonctions d'accès à la base pour le pipeline de prédiction."""
import time
import pandas as pd
from typing import Optional
from app.models.schema import ActivityLog, KeyboardEvent, MouseEvent, get_session
from app.models.base_model import FEATURE_NAMES

DB_URL = "sqlite:///keysentinel.db"


def insert_activity(window_start, window_end, label, confidence, model_used):
    with get_session(DB_URL) as session:
        session.add(ActivityLog(
            window_start=window_start,
            window_end=window_end,
            predicted_label=label,
            confidence=confidence,
            model_used=model_used,
        ))

# ── Queries ───────────────────────────────────────────────────────────────────

def get_last_activity() -> Optional[dict]:
    with get_session(DB_URL) as session:
        row = session.query(ActivityLog).order_by(ActivityLog.window_end.desc()).first()
        if row is None:
            return None
        return {
            "predicted_label": row.predicted_label,
            "confidence": row.confidence,
            "model_used": row.model_used,
            "window_start": row.window_start,
            "window_end": row.window_end,
        }


def get_activity_last_n_minutes(minutes: int = 30) -> pd.DataFrame:
    since = time.time() - minutes * 60
    with get_session(DB_URL) as session:
        rows = session.query(ActivityLog).filter(
            ActivityLog.window_start >= since
        ).order_by(ActivityLog.window_start).all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([{
            "window_start": r.window_start,
            "predicted_label": r.predicted_label,
            "confidence": r.confidence,
            "model_used": r.model_used,
        } for r in rows])



def get_today_distribution() -> pd.DataFrame:
    import datetime
    today_start = datetime.datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()
    with get_session(DB_URL) as session:
        rows = session.query(ActivityLog).filter(
            ActivityLog.window_start >= today_start
        ).all()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([{"predicted_label": r.predicted_label} for r in rows])
        return df.groupby("predicted_label").size().reset_index(name="count")


def count_labeled_windows() -> int:
    with get_session(DB_URL) as session:
        return session.query(ActivityLog).count()


def get_training_data() -> pd.DataFrame:
    """Retourne un DataFrame avec les features et labels pour entraîner le RF."""
    with get_session(DB_URL) as session:
        rows = session.query(ActivityLog).all()
    if not rows:
        return pd.DataFrame()
    data = [
        {f: 0.0 for f in FEATURE_NAMES} | {"label": r.predicted_label}
        for r in rows
    ]
    return pd.DataFrame(data)
