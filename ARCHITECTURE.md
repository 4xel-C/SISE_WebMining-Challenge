# Project Architecture — SISE WebMining Challenge

## Objectif

Application IA locale capable de prédire l'activité d'un utilisateur PC
(**idle / working / gaming**) à partir des données de périphériques (clavier + souris).

---

## Stack

### Agent Local (Python)

- **pynput** — capture clavier + souris (droits système complets car script local)
- **Flask** — serveur HTTP sur `localhost:5000`
- **SQLite** — base de données unique (`keysentinel.db`), pas de fichiers parquet
- **SQLAlchemy** — ORM pour lecture/écriture BDD
- **scikit-learn** — RandomForestClassifier (Phase 1)
- **joblib** — sauvegarde/chargement du modèle entraîné

### Frontend

- **HTML + CSS + JS vanilla** — page statique servie par Flask
- **Chart.js** (CDN) — graphiques temps réel
- **Tailwind** (CDN) — styles
- Polling `fetch()` toutes les 2s sur les endpoints Flask (pas de WebSocket)

---

## Architecture

```
pynput (listener)
      │  batch 200ms
      ▼
Flask /ingest  →  SQLite (keysentinel.db)
                        │
              ┌─────────┴──────────┐
              ▼                    ▼
     GET /api/features/live   sessions historiques
     GET /api/predict/live         │
              │                    ▼
              │            train RandomForest
              │            (fin de session)
              ▼                    │
       index.html             model.joblib
    (poll toutes 2s)
```

---

## Flow d'une session

```
uv run run_capture.py
  → prompt "Quel utilisateur ?"      → ex: cyraptor
  → prompt "Quelle activité ?"       → [1] idle  [2] working  [3] gaming
  → countdown 3s
  → enregistrement (pynput → Flask → SQLite)
  → touche End
        → sauvegarde session labelisée en BDD
        → extraction features (fenêtres glissantes 10s)
        → entraînement RandomForest sur toutes les sessions historiques
        → sauvegarde model.joblib
```

---

## Endpoints Flask

| Endpoint             | Méthode | Description                         |
| -------------------- | ------- | ----------------------------------- |
| `/`                  | GET     | Sert `frontend/index.html`          |
| `/api/ingest`        | POST    | Reçoit batch d'events depuis pynput |
| `/api/status`        | GET     | Session en cours ou non             |
| `/api/features/live` | GET     | Dernière fenêtre de features (10s)  |
| `/api/predict/live`  | GET     | Prédiction RF + score de confiance  |
| `/api/sessions`      | GET     | Historique des sessions labelisées  |
| `/api/session/stop`  | POST    | Stoppe session → entraîne modèle    |

---

## Structure projet

```
SISE_WebMining-Challenge/
├── app/
│   ├── collector/
│   │   └── listener.py          capture pynput → POST /api/ingest
│   ├── features/
│   │   └── extractor.py         features glissantes (polars/pandas)
│   ├── models/
│   │   └── database.py          SQLAlchemy + SQLite schema
│   ├── services/
│   │   ├── register_service.py  batch insert BDD
│   │   └── ml_service.py        train() / predict() interface
│   └── api/
│       └── main.py              Flask app + tous les endpoints
├── frontend/
│   └── index.html               dashboard JS polling
├── run_capture.py               point d'entrée principal
├── model.joblib                 modèle entraîné (gitignore)
├── keysentinel.db               base SQLite (gitignore)
├── ARCHITECTURE.md              ce fichier
└── pyproject.toml
```

---

## Base de données (SQLite)

### Table `events`

| Colonne      | Type       | Description                        |
| ------------ | ---------- | ---------------------------------- |
| `id`         | INTEGER PK | auto                               |
| `session_id` | TEXT       | UUID de la session                 |
| `wall_time`  | DATETIME   | horodatage UTC                     |
| `elapsed_s`  | FLOAT      | secondes depuis début session      |
| `device`     | TEXT       | `mouse` / `keyboard`               |
| `event_type` | TEXT       | `move/click/scroll/press/release`  |
| `x`          | INTEGER    | position souris (NULL si keyboard) |
| `y`          | INTEGER    | position souris (NULL si keyboard) |
| `key_button` | TEXT       | touche ou bouton                   |
| `extra`      | TEXT       | JSON (pressed, scroll_dx/dy)       |

### Table `sessions`

| Colonne       | Type     | Description               |
| ------------- | -------- | ------------------------- |
| `id`          | TEXT PK  | UUID                      |
| `user`        | TEXT     | nom utilisateur           |
| `activity`    | TEXT     | `idle / working / gaming` |
| `started_at`  | DATETIME | début                     |
| `ended_at`    | DATETIME | fin                       |
| `event_count` | INTEGER  | nb events total           |

### Table `features`

| Colonne            | Type       | Description                  |
| ------------------ | ---------- | ---------------------------- |
| `id`               | INTEGER PK | auto                         |
| `session_id`       | TEXT FK    | référence session            |
| `window_start`     | FLOAT      | début fenêtre (elapsed_s)    |
| `window_end`       | FLOAT      | fin fenêtre                  |
| `keys_per_sec`     | FLOAT      |                              |
| `mouse_speed`      | FLOAT      | px/s moyen                   |
| `click_rate`       | FLOAT      | clics/s                      |
| `gaming_key_ratio` | FLOAT      | WASD+flèches / total         |
| `wpm`              | FLOAT      | estimation WPM               |
| `mean_dwell`       | FLOAT      | ms touche enfoncée           |
| `activity`         | TEXT       | label (si session labelisée) |

---

## ML — Phase 1 (actuelle)

- **Modèle** : `RandomForestClassifier` (scikit-learn)
- **Entraînement** : fin de session, sur toutes les fenêtres historiques
- **Prédiction** : toutes les 2s sur la fenêtre des 10 dernières secondes
- **Interface** : `ml_service.train()` / `ml_service.predict(features_dict)`

## ML — Phase 2 (future)

- **Modèle** : LSTM sur séquences brutes d'events
- Même interface `train()` / `predict()` → swap transparent

---

## Décisions techniques

| Décision               | Choix                | Raison                                                            |
| ---------------------- | -------------------- | ----------------------------------------------------------------- |
| Pas de parquet         | SQLite uniquement    | un seul fichier, lecture/écriture simple, pas de gestion fichiers |
| Pas de WebSocket       | polling HTTP 2s      | même machine, split screen, largement suffisant                   |
| Pas de Streamlit       | Flask + HTML vanilla | Streamlit incompatible Python 3.13 + pandas 3                     |
| Pas de DuckDB/Polars   | SQLite + SQLAlchemy  | déjà dans le projet, évite dépendances inutiles                   |
| Labelling au lancement | prompt CLI           | simple, pas d'UI supplémentaire                                   |
