"""Cog — Evy's setup specialist.

Loads the per-key knowledge base (cog_knowledge.json), renders the user's
current setup state, and composes the system prompt used by the panel's Q&A
endpoint.

The knowledge base is the single place that explains what every config key and
secret does and how its value changes Evy's behaviour. Secret *values* are
never rendered; only whether they are set.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_KNOWLEDGE_PATH = Path(__file__).parent / "cog_knowledge.json"

_FALLBACK_PERSONA = (
    "You are Cog, the resident Evy specialist embedded in her setup panel. "
    "Be bright, brisk, and a little cynical, but always genuinely useful. "
    "Answer in 2-4 sentences, plain text, no emojis. Never reveal or ask for "
    "secret values. If a question is not about Evy or her setup, deflect and "
    "steer back."
)

# Non-secret config keys Cog may read from the saved config or the live draft.
_PUBLIC_KEYS = (
    "local",
    "model",
    "cloud-model",
    "preconscious-model",
    "context_window",
    "limits_pct",
    "preserve_count",
    "max_tools_per_load",
    "browser_headless",
    "thinking",
    "stream_thinking",
    "git_user_name",
    "git_user_email",
    "home_dir",
    "control_panel_port",
    "setup_complete",
)

# Everything under config["secrets"].
_SECRET_KEYS = (
    "ollama-api-key",
    "preconscious-key",
    "discord-token",
    "notion-key",
    "notion-default-page-id",
    "tavily-api-key",
    "obsidian-host",
    "obsidian-api-key",
    "groq-api-key",
    "github-token",
)

_MAX_PROMPT_CHARS = 20000

_cache: dict[str, Any] | None = None


def load_knowledge() -> dict[str, Any]:
    """Load and cache the knowledge base, falling back to a minimal stub."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        data = json.loads(_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
            raise ValueError("malformed knowledge base")
        _cache = data
    except Exception:
        _cache = {"version": 0, "persona": _FALLBACK_PERSONA, "keys": []}
    return _cache


def known_public_keys() -> tuple[str, ...]:
    return _PUBLIC_KEYS


def known_secret_keys() -> tuple[str, ...]:
    return _SECRET_KEYS


def render_knowledge() -> str:
    """Render every knowledge entry as compact plaintext."""
    keys = load_knowledge().get("keys") or []
    lines: list[str] = []
    for entry in keys:
        if not isinstance(entry, dict):
            continue
        name = entry.get("key", "?")
        bits = [f"- {entry.get('label', name)} (`{name}`)"]
        if entry.get("what"):
            bits.append(f"what: {entry['what']}")
        if entry.get("values"):
            bits.append(f"values: {entry['values']}")
        if entry.get("effect"):
            bits.append(f"effect: {entry['effect']}")
        if entry.get("gotcha"):
            bits.append(f"gotcha: {entry['gotcha']}")
        lines.append(" | ".join(bits))
    return "\n".join(lines) if lines else "(no knowledge base available)"


def _clean_scalar(value: Any) -> Any:
    """Keep only simple, non-secret-looking scalar values."""
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value.strip()[:300]
    return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def _merge_value(key: str, draft: dict, config: dict) -> Any:
    """Prefer a sanitised draft value, else the saved config value."""
    draft_val = _clean_scalar(draft.get(key))
    if draft_val not in (None, ""):
        return draft_val
    return _clean_scalar(config.get(key))


def _secret_is_set(name: str, draft_secrets: dict, config_secrets: dict) -> bool:
    if name in draft_secrets:
        value = draft_secrets.get(name)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return bool(value.strip())
    return bool(str(config_secrets.get(name, "")).strip())


def render_secret_state(draft: dict, config: dict) -> list[str]:
    """One 'name: SET/not set' line per known secret. Never values."""
    draft_secrets = draft.get("secrets")
    draft_secrets = draft_secrets if isinstance(draft_secrets, dict) else {}
    config_secrets = config.get("secrets")
    config_secrets = config_secrets if isinstance(config_secrets, dict) else {}
    return [
        f"{name}: {'SET' if _secret_is_set(name, draft_secrets, config_secrets) else 'not set'}"
        for name in _SECRET_KEYS
    ]


