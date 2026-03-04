"""
Moteur de prédiction temps réel.
Phase 1 : heuristiques → labels automatiques.
Phase 2+ : Random Forest (puis LSTM/CNN quand disponibles).
"""


from app.services.db_service import insert_activity, count_labeled_windows, get_training_data

MIN_WINDOWS_FOR_RF = 100
from app.models.random_forest import RandomForestModel

# Modèles chargés une seule fois
_rf = RandomForestModel()

# Import différé pour ne pas charger TensorFlow si inutile
_lstm = None
_cnn = None


# def _get_lstm():
#     global _lstm
#     if _lstm is None:
#         from app.models.lstm import LSTMModel
#         _lstm = LSTMModel()
#     return _lstm


# def _get_cnn():
#     global _cnn
#     if _cnn is None:
#         from app.models.cnn1d import CNN1DModel
#         _cnn = CNN1DModel()
#     return _cnn


# ── Heuristiques bootstrap ────────────────────────────────────────────────────

def _heuristic_label(features: dict) -> tuple[str, float]:
    keys_per_sec = features["keys_per_sec"]
    sr = features["special_key_ratio"]
    gr = features.get("gaming_key_ratio", 0.0)
    mean_move_speed = features["mean_move_speed"]
    clicks_per_sec = features.get("clicks_per_sec", 0.0)
    double_clicks = features["double_click_count"]
    scroll_events = features["scroll_events"]
    wpm = features.get("wpm", 0.0)
    mean_dwell = features["mean_dwell"]



    
    

    # Inactif
    if keys_per_sec < 0.5 and clicks_per_sec < 0.3 and mean_move_speed < 200:
        return "Inactif", 0.90

    # Jeu vidéo : souris rapide + frappes fréquentes sur game keys
    # OU fréquence de clics élevée (clicker games, RTS) + game keys dominantes
    if mean_move_speed > 3000 and keys_per_sec > 1.0 and gr > 0.30:
        return "Jeu vidéo", 0.85
    if gr > 0.50 and keys_per_sec > 1.5:
        return "Jeu vidéo", 0.80
    if clicks_per_sec > 2.0 and mean_move_speed> 2000:
        return "Jeu vidéo", 0.75
    if gr > 0.30 and mean_dwell > 150:  
        return "Jeu vidéo", 0.80

    # Navigation Web : beaucoup de scroll_events et de clics, peu de frappe
    if scroll_events > 5 and clicks_per_sec > 5 and wpm < 20:
        return "Navigation Web", 0.75

    # Travail / Code : frappe dense avec touches productivité (tab, F-keys, cmd)
    if wpm > 40 or (wpm > 20 and sr > 0.20):
        return "Travail/Code", 0.75

    # Fallback
    if keys_per_sec > clicks_per_sec and keys_per_sec > scroll_events:
        return "Travail/Code", 0.55
    if scroll_events > keys_per_sec:
        return "Navigation Web", 0.55
    return "Inactif", 0.50


# ── Sélection du meilleur modèle disponible ────────────────────────────────────

def _best_model():

    if _rf.is_trained():
        return _rf

    # cnn = _get_cnn()
    # if cnn.is_trained():
    #     return cnn

    # lstm = _get_lstm()
    # if lstm.is_trained():
    #     return lstm



    return None


# ── Point d'entrée principal ──────────────────────────────────────────────────

def on_window(features: dict):
    """
    Appelé par l'agrégateur après chaque fenêtre de WINDOW_SIZE secondes.
    Choisit le meilleur modèle disponible, prédit l'activité et la persiste.
    """
    model = _best_model()

    if model is not None:
        label, confidence = model.predict(features)
        model_name = model.name
    else:
        label, confidence = _heuristic_label(features)
        model_name = "heuristic"

    insert_activity(
        window_start=features["window_start"],
        window_end=features["window_end"],
        label=label,
        confidence=confidence,
        model_used=model_name,
    )

    # Déclenchement automatique de l'entraînement RF une fois le seuil atteint
    total = count_labeled_windows()
    if total == MIN_WINDOWS_FOR_RF and not _rf.is_trained():
        print(f"[predictor] {total} fenêtres collectées → entraînement Random Forest...")
        train_random_forest()


def train_random_forest():
    """Entraîne (ou ré-entraîne) le Random Forest sur les données DB."""
    df = get_training_data()
    if df.empty or len(df) < 20:
        print("[predictor] pas assez de données pour entraîner le RF.")
        return
    _rf.train(df)
    print(f"[predictor] RF entraîné sur {len(df)} fenêtres.")
    return len(df)
