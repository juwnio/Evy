import json
import os
import textwrap
from types import SimpleNamespace

import httpx
from dotenv import load_dotenv
from ollama import Client
from openai import OpenAI

load_dotenv()


def _fmt(key: str, value, width: int = 80) -> str:
    """Format a key-value pair, indenting nested dicts/lists."""
    if isinstance(value, dict):
        body = json.dumps(value, indent=2).replace("\n", "\n    ")
        return f"{key}:\n    {body}"
    if isinstance(value, list):
        if all(isinstance(v, str) for v in value):
            lines = []
            for p in value:
                wrapped = textwrap.fill(p, width=width)
                for line in wrapped.split("\n"):
                    lines.append("    " + line)
            return f"{key}:\n" + "\n".join(lines)
        body = json.dumps(value, indent=2).replace("\n", "\n    ")
        return f"{key}:\n    {body}"
    paragraphs = value.split("\n")
    lines = []
    for p in paragraphs:
        filled = textwrap.fill(p.strip(), width=width)
        for line in filled.split("\n"):
            lines.append("    " + line)
    return f"{key}:\n" + "\n".join(lines)


def load_system_context():
    with open("memory/static/system-context.json", "r") as f:
        system_context = json.load(f)
    return "\n".join(_fmt(k, v) for k, v in system_context.items())


def load_skills_context():
    with open("memory/static/skills-context.json", "r") as f:
        raw = f.read()
    with open("utilities/config.json", "r") as f:
        config = json.load(f)
    raw = raw.replace("{max_tools_per_load}", str(config.get("max_tools_per_load", 5)))
    skills_context = json.loads(raw)
    return "\n".join(_fmt(k, v) for k, v in skills_context.items())


def load_consolidation_context():
    with open("memory/static/consolidation-context.json", "r") as f:
        consolidation_context = json.load(f)
    return "\n".join(_fmt(k, v) for k, v in consolidation_context.items())


def load_episodic_consolidation_context():
    with open("memory/static/episodic-consolidation-context.json", "r") as f:
        consolidation_context = json.load(f)
    return "\n".join(_fmt(k, v) for k, v in consolidation_context.items())


def load_config():
    with open("utilities/config.json", "r") as f:
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
        os.rename(path, path + ".broken")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
        return default


_LLM_TIMEOUT = httpx.Timeout(300.0, connect=30.0)


def resolve_model_config(config):
    mode = config.get("model_mode", "local")
    if mode == "collab":
        base_url = (
            os.environ.get("collab-base-url")
            or config.get("collab-base-url", "")
        )
        api_key = (
            os.environ.get("collab-api-key")
            or config.get("collab-api-key", "")
        )
        model = config.get("collab-model", config["model"])
        if not base_url:
            raise ValueError(
                "Collab mode selected but no collab-base-url configured. "
                "Set it in utilities/config.json or your .env file."
            )
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=300)
        return client, model, "openai"

    # local or cloud mode — both use ollama.Client
    if mode == "local":
        return Client(timeout=_LLM_TIMEOUT), config["model"], "ollama"

    # cloud
    api_key = os.environ.get("ollama-api-key") or config.get("ollama-api-key", "")
    if not api_key:
        raise ValueError(
            "Cloud model selected but no API key found. "
            "Set ollama-api-key in your .env file or utilities/config.json."
        )
    return (
        Client(
            host="https://ollama.com",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_LLM_TIMEOUT,
        ),
        config.get("cloud-model", config["model"]),
        "ollama",
    )


# ── Unified model chat wrapper ──────────────────────────────────────────────

def _convert_tools_openai(tools):
    """Convert ollama-format tools list to OpenAI format."""
    if not tools:
        return None
    result = []
    for t in tools:
        func = t.get("function", {})
        result.append({
            "type": "function",
            "function": {
                "name": func["name"],
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
            },
        })
    return result


def _normalize_openai_response(response):
    """Wrap an OpenAI non-streaming response to look like an ollama response."""
    ns = SimpleNamespace()
    msg = response.choices[0].message
    ns.message = SimpleNamespace()
    ns.message.content = msg.content or None
    ns.message.thinking = None
    if msg.tool_calls:
        ns.message.tool_calls = [
            SimpleNamespace(
                id=tc.id,
                function=SimpleNamespace(
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments) if tc.function.arguments else {},
                ),
            )
            for tc in msg.tool_calls
        ]
    else:
        ns.message.tool_calls = None
    return ns


def _normalize_openai_stream(stream):
    """Yield chunks that look like ollama streaming chunks from an OpenAI stream."""
    aggregated_tool_calls = {}
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        finish_reason = chunk.choices[0].finish_reason

        content = getattr(delta, "content", None)
        reasoning = getattr(delta, "reasoning", None)

        # Accumulate partial tool calls
        tool_calls_delta = getattr(delta, "tool_calls", None)
        if tool_calls_delta:
            for tc in tool_calls_delta:
                idx = tc.index
                if idx not in aggregated_tool_calls:
                    aggregated_tool_calls[idx] = {"id": tc.id or "", "name": "", "arguments": ""}
                if tc.function:
                    if tc.function.name:
                        aggregated_tool_calls[idx]["name"] = tc.function.name
                    if tc.function.arguments:
                        aggregated_tool_calls[idx]["arguments"] += tc.function.arguments

        ns = SimpleNamespace()
        ns.message = SimpleNamespace()
        ns.message.content = content
        ns.message.thinking = reasoning
        ns.message.tool_calls = None

        yield ns

    # After stream ends, yield a final chunk with complete tool calls if any
    if aggregated_tool_calls:
        ns = SimpleNamespace()
        ns.message = SimpleNamespace()
        ns.message.content = None
        ns.message.thinking = None
        ns.message.tool_calls = [
            SimpleNamespace(
                id=data["id"],
                function=SimpleNamespace(
                    name=data["name"],
                    arguments=json.loads(data["arguments"]) if data["arguments"] else {},
                ),
            )
            for data in aggregated_tool_calls.values()
        ]
        yield ns


def _model_chat(client, provider, model, messages, tools=None, options=None, stream=False, think=False):
    """Unified chat() that works with both ollama and OpenAI backends.

    Returns a response compatible with ollama.Client.chat() semantics.
    For streaming, returns an iterator of normalized chunks.
    """
    if provider == "ollama":
        kwargs = dict(model=model, messages=messages)
        if tools:
            kwargs["tools"] = tools
        if options:
            kwargs["options"] = options
        if think:
            kwargs["think"] = True
        return client.chat(**kwargs, stream=stream)

    # OpenAI provider
    kwargs = dict(model=model, messages=messages)
    if tools:
        kwargs["tools"] = _convert_tools_openai(tools)
    if options and "num_predict" in options:
        kwargs["max_tokens"] = options["num_predict"]
    if stream:
        kwargs["stream"] = True
        return _normalize_openai_stream(client.chat.completions.create(**kwargs))
    else:
        return _normalize_openai_response(client.chat.completions.create(**kwargs))
