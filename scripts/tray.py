"""
scripts/tray.py — démarre l'icône systray uniquement (Flask doit déjà tourner).

Usage direct :
    uv run scripts/tray.py

Usage recommandé (tout-en-un) :
    uv run run.py
"""

from agent.ui.tray import TrayApp

if __name__ == "__main__":
    TrayApp().run()
