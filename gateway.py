import importlib
import inspect
import json
import os
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from ollama._types import ResponseError

from utilities.scripts.consolidation import PRESERVE_COUNT, consolidate_conversation, consolidate_episodic, _serialize_conversation
from utilities.scripts.conversion import consolidate_context, count_tokens
from utilities.scripts.manipulation import (
    Client,
    _LLM_TIMEOUT,
    load_config,
    load_memory,
    load_skills_context,
    load_system_context,
    resolve_model_config,
)


SKILLS_DIR = Path("skills")
BRAIN_PATH = Path("memory/dynamic/brain.json")
EPISODIC_PATH = Path("memory/dynamic/episodic-memory.json")
ACTIONS_LOG_PATH = Path("memory/dynamic/logs/actions-log.json")
HEARTBEAT_LOG_PATH = Path("memory/dynamic/logs/heartbeat-log.json")
MAX_RETRIES = 3

for _p in (BRAIN_PATH.parent, ACTIONS_LOG_PATH.parent, HEARTBEAT_LOG_PATH.parent):
    _p.mkdir(parents=True, exist_ok=True)

_permission_handler = None  # set by TUI on startup
_email_connections_context = ""  # set by TUI when email connections change
_cancelled = threading.Event()  # set by TUI when user cancels mid-turn
_active_key = "main"  # tracks which API key is in use for cell swapping


def cancel_pending() -> None:
    _cancelled.set()


def _get_active_key() -> str:
    return _active_key


def _build_client_for_key(key_name: str) -> Client:
    config = load_config()
    if config.get("local", True):
        return Client(timeout=_LLM_TIMEOUT)
    if key_name == "preconscious":
        api_key = os.environ.get("preconscious-key", "")
    else:
        api_key = os.environ.get("ollama-api-key", "") or config.get("ollama-api-key", "")
    if not api_key:
        raise ValueError(f"No API key available for '{key_name}'")
    return Client(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_LLM_TIMEOUT,
    )


