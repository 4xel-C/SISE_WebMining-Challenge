"""
Flask application factory.

Usage:
    uv run flask --app app.api run --debug
  or via run_server.py:
    uv run run_server.py
"""

from pathlib import Path

from flask import Flask, send_from_directory

from app.api.routes import agent, dashboard

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(FRONTEND_DIR))

    # ── Blueprints ────────────────────────────────────────────────
    app.register_blueprint(dashboard)  # GET  — frontend visualisation
    app.register_blueprint(agent)  # POST — local capture agent only

    # ── Serve frontend ────────────────────────────────────────────
    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app
