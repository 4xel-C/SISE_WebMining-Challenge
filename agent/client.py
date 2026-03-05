"""
agent/client.py — HTTP client for the Flask API.

Single responsibility: send requests, surface errors, nothing else.
"""

import sys

import requests

API_BASE = "http://127.0.0.1:5000"


def post(path: str, payload: dict) -> dict | None:
    """POST JSON to the API; returns parsed response or None on error."""
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, timeout=3)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"[agent] POST {path} échoué : {exc}", file=sys.stderr)
        return None


def check_server() -> bool:
    """Return True if the Flask server is reachable."""
    try:
        requests.get(f"{API_BASE}/api/status", timeout=3).raise_for_status()
        return True
    except Exception:
        return False