def _is_rate_limited(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg

TEMP_SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "evy_screenshots"
SCREENSHOT_MAX_AGE = 300  # 5 minutes


def _cleanup_temp_screenshots() -> None:
    """Remove temp screenshots older than SCREENSHOT_MAX_AGE seconds."""
    if not TEMP_SCREENSHOT_DIR.exists():
        return
    now = time.time()
    for f in TEMP_SCREENSHOT_DIR.iterdir():
        try:
            if now - f.stat().st_mtime > SCREENSHOT_MAX_AGE:
                f.unlink(missing_ok=True)
        except OSError:
            pass


def _save_brain_entry(entry: dict) -> None:
    try:
        with open(BRAIN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []
    data.append(entry)
    with open(BRAIN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_tools():
    with open(SKILLS_DIR / "primary-skills.json") as f:
        schemas = json.load(f)
    mod = importlib.import_module(f"{SKILLS_DIR.name}.primary")
    functions = {}
    for tool in schemas:
        name = tool["function"]["name"]
        fn = getattr(mod, name, None)
        if fn:
            functions[name] = fn
    return schemas, functions


def _log_tool_call(entry: dict) -> None:
    path = ACTIONS_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "r", encoding="utf-8") as f:
            log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log = []
    log.append(entry)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
    tmp.replace(path)



def _log_heartbeat_entry(entry: dict) -> None:
    path = HEARTBEAT_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "r", encoding="utf-8") as f:
            log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log = []
    log.append(entry)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
    tmp.replace(path)


def _check_permission(tool_name: str, tool_args: dict | None = None) -> bool:
    try:
        with open("utilities/permissions-check.json") as f:
            rules = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return True

    check = rules.get(tool_name)
    if check is None:
        return True
    if not check:
        return False
    if _permission_handler is not None:
        return _permission_handler(tool_name, tool_args)
    return True


def call_evy_stream(prompt: str, images: list[str] | None = None, voice_mode: bool = False):
    # Clear actions log for this prompt
    with open(ACTIONS_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump([], f)

    _cleanup_temp_screenshots()

    global _active_key
    _active_key = "main"

    config = load_config()
    try:
        client = _build_client_for_key(_active_key)
        model = config.get("cloud-model", config["model"]) if not config.get("local", True) else config["model"]
    except ValueError as e:
        yield {"type": "final", "text": str(e)}
        return

    # ── Calculate token limits from percentages ──────────────────────────
    pct = config.get("limits_pct", {})
    total_pct = sum(pct.values())
    if total_pct > 100:
        yield {"type": "warning", "text": f"[#888]Warning: configured limits_pct sum ({total_pct}) exceeds 100%. Reduce percentages in utilities/config.json.[/#888]"}
        return
    window = config["context_window"]
    max_static_tokens = int(window * pct.get("static", 0) / 100)
    max_conversation_tokens = int(window * pct.get("conversation", 0) / 100)
    max_episodic_tokens = int(window * pct.get("episodic", 0) / 100)
    max_output_tokens = int(window * pct.get("output", 0) / 100)
    preserve_count = config.get("preserve_count", PRESERVE_COUNT)

    system_context = load_system_context()
    skills_context = load_skills_context()
    if _email_connections_context:
        skills_context += "\n\n" + _email_connections_context

    # Load both conversation memory and episodic (memorised) memory
    memory = load_memory(str(BRAIN_PATH), [])
    episodic = load_memory(str(EPISODIC_PATH), [])

    # Check if conversation history needs consolidation
    if count_tokens(json.dumps(memory)) > max_conversation_tokens:
        yield {"type": "consolidating", "target": "conversation"}
        memory = consolidate_conversation(memory, max_output_tokens, preserve_count)

    # Check if episodic memory needs consolidation
    if count_tokens(json.dumps(episodic)) > max_episodic_tokens:
        yield {"type": "consolidating", "target": "episodic"}
        episodic = consolidate_episodic(episodic, max_output_tokens)

    primary_schemas, primary_functions = load_tools()
    loaded_schemas = []
    loaded_functions = {}

    combined_static = consolidate_context(
        system_context, skills_context, primary_schemas
    )

    token_count = count_tokens(combined_static)
    if token_count > max_static_tokens:
        yield {"type": "warning", "text": f"[#888]Warning: static context ({token_count}) exceeds max static tokens ({max_static_tokens}). Reduce skills or increase 'static' percentage in limits_pct.[/#888]"}
        return

    # Parse memory: extract compaction summary + raw exchanges
    # Strip images from past turns — they are not re-sent to the model
    compaction_summary = None
    raw_exchanges = []
    for entry in memory:
        entry.pop("images", None)
        if entry.get("type") == "compaction":
            compaction_summary = entry.get("summary", "")
        else:
            raw_exchanges.append(entry)

    messages = [
        {"role": "system", "content": system_context},
    ]

    if compaction_summary:
        messages.append(
            {"role": "system", "content": f"## Conversation Summary\n\n{compaction_summary}"}
        )

    if raw_exchanges:
        serialized = _serialize_conversation(raw_exchanges)
        messages.append(
            {"role": "system", "content": f"## Recent Conversation\n\n{serialized}"}
        )

    user_msg: dict = {"role": "user", "content": prompt}
    if images:
        resolved = []
        for img in images:
            p = Path(img)
            if p.exists():
                resolved.append(str(p.resolve()))
        if resolved:
            user_msg["images"] = resolved
    messages.extend([
        {"role": "system", "content": f"Memorised facts: {episodic}"},
        user_msg,
        {"role": "system", "content": skills_context},
    ])

    if voice_mode:
        messages.append({
            "role": "system",
            "content": (
                "VOICE MODE ACTIVE \u2014 The user is listening to your responses as spoken audio. "
                "Reply in short, natural, conversational sentences. Do NOT use tables, bullet "
                "lists, code blocks, or any formatted data representation. Explain data and "
                "information verbally in plain spoken English. Keep responses brief and "
                "conversational \u2014 as if you're talking to someone, not writing to them."
            ),
        })

    # Temporary thinking: force thinking on for one turn after an error,
    # but only if config thinking is off — restores after that turn.
    force_thinking = False

    # Track tool calls executed during this turn
    turn_actions = []
    saved = False
    _cancelled.clear()
    try:
        while True:
            effective_thinking = config["thinking"] or force_thinking
            tools = [
                {**s, "function": {k: v for k, v in s["function"].items() if k not in ("tag", "module")}}
                for s in primary_schemas + loaded_schemas
            ]

            for attempt in range(MAX_RETRIES):
                try:
                    chat_kwargs = dict(
                        model=model,
                        messages=messages,
                        tools=tools,
                        options={"num_predict": max_output_tokens},
                    )
                    if effective_thinking:
                        chat_kwargs["think"] = True

                    if config.get("stream_thinking"):
                        content_fragments = []
                        thinking_fragments = []
                        tool_calls = None
                        response = None
                        stream = client.chat(**chat_kwargs, stream=True)
                        for chunk in stream:
                            response = chunk
                            if chunk.message.thinking:
                                thinking_fragments.append(chunk.message.thinking)
                                yield {"type": "thinking_chunk", "text": chunk.message.thinking}
                            if chunk.message.content:
                                content_fragments.append(chunk.message.content)
                            if chunk.message.tool_calls:
                                tool_calls = chunk.message.tool_calls
                        if response is None:
                            yield {"type": "final", "text": "No response from model"}
                            saved = True
                            return
                        if thinking_fragments:
                            yield {"type": "thinking_flush"}
                        response.message.content = "".join(content_fragments) or None
                        response.message.thinking = "".join(thinking_fragments) or None
                        response.message.tool_calls = tool_calls
                    else:
                        yield {"type": "thinking_spinner", "state": "start"}
                        response = client.chat(**chat_kwargs)
                        yield {"type": "thinking_spinner", "state": "stop"}
                    break
                except ResponseError as e:
                    if "does not support thinking" in str(e):
                        effective_thinking = False
                        continue
                    if _is_rate_limited(e) and attempt < MAX_RETRIES - 1:
                        _active_key = "preconscious" if _active_key == "main" else "main"
                        try:
                            client = _build_client_for_key(_active_key)
                        except ValueError:
                            pass
                        yield {"type": "cell_swap", "key": _active_key}
                        continue
                    if attempt < MAX_RETRIES - 1:
                        yield {"type": "retry", "attempt": attempt + 2}
                        time.sleep(1)
                    else:
                        raise

            # Reset after use — forced thinking only lasts one turn
            force_thinking = False

            messages.append(response.message)

            if response.message.tool_calls:
                for tc in response.message.tool_calls:
                    frames_list_name = "memorising" if tc.function.name == "memorise" else "acting"

                    # ── Permission check ─────────────────────────────────────────
                    always_allowed = {"memorise", "reconsolidation", "search_skills", "load_skills"}
                    if tc.function.name not in always_allowed and not _check_permission(
                        tc.function.name, dict(tc.function.arguments)
                    ):
                        result = "User did not allow you to execute this tool."
                        force_thinking = not config["thinking"]
                        turn_actions.append(
                            {
                                "tool-name": tc.function.name,
                                "arguments": dict(tc.function.arguments),
                                "results": result,
                                "success": False,
                            }
                        )
                        _log_tool_call(
                            {
                                "tool_name": tc.function.name,
                                "arguments": tc.function.arguments,
                                "result": result,
                                "status": "denied",
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_name": tc.function.name,
                                "content": result,
                            }
                        )
                        continue

                    # Yield tool-start event with icon
                    if tc.function.name == "load_skills":
                        yield {"type": "tool_start", "name": "load_skills", "kind": "load_skills", "args": dict(tc.function.arguments)}
                    elif tc.function.name == "search_skills":
                        yield {"type": "tool_start", "name": "search_skills", "kind": "search_skills", "args": dict(tc.function.arguments)}
                    else:
                        yield {"type": "tool_start", "name": tc.function.name, "kind": "tool", "args": dict(tc.function.arguments)}

                    _tool_status = "success"
                    yield {"type": "tool_spinner", "name": tc.function.name, "state": "start", "kind": frames_list_name}
                    try:
                        # ── Defensive guard ──────────────────────────────────────
                        # Model called load_skills with 'tag' instead of 'names'
                        if (
                            tc.function.name == "load_skills"
                            and "tag" in tc.function.arguments
                        ):
                            result = (
                                "Defensive guard: load_skills only accepts 'names', not 'tag'. "
                                "Call search_skills with the tag first, then pass the returned "
                                "tool names to load_skills."
                            )
                            _tool_status = "defensive_guard"
                            force_thinking = not config["thinking"]
                            turn_actions.append(
                                {
                                    "tool-name": tc.function.name,
                                    "arguments": dict(tc.function.arguments),
                                    "results": result,
                                    "success": False,
                                }
                            )
                            _log_tool_call(
                                {
                                    "tool_name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                    "result": result,
                                    "status": "defensive_guard",
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )

                        # ── load_skills (correct args) ───────────────────────────
                        elif tc.function.name == "load_skills":
                            loaded_schemas.clear()
                            loaded_functions.clear()
                            new_schemas = primary_functions["load_skills"](
                                **tc.function.arguments
                            )
                            for s in new_schemas:
                                mod = importlib.import_module(s["function"]["module"])
                                loaded_functions[s["function"]["name"]] = getattr(
                                    mod, s["function"]["name"]
                                )
                            loaded_schemas.extend(new_schemas)
                            result = f"Loaded {len(new_schemas)} tool(s): {[s['function']['name'] for s in new_schemas]}"
                            _tool_status = "success"
                            turn_actions.append(
                                {
                                    "tool-name": tc.function.name,
                                    "arguments": dict(tc.function.arguments),
                                    "results": result,
                                    "success": True,
                                }
                            )
                            _log_tool_call(
                                {
                                    "tool_name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                    "result": result,
                                    "status": "success",
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )

                        # ── All other tools ──────────────────────────────────────
                        else:
                            fn = primary_functions.get(
                                tc.function.name
                            ) or loaded_functions.get(tc.function.name)
                            if fn:
                                if _cancelled.is_set():
                                    result = "Cancelled by user."
                                    _tool_status = "cancelled"
                                    _log_tool_call(
                                        {
                                            "tool_name": tc.function.name,
                                            "arguments": tc.function.arguments,
                                            "result": result,
                                            "status": "cancelled",
                                            "timestamp": datetime.now().isoformat(),
                                        }
                                    )
                                else:
                                    try:
                                        tool_args = dict(tc.function.arguments)
                                        if "_cancel_event" in inspect.signature(fn).parameters:
                                            tool_args["_cancel_event"] = _cancelled
                                        result = fn(**tool_args)
                                        _tool_status = "success"
                                        turn_actions.append(
                                            {
                                                "tool-name": tc.function.name,
                                                "arguments": dict(tc.function.arguments),
                                                "results": result,
                                                "success": True,
                                            }
                                        )
                                        _log_tool_call(
                                            {
                                                "tool_name": tc.function.name,
                                                "arguments": tc.function.arguments,
                                                "result": result,
                                                "status": "success",
                                                "timestamp": datetime.now().isoformat(),
                                            }
                                        )
                                    except Exception as e:
                                        # ── Exception guard ─────────────────────────
                                        # Error goes back to model — it decides whether
                                        # to self-correct or surface it to the user
                                        result = f"Tool error ({tc.function.name}): {e}"
                                        _tool_status = "error"
                                        force_thinking = not config["thinking"]
                                        turn_actions.append(
                                            {
                                                "tool-name": tc.function.name,
                                                "arguments": dict(tc.function.arguments),
                                                "results": result,
                                                "success": False,
                                            }
                                        )
                                        _log_tool_call(
                                            {
                                                "tool_name": tc.function.name,
                                                "arguments": tc.function.arguments,
                                                "result": str(e),
                                                "status": "error",
                                                "timestamp": datetime.now().isoformat(),
                                            }
                                        )
                            else:
                                result = (
                                    f"Tool '{tc.function.name}' is not loaded. "
                                    "You must call search_skills(tag=...) to find available tools, "
                                    "then call load_skills(names=[...]) to load them before they can be used. "
                                    "Primary tools (search_skills, load_skills, grep, etc.) are always available."
                                )
                                _tool_status = "unknown"
                                force_thinking = not config["thinking"]
                                turn_actions.append(
                                    {
                                        "tool-name": tc.function.name,
                                        "arguments": dict(tc.function.arguments),
                                        "results": result,
                                        "success": False,
                                    }
                                )
                                _log_tool_call(
                                    {
                                        "tool_name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                        "result": result,
                                        "status": "unknown",
                                        "timestamp": datetime.now().isoformat(),
                                    }
                                )
                    finally:
                        yield {"type": "tool_spinner", "name": tc.function.name, "state": "stop", "kind": frames_list_name}
                        yield {"type": "tool_result", "name": tc.function.name, "args": dict(tc.function.arguments), "result": str(result), "status": _tool_status}

                    result_str = str(result)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": tc.function.name,
                            "content": result_str,
                        }
                    )

                    # ── Image injection ────────────────────────────────────────
                    # If a tool result starts with IMAGE:, extract the path and
                    # inject it into the next model call so the model can see it.
                    if result_str.startswith("IMAGE:"):
                        img_line = result_str.split("\n")[0]
                        img_path = img_line[len("IMAGE:"):].strip()
                        if os.path.exists(img_path):
                            messages.append({
                                "role": "system",
                                "content": "The following screenshot was captured for processing.",
                                "images": [img_path],
                            })

                # Yield live brain occupation after each tool-call turn
                try:
                    _past = json.loads(BRAIN_PATH.read_text())
                except (FileNotFoundError, json.JSONDecodeError):
                    _past = []
                _current = {
                    "prompt": prompt,
                    "actions": turn_actions,
                    "response": response.message.content,
                }
                _cc = sum(len(json.dumps(e)) for e in _past + [_current])
                _tc = count_tokens(json.dumps(_past + [_current]))
                yield {"type": "brain_update", "char_count": _cc, "token_count": _tc}

                if _cancelled.is_set():
                    saved = True
                    yield {"type": "final", "text": "Cancelled."}
                    return

            else:
                _save_brain_entry(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "prompt": prompt,
                        "images": images or [],
                        "actions": turn_actions,
                        "response": response.message.content,
                    }
                )
                saved = True
                yield {"type": "final", "text": response.message.content}
                return

    finally:
        if not saved:
            entry: dict = {
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt,
                "actions": turn_actions,
                "response": None,
            }
            if images:
                entry["images"] = images
            _save_brain_entry(entry)


def call_evy(prompt, images=None):
    """Synchronous wrapper around call_evy_stream — returns final text only."""
    for event in call_evy_stream(prompt, images=images):
        if event["type"] == "final":
            return event["text"]


def execute_heartbeat(prompt: str) -> tuple[str, str]:
    """Execute a heartbeat prompt using the preconscious API key.

    Returns (final_text, status) where status is 'success' or 'fail'.
    """
    config = load_config()
    api_key = os.environ.get("preconscious-key")
    if not api_key:
        return "preconscious-key not found in environment", "fail"
    try:
        model = config.get("preconscious-model") or config.get("cloud-model") or "llama3"
        client = Client(
            host="https://ollama.com",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_LLM_TIMEOUT,
        )
    except Exception as e:
        return f"Failed to create heartbeat client: {e}", "fail"

    system_context = load_system_context()
    skills_context = load_skills_context()
    if _email_connections_context:
        skills_context += "\n\n" + _email_connections_context
    primary_schemas, primary_functions = load_tools()
    loaded_schemas: list[dict] = []
    loaded_functions: dict = {}

    # Include episodic memory so heartbeat knows facts (email, name, etc.)
    episodic = load_memory(str(EPISODIC_PATH), [])

    combined_static = consolidate_context(system_context, skills_context, primary_schemas)
    pct = config.get("limits_pct", {})
    window = config["context_window"]
    max_static_tokens = int(window * pct.get("static", 0) / 100)
    static_tokens = count_tokens(combined_static)
    if static_tokens > max_static_tokens:
        ratio = max_static_tokens / static_tokens
        cutoff = int(len(combined_static) * ratio)
        combined_static = combined_static[:cutoff]
        combined_static += f"\n[truncated: static context was {static_tokens} tokens, truncated to {max_static_tokens}]"

    messages = [
        {"role": "system", "content": combined_static},
    ]
    if episodic:
        messages.append({"role": "system", "content": f"Memorised facts: {episodic}"})
    messages.append({"role": "user", "content": prompt})

    tools = [
        {**s, "function": {k: v for k, v in s["function"].items() if k not in ("tag", "module")}}
        for s in primary_schemas
    ]
    max_output_tokens = int(window * pct.get("output", 0) / 100)

    tool_calls_made: list[dict] = []

    try:
        response = client.chat(
            model=model,
            messages=messages,
            tools=tools,
            options={"num_predict": max_output_tokens},
        )
    except ResponseError as e:
        if _is_rate_limited(e):
            fallback_key = os.environ.get("ollama-api-key", "")
            if fallback_key:
                client = Client(
                    host="https://ollama.com",
                    headers={"Authorization": f"Bearer {fallback_key}"},
                    timeout=_LLM_TIMEOUT,
                )
                try:
                    response = client.chat(
                        model=model,
                        messages=messages,
                        tools=tools,
                        options={"num_predict": max_output_tokens},
                    )
                except Exception as e2:
                    _log_heartbeat_entry({"prompt": prompt, "status": "fail", "error": f"Heartbeat model call failed after swap: {e2}", "tool_calls": tool_calls_made, "timestamp": datetime.now().isoformat()})
                    return f"Heartbeat model call failed after swap: {e2}", "fail"
            else:
                _log_heartbeat_entry({"prompt": prompt, "status": "fail", "error": f"Heartbeat model call failed: {e}", "tool_calls": tool_calls_made, "timestamp": datetime.now().isoformat()})
                return f"Heartbeat model call failed: {e}", "fail"
        else:
            _log_heartbeat_entry({"prompt": prompt, "status": "fail", "error": f"Heartbeat model call failed: {e}", "tool_calls": tool_calls_made, "timestamp": datetime.now().isoformat()})
            return f"Heartbeat model call failed: {e}", "fail"
    except Exception as e:
        _log_heartbeat_entry({"prompt": prompt, "status": "fail", "error": f"Heartbeat model call failed: {e}", "tool_calls": tool_calls_made, "timestamp": datetime.now().isoformat()})
        return f"Heartbeat model call failed: {e}", "fail"

    for _ in range(20):
        if not response.message.tool_calls:
            break
        for tc in response.message.tool_calls:
            if tc.function.name == "load_skills":
                loaded_schemas.clear()
                loaded_functions.clear()
                try:
                    new_schemas = primary_functions["load_skills"](**tc.function.arguments)
                    for s in new_schemas:
                        mod = importlib.import_module(s["function"]["module"])
                        loaded_functions[s["function"]["name"]] = getattr(mod, s["function"]["name"])
                    loaded_schemas.extend(new_schemas)
                    result = f"Loaded {len(new_schemas)} tool(s): {[s['function']['name'] for s in new_schemas]}"
                except Exception as e:
                    result = f"Tool error (load_skills): {e}"
            else:
                fn = primary_functions.get(tc.function.name) or loaded_functions.get(tc.function.name)
                if fn:
                    try:
                        result = fn(**tc.function.arguments)
                    except Exception as e:
                        result = f"Tool error ({tc.function.name}): {e}"
                else:
                    result = (
                        f"Tool '{tc.function.name}' is not loaded. "
                        "You must call search_skills(tag=...) to find available tools, "
                        "then call load_skills(names=[...]) to load them before they can be used. "
                        "Primary tools (search_skills, load_skills, grep, etc.) are always available."
                    )
            tool_calls_made.append({"tool": tc.function.name, "arguments": dict(tc.function.arguments), "result": str(result)})
            messages.append({"role": "tool", "tool_name": tc.function.name, "content": str(result)})
        tools = [
            {**s, "function": {k: v for k, v in s["function"].items() if k not in ("tag", "module")}}
            for s in primary_schemas + loaded_schemas
        ]
        try:
            response = client.chat(
                model=model,
                messages=messages,
                tools=tools,
                options={"num_predict": max_output_tokens},
            )
        except ResponseError as e:
            if _is_rate_limited(e):
                fallback_key = os.environ.get("ollama-api-key", "")
                if fallback_key:
                    client = Client(
                        host="https://ollama.com",
                        headers={"Authorization": f"Bearer {fallback_key}"},
                        timeout=_LLM_TIMEOUT,
                    )
                    try:
                        response = client.chat(
                            model=model,
                            messages=messages,
                            tools=tools,
                            options={"num_predict": max_output_tokens},
                        )
                    except Exception as e2:
                        _log_heartbeat_entry({"prompt": prompt, "status": "fail", "error": f"Heartbeat tool loop failed after swap: {e2}", "tool_calls": tool_calls_made, "timestamp": datetime.now().isoformat()})
                        return f"Heartbeat model call failed during tool loop after swap: {e2}", "fail"
                else:
                    _log_heartbeat_entry({"prompt": prompt, "status": "fail", "error": f"Heartbeat tool loop failed: {e}", "tool_calls": tool_calls_made, "timestamp": datetime.now().isoformat()})
                    return f"Heartbeat model call failed during tool loop: {e}", "fail"
            else:
                _log_heartbeat_entry({"prompt": prompt, "status": "fail", "error": f"Heartbeat tool loop failed: {e}", "tool_calls": tool_calls_made, "timestamp": datetime.now().isoformat()})
                return f"Heartbeat model call failed during tool loop: {e}", "fail"
        except Exception as e:
            _log_heartbeat_entry({"prompt": prompt, "status": "fail", "error": f"Heartbeat tool loop failed: {e}", "tool_calls": tool_calls_made, "timestamp": datetime.now().isoformat()})
            return f"Heartbeat model call failed during tool loop: {e}", "fail"

    final_text = response.message.content or ""
    _log_heartbeat_entry({"prompt": prompt, "status": "success", "final_text": final_text, "tool_calls": tool_calls_made, "timestamp": datetime.now().isoformat()})
    return final_text, "success"
