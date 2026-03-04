"""Dashboard Streamlit — Activity Recognition en temps réel."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.express as px
import pandas as pd
from datetime import datetime

from app.models.schema import create_tables
from app.services.db_service import (
    get_last_activity,
    get_activity_last_n_minutes,
    get_today_distribution,
    count_labeled_windows,
)
from app.inference.predictor import train_random_forest

# ── Constantes ────────────────────────────────────────────────────────────────
LABELS = ["Inactif", "Navigation Web", "Jeu vidéo", "Travail/Code"]
LABEL_COLORS = {
    "Inactif": "#6c757d",
    "Navigation Web": "#0d6efd",
    "Jeu vidéo": "#dc3545",
    "Travail/Code": "#198754",
}
DASHBOARD_REFRESH_MS = 5000

# ── Config page ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Activity Monitor",
    page_icon="📊",
    layout="wide",
)

create_tables()
st_autorefresh(interval=DASHBOARD_REFRESH_MS, key="autorefresh")

# ── Titre ─────────────────────────────────────────────────────────────────────
st.title("Activity Monitor")
st.caption(f"Dernière mise à jour : {datetime.now().strftime('%H:%M:%S')}")

# ── Activité actuelle ─────────────────────────────────────────────────────────
last = get_last_activity()
col1, col2, col3 = st.columns(3)

with col1:
    if last:
        label = last["predicted_label"]
        color = LABEL_COLORS.get(label, "#ffffff")
        st.markdown(
            f"<div style='background:{color};padding:16px;border-radius:8px;"
            f"color:white;font-size:1.4rem;font-weight:bold;text-align:center'>"
            f"{label}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("En attente de la première fenêtre (5s)...")

with col2:
    if last:
        conf = last.get("confidence", 0) * 100
        st.metric("Confiance", f"{conf:.1f}%")
        st.metric("Modèle actif", last.get("model_used", "—"))

with col3:
    n = count_labeled_windows()
    st.metric("Fenêtres collectées", n)

# ── Graphique : activité sur les 30 dernières minutes ────────────────────────
st.subheader("Activité — 30 dernières minutes")
df_recent = get_activity_last_n_minutes(30)

if not df_recent.empty:
    df_recent["window_start"] = pd.to_datetime(df_recent["window_start"], unit="s")
    fig_timeline = px.scatter(
        df_recent,
        x="window_start",
        y="predicted_label",
        color="predicted_label",
        color_discrete_map=LABEL_COLORS,
        size="confidence",
        size_max=14,
        labels={"window_start": "Heure", "predicted_label": "Activité"},
    )
    fig_timeline.update_layout(
        showlegend=False,
        margin=dict(l=0, r=0, t=0, b=0),
        height=200,
        yaxis=dict(categoryorder="array", categoryarray=LABELS),
    )
    st.plotly_chart(fig_timeline, use_container_width=True)
else:
    st.info("Pas encore de données pour les 30 dernières minutes.")

# ── Distribution du jour ──────────────────────────────────────────────────────
st.subheader("Distribution aujourd'hui")
df_dist = get_today_distribution()

if not df_dist.empty:
    fig_pie = px.pie(
        df_dist,
        names="predicted_label",
        values="count",
        color="predicted_label",
        color_discrete_map=LABEL_COLORS,
        hole=0.4,
    )
    fig_pie.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=300)
    st.plotly_chart(fig_pie, use_container_width=True)
else:
    st.info("Pas encore de données pour aujourd'hui.")

# ── Entraînement manuel du Random Forest ─────────────────────────────────────
st.divider()
st.subheader("Entraînement du modèle")

col_a, col_b = st.columns([1, 3])
with col_a:
    if st.button("Entraîner Random Forest", type="primary"):
        with st.spinner("Entraînement en cours..."):
            n_trained = train_random_forest()
        if n_trained:
            st.success(f"Random Forest entraîné sur {n_trained} fenêtres.")
        else:
            st.warning("Pas assez de données (minimum 20 fenêtres nécessaires).")

with col_b:
    st.caption(
        "Le Random Forest s'entraîne automatiquement après 100 fenêtres. "
        "Vous pouvez aussi déclencher l'entraînement manuellement ici."
    )

# ── Données brutes (expander) ─────────────────────────────────────────────────
with st.expander("Données brutes (dernières 50 entrées)"):
    df_all = get_activity_last_n_minutes(9999)
    if not df_all.empty:
        st.dataframe(df_all.tail(50), use_container_width=True)
    else:
        st.write("Aucune donnée.")
