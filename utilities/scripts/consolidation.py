import json
from datetime import datetime

from utilities.scripts.manipulation import (
    load_config,
    load_consolidation_context,
    load_episodic_consolidation_context,
    resolve_model_config,
)

PRESERVE_COUNT = 5


def _serialize_conversation(entries) -> str:
    """Serialize brain.json entries into flat [User]/[Assistant]/[Tool] text."""
    parts = []
    for entry in entries:
        prompt = entry.get("prompt")
        if prompt:
            parts.append(f"[User]: {prompt}")
        for action in entry.get("actions", []):
            if isinstance(action, str):
                parts.append(f"[Tool results cleared]: {action}")
                continue
            name = action.get("tool-name", "?")
            args = action.get("arguments", {})
            result = action.get("results", "")
            success = action.get("success", False)
            parts.append(f"[Assistant tool call]: {name}({json.dumps(args)})")
            result_str = str(result)
            if len(result_str) > 500:
                result_str = result_str[:500] + "...[truncated]"
            status = "ok" if success else "error"
            parts.append(f"[Tool result ({status})]: {result_str}")
        response = entry.get("response")
        if response:
            parts.append(f"[Assistant]: {response}")
    return "\n".join(parts)


def _build_consolidation_prompt(serialized_head: str, previous_summary: str | None = None) -> str:
    parts = [
        "Summarize the following conversation history into an anchored Markdown summary.",
        "",
        "Conversation history:",
        serialized_head,
        "",
    ]
    if previous_summary:
        parts.append(
            f"Update the anchored summary below using the conversation history above.\n"
            f"Preserve still-true details, remove stale details, and merge in the new facts.\n"
            f"<previous-summary>\n{previous_summary.strip()}\n</previous-summary>"
        )
    else:
        parts.append("Create a new anchored summary from the conversation history.")
    return "\n".join(parts)


def consolidate_conversation(memory, max_output_tokens=2048, preserve_count=PRESERVE_COUNT):
    config = load_config()
    client, model = resolve_model_config(config)
    system_context = load_consolidation_context()

    head = memory[:-preserve_count]
    tail = memory[-preserve_count:]

    previous_summary = None
    head_entries = []
    for entry in head:
        if entry.get("type") == "compaction":
            previous_summary = entry.get("summary")
        else:
            head_entries.append(entry)

    if not head_entries:
        return memory

    serialized_head = _serialize_conversation(head_entries)

    prompt = _build_consolidation_prompt(serialized_head, previous_summary)

    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_context},
            {"role": "user", "content": prompt},
        ],
        think=False,
        options={"num_predict": max_output_tokens},
    )

    compressed = response.message.content

    cleaned_tail = [
        {**entry, "actions": ["cleared for consolidation"]}
        for entry in tail
    ]

    new_memory = [
        {
            "timestamp": datetime.now().isoformat(),
            "type": "compaction",
            "summary": compressed,
        }
    ] + cleaned_tail

    with open("memory/dynamic/brain.json", "w", encoding="utf-8") as f:
        json.dump(new_memory, f, indent=2)

    return new_memory


def consolidate_episodic(episodic, max_output_tokens=2048):
    config = load_config()
    client, model = resolve_model_config(config)
    system_context = load_episodic_consolidation_context()

    response = client.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_context,
            },
            {
                "role": "user",
                "content": json.dumps(episodic, indent=2),
            },
        ],
        think=False,
        options={"num_predict": max_output_tokens},
    )

    compressed = response.message.content
    with open("memory/episodic-memory.json", "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "memory-saved-on": datetime.now().isoformat(),
                    "fact": compressed,
                }
            ],
            f,
            indent=2,
        )

    return compressed
