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

WEB_DIR = Path(__file__).resolve().parent
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from utilities.scripts import settings
from utilities.scripts.google_auth import (
    add_connection,
    delete_connection,
    list_connections,
)

import cog  # noqa: E402

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


# ── Setup Q&A ──────────────────────────────────────────────────────────

_ASK_TIMEOUT = 60
_ASK_MAX_QUESTION = 1000
_ASK_MAX_ANSWER = 2000
_ASK_MEMORY = 5


def _history_messages(data: dict) -> list[dict]:
    """Normalise the client's session memory into prior chat turns (last 5 exchanges)."""
    history = data.get("history")
    if not isinstance(history, list):
        return []
    messages: list[dict] = []
    for item in history[-_ASK_MEMORY:]:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        answer = item.get("answer")
        if not isinstance(question, str) or not isinstance(answer, str):
            continue
        question = question.strip()[:_ASK_MAX_QUESTION]
        answer = answer.strip()[:_ASK_MAX_ANSWER]
        if not question or not answer:
            continue
        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": answer})
    return messages


class AskUnavailable(Exception):
    """Raised when Q&A cannot run (missing key, unreachable host)."""


def _ask_client_and_model():
    """Return (client, model) honouring the local/cloud setting."""
    from ollama import Client

    config = settings.load_config()
    if config.get("local", True):
        model = config.get("model") or "llama3.2:latest"
        return Client(timeout=_ASK_TIMEOUT), model

    api_key = settings.get_secret("ollama-api-key", "")
    if not api_key:
        raise AskUnavailable(
            "Add your Ollama API key in the LLM step to ask questions here."
        )
    model = config.get("cloud-model") or config.get("model") or "llama3.2:latest"
    client = Client(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_ASK_TIMEOUT,
    )
    return client, model


def _email_count() -> int:
    try:
        return len(list_connections())
    except Exception:
        return 0


def _build_system_prompt(data: dict) -> str:
    """Build the Cog system prompt from saved config + the client's live draft."""
    config = settings.load_config()
    draft = data.get("draft")
    draft = draft if isinstance(draft, dict) else {}
    step = (data.get("step") or "").strip()
    step_title = (data.get("step_title") or "").strip()
    return cog.build_system_prompt(
        config,
        draft=draft,
        step=step,
        step_title=step_title,
        email_count=_email_count(),
    )


@app.post("/api/ask")
def api_ask():
    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()[:_ASK_MAX_QUESTION]
    if not question:
        return jsonify({"error": "Ask a question first."}), 400

    try:
        client, model = _ask_client_and_model()
    except AskUnavailable as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Could not reach the model: {e}"}), 502

    system = _build_system_prompt(data)

    messages = [{"role": "system", "content": system}]
    messages.extend(_history_messages(data))
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat(
            model=model,
            messages=messages,
        )
    except Exception as e:
        message = str(e)
        if "connect" in message.lower() or "refused" in message.lower():
            return jsonify({
                "error": (
                    "Can't reach local Ollama at 127.0.0.1:11434 — start it, "
                    "or switch to Cloud and add a key."
                )
            }), 502
        return jsonify({"error": f"Could not get an answer: {message}"}), 502

    answer = (getattr(response.message, "content", "") or "").strip()
    return jsonify({"answer": answer or "(no answer)"})


@app.post("/api/ask/preview")
def api_ask_preview():
    """Return the exact system prompt Cog would receive (no secrets, no model call)."""
    data = request.get_json(force=True) or {}
    return jsonify({"prompt": _build_system_prompt(data)})


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
    print(f"Evy control panel: http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)