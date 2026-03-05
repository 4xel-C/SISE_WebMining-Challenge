import math
import pickle
from pathlib import Path

import numpy as np

from app.features.feature_engineering import extract_features

_MODEL_PATH = Path(__file__).parent.parent.parent / "predictor" / "random_forest.pkl"
_model = None


def load_model():
    global _model
    with open(_MODEL_PATH, "rb") as f:
        _model = pickle.load(f)


def _convert(store_events: list[dict]) -> list[dict]:
    """Convertit le format store vers le format attendu par extract_features."""
    out = []
    last_release_ts: dict[str, float] = {}
    press_ts: dict[str, float] = {}
    _last_move = None

    for ev in store_events:
        d = ev.get("data", {})
        etype = d.get("event_type", "")
        ts = ev.get("ts", 0.0)

        if ev["type"] == "keyboard":
            key = d.get("key", "")
            if etype == "press":
                flight = ts - last_release_ts[key] if key in last_release_ts else None
                press_ts[key] = ts
                out.append({"type": "key_press", "time": ts, "key": key, "flight_time": flight})
            elif etype == "release":
                dwell = ts - press_ts[key] if key in press_ts else None
                last_release_ts[key] = ts
                out.append({"type": "key_release", "time": ts, "key": key, "dwell": dwell})

        elif ev["type"] == "mouse":
            if etype == "move":
                x, y = d.get("x", 0.0), d.get("y", 0.0)
                if _last_move is not None:
                    dx = x - _last_move["x"]
                    dy = y - _last_move["y"]
                    dt = ts - _last_move["ts"]
                    speed = ((dx**2 + dy**2) ** 0.5 / dt) if dt > 0 else 0.0
                else:
                    speed = 0.0
                _last_move = {"x": x, "y": y, "ts": ts}
                out.append({"type": "move", "time": ts, "speed": speed})

        elif etype == "click":
                    out.append({"type": "click", "time": ts})
        elif etype == "scroll":
                    out.append({"type": "scroll", "time": ts})

    return out


def predict(store_events: list[dict]) -> dict:
    empty = {"activity": None, "confidence": None,
             "probabilities": {"coding": None, "writing": None, "gaming": None}}

    if _model is None or len(store_events) < 5:
        return empty

    converted = _convert(store_events)
    features = extract_features(converted, window_size=10.0)
    X = np.array([[features[f] for f in _model.feature_names_in_]])
    probs = _model.predict_proba(X)[0]
    classes = list(_model.classes_)
    prob_dict = {c: round(float(p), 3) for c, p in zip(classes, probs)}
    best = classes[int(np.argmax(probs))]

    return {
        "activity": best,
        "confidence": round(float(max(probs)), 3),
        "probabilities": prob_dict,
    }
