"""Local control panel for Evy.

Serves a single configuration HTML page on 127.0.0.1 and exposes a small JSON
API that reads/writes utilities/config.json and credentials/emails.json — the
same files the TUI uses — so changes apply live while Evy is running.

Usage:
    from web.server import start_server_thread
    start_server_thread(port=8765)

Or standalone:
    python web/server.py
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utilities.scripts import settings
from utilities.scripts.google_auth import (
    add_connection,
    delete_connection,
    list_connections,
)

STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")


def _refresh_email_context() -> None:
    """Rebuild the email snippet the model sees (only relevant when Evy is running)."""
    try:
        import gateway as _gateway_mod

        _gateway_mod._refresh_email_context()
    except Exception:
        pass


# ── Page ────────────────────────────────────────────────────────────────


@app.get("/")
def index():
    try:
        port = int(settings.load_config().get("control_panel_port", 8765))
    except Exception:
        port = 8765
    return send_from_directory(STATIC_DIR, "index.html")


# ── Config ──────────────────────────────────────────────────────────────


@app.get("/api/config")
def api_get_config():
    return jsonify(settings.load_config())


@app.put("/api/config")
def api_put_config():
    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Config must be a JSON object"}), 400
    settings.update_config(payload)
    return jsonify({"ok": True})


@app.put("/api/secrets")
def api_put_secrets():
    payload = request.get_json(force=True) or {}
    if "secrets" in payload:
        payload = payload.get("secrets")
    if not isinstance(payload, dict):
        return jsonify({"error": "Secrets must be a JSON object"}), 400
    settings.update_secrets(payload)
    return jsonify({"ok": True})


@app.post("/api/migrate")
def api_migrate():
    config = settings.migrate_env_to_config()
    secrets = {
        k: (v[:8] + "..." if isinstance(v, str) and len(v) > 8 else v)
        for k, v in (config.get("secrets") or {}).items()
    }
    return jsonify({"ok": True, "secrets": secrets})


# ── Email connections ──────────────────────────────────────────────────


@app.get("/api/emails")
def api_get_emails():
    return jsonify(list_connections())


@app.post("/api/emails")
def api_add_email():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip()
    app_password = (data.get("app_password") or "").strip()
    description = (data.get("description") or "").strip()
    if not email or not app_password or not description:
        return jsonify({"error": "Email, app password and description are all required."}), 400
    conn = add_connection(email, app_password, description)
    _refresh_email_context()
    return jsonify(conn)


@app.delete("/api/emails/<email_id>")
def api_delete_email(email_id):
    removed = delete_connection(email_id)
    if removed is None:
        return jsonify({"error": f"No email connection with id '{email_id}'"}), 404
    _refresh_email_context()
    return jsonify(removed)


# ── Lifecycle ──────────────────────────────────────────────────────────


def start_server_thread(port: int = 8765, host: str = "127.0.0.1"):
    """Run the Flask app on a daemon thread. Returns the server object."""
    from werkzeug.serving import make_server

    server = make_server(host, port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    try:
        port = int(settings.load_config().get("control_panel_port", 8765))
    except Exception:
        port = 8765
    print(f"Evy control panel: http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)