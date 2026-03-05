"""
scripts/server.py — démarre le serveur Flask (API + frontend).

Usage direct :
    uv run scripts/server.py

Usage recommandé (tout-en-un) :
    uv run run.py
"""

from app.api import create_app

app = create_app()

if __name__ == "__main__":
    # use_reloader=False : le reloader Werkzeug fork un sous-processus qui
    # réinitialise le store in-memory à chaque modification de fichier.
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