def render_state(
    config: dict,
    draft: dict | None = None,
    email_count: int | None = None,
) -> str:
    """Render the current (or unsaved draft) non-secret state."""
    draft = draft if isinstance(draft, dict) else {}

    def value(key: str, default: Any = None) -> Any:
        cleaned = _merge_value(key, draft, config)
        return default if cleaned in (None, "") else cleaned

    raw_local = _merge_value("local", draft, config)
    local = _as_bool(raw_local) if raw_local is not None else bool(config.get("local", True))
    local_model = value("model", "llama3.2:latest")
    cloud_model = value("cloud-model", "—")
    active = local_model if local else cloud_model

    limits = value("limits_pct")
    if not isinstance(limits, dict):
        limits = config.get("limits_pct") if isinstance(config.get("limits_pct"), dict) else {}
    if limits:
        parts = " / ".join(f"{k} {limits.get(k, 0)}%" for k in ("static", "conversation", "episodic", "output"))
        try:
            total = sum(float(limits.get(k, 0) or 0) for k in ("static", "conversation", "episodic", "output"))
            parts += f" (sum {total}%)"
        except (TypeError, ValueError):
            pass
    else:
        parts = "—"

    lines = [
        f"Mode: {'local' if local else 'cloud'} (active model: {active})",
        f"Local model: {local_model}; cloud model: {cloud_model}",
        f"Preconscious model: {value('preconscious-model') or '(blank — falls back to cloud model)'}",
        f"Context window: {value('context_window', '—')} tokens",
        f"Token budget split: {parts}",
        f"Preserve count: {value('preserve_count', '—')}; max tools per load: {value('max_tools_per_load', '—')}",
        f"Browser: {'headless' if _as_bool(value('browser_headless', True)) else 'visible'}; "
        f"Thinking: {'on' if _as_bool(value('thinking', True)) else 'off'}; "
        f"Stream thinking: {'on' if _as_bool(value('stream_thinking', True)) else 'off'}",
        f"Home directory: {value('home_dir', '—')}",
        f"Git identity: {value('git_user_name', '—')} <{value('git_user_email', '—')}>",
        f"Control panel port: {value('control_panel_port', 8765)}",
        f"Setup complete: {'yes' if _as_bool(value('setup_complete', False)) else 'no'}",
    ]

    secret_lines = render_secret_state(draft, config)
    lines.append("Credentials — " + "; ".join(secret_lines))

    email_count = email_count if isinstance(email_count, int) else draft.get("email_count")
    if not isinstance(email_count, int):
        email_count = config.get("_email_count", 0)
    lines.append(f"Email connections: {email_count if isinstance(email_count, int) else 0}")

    return "\n".join(lines)


def _fields_for_step(step: str) -> list[str]:
    if not step:
        return []
    keys = load_knowledge().get("keys") or []
    return [
        str(e.get("label") or e.get("key"))
        for e in keys
        if isinstance(e, dict) and e.get("step") == step
    ]


def build_system_prompt(
    config: dict,
    draft: dict | None = None,
    step: str = "",
    step_title: str = "",
    email_count: int | None = None,
) -> str:
    """Compose the full Cog system prompt."""
    persona = load_knowledge().get("persona") or _FALLBACK_PERSONA

    prompt = (
        persona
        + "\n\n== EVY CONFIGURATION KNOWLEDGE ==\n"
        + "Every key below, what it does, and how its value changes Evy:\n"
        + render_knowledge()
        + "\n\n== CURRENT SETUP STATE ==\n"
        + render_state(config, draft, email_count)
    )

    title = step_title or step
    if title:
        prompt += f"\n\n== CURRENT STEP ==\nThe user is on the '{title}' step."
        fields = _fields_for_step(step)
        if fields:
            prompt += " The fields on this step are: " + ", ".join(fields) + "."

    prompt += (
        "\n\nAnswer using this knowledge and state. Refer to concrete keys when "
        "helpful. Never output secret values. Keep it short and in character."
    )

    if len(prompt) > _MAX_PROMPT_CHARS:
        prompt = prompt[:_MAX_PROMPT_CHARS] + "\n[truncated]"
    return prompt
