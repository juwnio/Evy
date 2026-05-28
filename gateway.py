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


def call_evy(prompt):
    config = load_config()
    model = config["model"]
    system_context = load_system_context()
    skills_context = load_skills_context()
    memory = load_memory(str(BRAIN_PATH), [])

    ## Check if memory is eligable for consolidation
    token_count = count_tokens(json.dumps(memory))
    if token_count > config["max_memory_tokens"]:
        # Memory is too large, consolidate before sending to model
        memory = consolidate(memory)

    tool_schemas, functions = load_tools()

    ## Convert prompt to tokens and count before sending to model
    # Create one sting combination
    combined_static = consolidate_context(system_context, skills_context, tool_schemas)

    # Conversion of combined_static to tokens
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

    while True:
        thinking_animation.start()
        response = ollama.chat(
            model=model,
            messages=messages,
            tools=tool_schemas,
            think=config["thinking"],
            options={"num_predict": config["max_output_tokens"]},
        )
        thinking_animation.stop()
        messages.append(response.message)

        if response.message.tool_calls:
            for tc in response.message.tool_calls:
                frames = memorising if tc.function.name == "memorise" else acting
                with show_state(frames, color="blue", speed=0.1):
                    fn = functions.get(tc.function.name)
                    if fn:
                        try:
                            result = fn(**tc.function.arguments)
                            _log_action(
                                f"Executed tool: {tc.function.name}, ran successfully"
                            )
                        except Exception as e:
                            result = str(e)
                            _log_action(
                                f"Executed tool: {tc.function.name}, failed: {e}"
                            )
                    else:
                        result = f"Unknown tool: {tc.function.name}"
                        _log_action(
                            f"Executed tool: {tc.function.name}, failed: unknown tool"
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
