"""
Flask application factory.

Usage:
    uv run flask --app app.api run --debug
  or via run_server.py:
    uv run run_server.py
"""

from pathlib import Path

from flask import Flask, render_template, send_from_directory

from app.api.routes import agent, dashboard
from app.api.routes.sentinel import sentinel_bp
from app.services import ml_service

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(STATIC_DIR),
        template_folder=str(FRONTEND_DIR),
    )

    # ── Blueprints ────────────────────────────────────────────────
    app.register_blueprint(dashboard)  # GET  — frontend visualisation
    app.register_blueprint(agent)  # POST — local capture agent only
    app.register_blueprint(sentinel_bp)  # GET  — sentinel DB viewer
    ml_service.load_model()

    # ── Serve frontend ────────────────────────────────────────────
    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/sentinel")
    def sentinel():
        return render_template("sentinel.html")

    return app
