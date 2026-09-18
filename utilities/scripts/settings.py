"""Central settings accessor for Evy.

config.json (utilities/config.json) is the single source of truth for both
runtime settings and secrets. Secrets live under the ``secrets`` object.

Secrets can still be provided via environment/.env as a fallback so existing
installs keep working without a restart, but the recommended path is the
control panel (web/) which writes directly to config.json.
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "utilities" / "config.json"

# Every secret that may be stored in config.json["secrets"]. Keys map to their
# default value when nothing is configured.
SECRET_DEFAULTS = {
    "ollama-api-key": "",
    "preconscious-key": "",
    "discord-token": "",
    "notion-key": "",
    "notion-default-page-id": "",
    "tavily-api-key": "",
    "obsidian-host": "http://127.0.0.1:27123",
    "obsidian-api-key": "",
    "groq-api-key": "",
    "github-token": "",
}


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    tmp = CONFIG_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    tmp.replace(CONFIG_PATH)


def get_secret(name: str, default: str | None = None) -> str | None:
    """Return a secret value from config.json, falling back to the environment.

    Returns the stored env value (when set) under the fallback. A secret that is
    legitimately empty resolves to the env fallback or the supplied default.
    """
    try:
        config = load_config()
    except (FileNotFoundError, json.JSONDecodeError):
        config = {}
    secrets = config.get("secrets") or {}
    if name in secrets and secrets[name] not in (None, ""):
        return secrets[name]
    env_val = os.environ.get(name)
    if env_val:
        return env_val
    return default


def update_secrets(patch: dict) -> None:
    """Merge key/value pairs into config.json["secrets"]."""
    config = load_config()
    secrets = config.setdefault("secrets", {})
    secrets.update(patch)
    save_config(config)


def update_config(patch: dict) -> None:
    """Merge key/value pairs into the top level of config.json.

    Secret keys are redirected into the ``secrets`` object when a caller
    passes them at the top level by mistake.
    """
    config = load_config()
    secrets = config.setdefault("secrets", {})
    for key, value in patch.items():
        if key in SECRET_DEFAULTS:
            secrets[key] = value
        else:
            config[key] = value
    save_config(config)


def masked_config() -> dict:
    """Deep copy of config.json with all secret values truncated for display."""
    config = json.loads(json.dumps(load_config()))
    secrets = config.get("secrets") or {}
    for key, value in secrets.items():
        if isinstance(value, str) and value:
            secrets[key] = value[:8] + "..."
    config["secrets"] = secrets
    return config


def is_first_run() -> bool:
    """True until the user has completed setup via the control panel."""
    try:
        config = load_config()
    except (FileNotFoundError, json.JSONDecodeError):
        return True
    if config.get("setup_complete"):
        return False
    secrets = config.get("secrets") or {}
    return not any(str(v).strip() for v in secrets.values())


def migrate_env_to_config() -> dict:
    """One-time migration of .env / legacy config values into secrets.

    Also moves a legacy top-level ``ollama-api-key`` (from older config.json
    files) into the secrets object. Idempotent — existing secret values are
    never overwritten.
    """
    from dotenv import load_dotenv

    if not CONFIG_PATH.exists():
        return {}
    load_dotenv(dotenv_path=ROOT / ".env")

    try:
        config = load_config()
    except (json.JSONDecodeError, OSError):
        return {}

    secrets = config.setdefault("secrets", {})
    changed = False

    # Legacy top-level key from older config.json files
    if "ollama-api-key" in config:
        legacy_value = config.pop("ollama-api-key") or ""
        if legacy_value:
            secrets.setdefault("ollama-api-key", legacy_value)
        changed = True

    for key, default in SECRET_DEFAULTS.items():
        present = secrets.get(key)
        if present in (None, ""):
            env_value = os.environ.get(key) or default
            if env_value != present:
                secrets[key] = env_value
                changed = True

    if changed:
        save_config(config)
    return config