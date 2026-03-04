from abc import ABC, abstractmethod
import numpy as np


FEATURE_NAMES = [
    "keys_per_sec", 
    "wpm", 
    "mean_dwell", 
    "std_dwell",
    "mean_flight",
    "std_flight",
    "special_key_ratio",
    "gaming_key_ratio",
    "burst_count",
    "pause_ratio",
    "clicks_per_sec",
    "mean_move_speed",
    "scroll_events",
    "double_click_count",
]



def features_to_array(features: dict) -> np.ndarray:
    """Convertit un dict de features en vecteur numpy ordonné."""
    return np.array([features.get(f, 0.0) for f in FEATURE_NAMES], dtype=np.float32)


class BaseModel(ABC):

    @abstractmethod
    def predict(self, features: dict) -> tuple[str, float]:
        """
        Retourne (label, confidence) pour un vecteur de features.
        confidence est entre 0.0 et 1.0.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifiant du modèle utilisé dans activity_log."""

    def is_trained(self) -> bool:
        return True
