





import os
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder


RF_MODEL_PATH = "app/models/saved/random_forest.joblib"
LABELS = ["Inactif", "Navigation Web", "Jeu vidéo", "Travail/Code"]

from app.models.base_model import BaseModel, features_to_array, FEATURE_NAMES


class RandomForestModel(BaseModel):

    def __init__(self):
        self._clf = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1,
        )
        self._encoder = LabelEncoder()
        self._encoder.fit(LABELS)
        self._trained = False
        self._load_if_exists()

    def _load_if_exists(self):
        if os.path.exists(RF_MODEL_PATH):
            data = joblib.load(RF_MODEL_PATH)
            self._clf = data["clf"]
            self._encoder = data["encoder"]
            self._trained = True
            print(f"[RandomForest] modèle chargé depuis {RF_MODEL_PATH}")

    def train(self, df):
        """
        df : DataFrame avec colonnes FEATURE_NAMES + 'label'.
        """
        X = df[FEATURE_NAMES].values.astype(np.float32)
        y = self._encoder.transform(df["label"].values)
        self._clf.fit(X, y)
        self._trained = True
        os.makedirs(os.path.dirname(RF_MODEL_PATH), exist_ok=True)
        joblib.dump({"clf": self._clf, "encoder": self._encoder}, RF_MODEL_PATH)
        print(f"[RandomForest] modèle sauvegardé → {RF_MODEL_PATH}")

    def predict(self, features: dict) -> tuple[str, float]:
        if not self._trained:
            return "Inactif", 0.0
        x = features_to_array(features).reshape(1, -1)
        proba = self._clf.predict_proba(x)[0]
        idx = int(np.argmax(proba))
        label = self._encoder.inverse_transform([idx])[0]
        return label, float(proba[idx])

    def is_trained(self) -> bool:
        return self._trained

    @property
    def name(self) -> str:
        return "random_forest"
