# SISE WebMining Challenge — KeySentinel

![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-informational)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?logo=flask)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.5+-orange?logo=scikit-learn)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-red)
![License](https://img.shields.io/badge/license-MIT-green)
![Built in](https://img.shields.io/badge/built%20in-48h-%23e74c3c)

> Application de monitoring comportemental en temps reel par analyse des entrees clavier et souris, avec classification d'activite par Machine Learning.

---

## Contexte

Ce projet a ete realise dans le cadre du **SISE WebMining Challenge**, un hackathon universitaire avec une contrainte de **48 heures**. L'objectif : concevoir et livrer une application fonctionnelle de bout en bout — collecte de donnees, feature engineering, modele ML, stockage persistant et interface web — en un temps extremement reduit.

Le defi principal etait de concilier la rapidite de developpement avec la robustesse technique : pipeline temps reel, API Flask decouplee, modele Random Forest entraine sur des donnees comportementales, et dashboard interactif accessible depuis un navigateur.

---

## Apercu

<img width="3010" height="1038" alt="image" src="https://github.com/user-attachments/assets/c22b78cb-ac50-4a26-810b-a030b0f6b376" />

---

## Fonctionnalites

- **Collecte temps reel** des evenements clavier (press/release, dwell time, flight time) et souris (deplacement, clics, scroll)
- **Feature engineering** sur une fenetre glissante de 10 secondes : WPM, keys/sec, vitesse souris, gaming key ratio, mean dwell, etc.
- **Classification d'activite** via un modele Random Forest pre-entraine : `coding` | `writing` | `gaming`
- **Prediction en arriere-plan** toutes les 10 secondes, cumulant le temps par categorie d'activite par session
- **Dashboard live** (frontend HTML/JS) affichant les metriques en direct et la prediction courante
- **Mode Sentinel** : supervision multi-utilisateurs, historique des sessions, replay et statistiques agregees
- **Stockage persistant** : SQLite par defaut, PostgreSQL configurable via `.env`
- **Architecture decouplee** : agent CLI (pynput) + serveur Flask + frontend statique

---

## Architecture

```
KeySentinel
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── agent.py        # POST endpoints (agent -> serveur)
│   │   │   ├── dashboard.py    # GET endpoints + boucle de prediction bg
│   │   │   └── sentinel.py     # GET endpoints supervision multi-users
│   │   └── store.py            # Couche acces donnees (in-memory + DB)
│   ├── collector/
│   │   ├── keyboard_listener.py  # Listener pynput clavier
│   │   └── mouse_listener.py     # Listener pynput souris
│   ├── features/
│   │   └── feature_engineering.py  # Extraction de 14 features comportementales
│   ├── models/
│   │   └── schema.py           # ORM SQLAlchemy (User, Session, Events)
│   └── services/
│       ├── feature_service.py  # Fetch + conversion des evenements DB
│       ├── ml_service.py       # Chargement et inference Random Forest
│       ├── pygame_record_service.py
│       └── register_service.py
├── frontend/
│   ├── index.html              # Dashboard utilisateur
│   ├── sentinel.html           # Interface supervision
│   └── static/                 # CSS + JS
├── predictor/
│   └── random_forest.pkl       # Modele ML pre-entraine
└── pyproject.toml
```

---

## Pipeline temps reel

```
[pynput listeners]
       |
       v  (events batch, POST /api/ingest)
[Flask API server]
       |
       +---> [SQLite / PostgreSQL]
       |              |
       |     (fetch last 10s)
       v
[Background prediction loop]  (toutes les 10s)
       |
       +---> [Feature extraction (14 features)]
       |
       +---> [Random Forest .predict_proba()]
       |
       +---> [Mise a jour coding_time / writing_time / gaming_time]
       |
       v
[GET /api/predict/live]  <--- Dashboard JS (polling)
```

---

## Features extraites

| Feature              | Description                                           |
| -------------------- | ----------------------------------------------------- |
| `keys_per_sec`       | Nombre de touches par seconde                         |
| `wpm`                | Mots par minute (estimation)                          |
| `mean_dwell`         | Duree moyenne de maintien d'une touche (ms)           |
| `std_dwell`          | Ecart-type du dwell time                              |
| `mean_flight`        | Temps moyen entre deux frappes (ms)                   |
| `std_flight`         | Ecart-type du flight time                             |
| `special_key_ratio`  | Ratio touches speciales (Ctrl, Alt, Shift, F1-F12...) |
| `gaming_key_ratio`   | Ratio touches gaming (WASD, fleches)                  |
| `burst_count`        | Nombre de pauses > 0.5s dans la frappe                |
| `pause_ratio`        | Proportion du temps en pause                          |
| `clicks_per_sec`     | Clics souris par seconde                              |
| `mean_move_speed`    | Vitesse moyenne de deplacement souris (px/s)          |
| `scroll_events`      | Nombre d'evenements de scroll                         |
| `double_click_count` | Nombre de double-clics detectes                       |

---

## Installation

### Prerequis

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) (gestionnaire de packages recommande)

### Setup

```bash
# Cloner le depot
git clone <repo-url>
cd SISE_WebMining-Challenge

# Installer les dependances
uv sync

# (Optionnel) Configurer PostgreSQL
cp .env.example .env
# Editer .env avec DB_USER, DB_PASSWORD, DB_HOST, DB_NAME
```

---

## Utilisation

### Lancer le tout

```bash
uv run run.py
```

### Lancer le serveur Flask

```bash
uv run python -m app
# ou
flask --app app run
```

### Demarrer une session de capture

```bash
# Enregistrer une session labellisee (pour training / replay)
uv run python run_capture.py --user alice --activity coding

# Les activites disponibles : coding | writing | gaming
```

### Acceder aux interfaces

| Interface             | URL                              |
| --------------------- | -------------------------------- |
| Dashboard utilisateur | `http://localhost:5000/`         |
| Supervision Sentinel  | `http://localhost:5000/sentinel` |

<img width="2224" height="1470" alt="image" src="https://github.com/user-attachments/assets/6e035c1a-0d60-43c8-a362-2f3e4386254d" />

---

## Configuration base de donnees

Par defaut, l'application utilise **SQLite** (`keysentinel.db` a la racine du projet).

Pour utiliser **PostgreSQL**, creer un fichier `.env` :

```env
DB_USER=postgres
DB_PASSWORD=secret
DB_HOST=localhost
DB_PORT=5432
DB_NAME=keysentinel
```

---

## Modele ML

Le modele Random Forest (`predictor/random_forest.pkl`) a ete entraine sur des sessions labellisees de frappe clavier/souris pour distinguer trois classes comportementales :

- **coding** — frappe irreguliere, nombreux caracteres speciaux, pauses frequentes
- **writing** — frappe reguliere, faible ratio touches speciales, WPM eleve
- **gaming** — ratio WASD/fleches eleve, clics frequents, vitesse souris elevee

La prediction tourne en **arriere-plan** toutes les 10 secondes et cumule le temps par activite sur chaque session.

---

## Stack technique

| Composant           | Technologie                        |
| ------------------- | ---------------------------------- |
| Collecte evenements | `pynput`                           |
| Serveur API         | `Flask`                            |
| ORM / BDD           | `SQLAlchemy` + SQLite / PostgreSQL |
| Machine Learning    | `scikit-learn` (Random Forest)     |
| Feature engineering | `numpy`                            |
| Frontend            | HTML / CSS / JavaScript vanilla    |
| Packaging           | `hatchling` + `uv`                 |

---

## Equipe

Projet realise en 48h dans le cadre du **SISE WebMining Challenge** — Master SISE, Universite Lyon 2.
