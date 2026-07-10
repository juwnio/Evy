import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONNECTIONS_PATH = _PROJECT_ROOT / "credentials" / "emails.json"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993


def _ensure_file() -> None:
    CONNECTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONNECTIONS_PATH.exists():
        CONNECTIONS_PATH.write_text("[]")


def _load_connections() -> list[dict]:
    _ensure_file()
    try:
        return json.loads(CONNECTIONS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_connections(conns: list[dict]) -> None:
    _ensure_file()
    CONNECTIONS_PATH.write_text(json.dumps(conns, indent=2))


def add_connection(email: str, app_password: str, description: str) -> dict:
    conns = _load_connections()
    conn = {
        "id": "eml_" + uuid.uuid4().hex[:12],
        "email": email,
        "app_password": app_password,
        "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    conns.append(conn)
    _save_connections(conns)
    return conn


def list_connections() -> list[dict]:
    conns = _load_connections()
    return [
        {
            "id": c["id"],
            "email": c["email"],
            "description": c["description"],
            "created_at": c["created_at"],
        }
        for c in conns
    ]


def get_connection(connection_id: str | None = None) -> tuple[dict | None, str | None]:
    conns = _load_connections()
    if not conns:
        return None, "No email connections configured. Use Ctrl+E to add one."
    if connection_id:
        for c in conns:
            if c["id"] == connection_id:
                return {"email": c["email"], "app_password": c["app_password"]}, None
        return None, f"No email connection found with id '{connection_id}'. Available: {[c['id'] for c in conns]}"
    if len(conns) == 1:
        return {"email": conns[0]["email"], "app_password": conns[0]["app_password"]}, None
    return None, f"Multiple email connections available. Specify a connection_id. Available: {[{'id': c['id'], 'description': c['description']} for c in conns]}"
