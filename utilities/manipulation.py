import json
import os
import textwrap

from dotenv import load_dotenv
from ollama import Client

load_dotenv()


def _fmt(key: str, value, width: int = 80) -> str:
    """Format a key-value pair, indenting nested dicts/lists."""
    if isinstance(value, dict):
        body = json.dumps(value, indent=2).replace("\n", "\n    ")
        return f"{key}:\n    {body}"
    if isinstance(value, list):
        # String-only arrays: format as indented paragraphs
        if all(isinstance(v, str) for v in value):
            lines = []
            for p in value:
                wrapped = textwrap.fill(p, width=width)
                for line in wrapped.split("\n"):
                    lines.append("    " + line)
            return f"{key}:\n" + "\n".join(lines)
        # Mixed/non-string lists: JSON pretty-print
        body = json.dumps(value, indent=2).replace("\n", "\n    ")
        return f"{key}:\n    {body}"
    # String value: split on \n for backward compat
    paragraphs = value.split("\n")
    lines = []
    for p in paragraphs:
        filled = textwrap.fill(p.strip(), width=width)
        for line in filled.split("\n"):
            lines.append("    " + line)
    return f"{key}:\n" + "\n".join(lines)


# Load system context from system-context.json
def load_system_context():
    with open("memory/system-context.json", "r") as f:
        system_context = json.load(f)

    return "\n".join(_fmt(k, v) for k, v in system_context.items())


# Load skills context from skills-context.json, injecting values from config
def load_skills_context():
    with open("memory/skills-context.json", "r") as f:
        raw = f.read()

    with open("config.json", "r") as f:
        config = json.load(f)

    raw = raw.replace("{max_tools_per_load}", str(config.get("max_tools_per_load", 5)))

    skills_context = json.loads(raw)
    return "\n".join(_fmt(k, v) for k, v in skills_context.items())


# Load consolidation context from consolidation-context.json
def load_consolidation_context():
    with open("memory/system/consolidation-context.json", "r") as f:
        consolidation_context = json.load(f)

    return "\n".join(_fmt(k, v) for k, v in consolidation_context.items())


# Load configuration from config.json
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)


def load_memory(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        # backup the broken file and re-create
        os.rename(path, path + ".broken")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
        return default


def resolve_model_config(config):
    if config.get("local", True):
        return Client(), config["model"]
    api_key = os.environ.get("ollama-api-key") or config.get("ollama-api-key", "")
    if not api_key:
        raise ValueError(
            "Cloud model selected but no API key found. "
            "Set ollama-api-key in your .env file or config.json."
        )
    return Client(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"},
    ), config.get("cloud-model", config["model"])
