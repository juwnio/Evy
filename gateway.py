import importlib
import json
from datetime import datetime
from pathlib import Path

import ollama
from rich.console import Console

from utilities.consolidation import consolidate
from utilities.conversion import consolidate_context, count_tokens
from utilities.manipulation import (
    load_config,
    load_memory,
    load_skills_context,
    load_system_context,
)
from utilities.states import acting, memorising, show_state, thinking_animation

SKILLS_DIR = Path("skills")
BRAIN_PATH = Path("memory/brain.json")
ACTIONS_LOG_PATH = Path("memory/system/actions-log.json")

console = Console()


def _log_action(text: str) -> None:
    with open(BRAIN_PATH, "r", encoding="utf-8") as f:
        memory = json.load(f)
    memory.append({"timestamp": datetime.now().isoformat(), "actions": text})
    with open(BRAIN_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)


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
    with open(ACTIONS_LOG_PATH, "r", encoding="utf-8") as f:
        log = json.load(f)
    log.append(entry)
    with open(ACTIONS_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def call_evy(prompt):
    # Clear actions log for this prompt
    with open(ACTIONS_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump([], f)

    config = load_config()
    model = config["model"]
    system_context = load_system_context()
    skills_context = load_skills_context()
    memory = load_memory(str(BRAIN_PATH), [])

    ## Check if memory is eligible for consolidation
    token_count = count_tokens(json.dumps(memory))
    if token_count > config["max_memory_tokens"]:
        memory = consolidate(memory)

    primary_schemas, primary_functions = load_tools()
    loaded_schemas = []
    loaded_functions = {}

    combined_static = consolidate_context(
        system_context, skills_context, primary_schemas
    )

    token_count = count_tokens(combined_static)
    max_static_tokens = config["max_static_tokens"]

    if token_count > max_static_tokens:
        console.print(
            f"[red]Warning: token count ({token_count}) exceeds max static tokens ({max_static_tokens})[/red]"
        )
        return

    messages = [
        {"role": "system", "content": system_context},
        {"role": "system", "content": f"Memory: {memory}"},
        {"role": "user", "content": prompt},
        {"role": "system", "content": skills_context},
    ]

    # Temporary thinking: force thinking on for one turn after an error,
    # but only if config thinking is off — restores after that turn.
    force_thinking = False

    while True:
        effective_thinking = config["thinking"] or force_thinking

        thinking_animation.start()
        response = ollama.chat(
            model=model,
            messages=messages,
            tools=primary_schemas + loaded_schemas,
            think=effective_thinking,
            options={"num_predict": config["max_output_tokens"]},
        )
        thinking_animation.stop()

        # Reset after use — forced thinking only lasts one turn
        force_thinking = False

        messages.append(response.message)

        if response.message.tool_calls:
            for tc in response.message.tool_calls:
                frames = memorising if tc.function.name == "memorise" else acting

                # Print before spinner
                if tc.function.name == "load_skills":
                    console.print(
                        f"\n[#eb9b34]⊶[/#eb9b34] [dim]Loading {tc.function.arguments.get('names', '?')}...[/dim]\n"
                    )
                elif tc.function.name == "search_skills":
                    console.print(
                        f"\n[#eb9b34]⌕[/#eb9b34] [dim]Searching for a '{tc.function.arguments['tag']}' skill[/dim]\n"
                    )
                else:
                    console.print(
                        f"\n[#eb9b34]⧉[/#eb9b34] [dim]Executing tool: {tc.function.name}[/dim]\n"
                    )

                with show_state(frames, color="blue", speed=0.1):
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
                        force_thinking = not config["thinking"]
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
                        _log_action(result)
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
                            try:
                                result = fn(**tc.function.arguments)
                                _log_action(
                                    f"Executed tool: {tc.function.name}, ran successfully"
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
                                force_thinking = not config["thinking"]
                                _log_action(
                                    f"Executed tool: {tc.function.name}, failed: {e}"
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
                            result = f"Unknown tool: {tc.function.name}"
                            force_thinking = not config["thinking"]
                            _log_action(
                                f"Executed tool: {tc.function.name}, failed: unknown tool"
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

                messages.append(
                    {
                        "role": "tool",
                        "tool_name": tc.function.name,
                        "content": str(result),
                    }
                )
        else:
            new_entry = {
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt,
                "response": response.message.content,
            }
            with open(BRAIN_PATH, "r", encoding="utf-8") as f:
                memory_data = json.load(f)
            memory_data.append(new_entry)
            with open(BRAIN_PATH, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, indent=2)
            return response.message.content
