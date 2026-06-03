import json
from datetime import datetime

from utilities.manipulation import (
    load_config,
    load_consolidation_context,
    load_episodic_consolidation_context,
    resolve_model_config,
)


def consolidate_conversation(memory, max_output_tokens=2048):
    config = load_config()
    client, model = resolve_model_config(config)
    system_context = load_consolidation_context()

    response = client.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_context,
            },
            {
                "role": "user",
                "content": json.dumps(memory, indent=2),
            },
        ],
        think=False,
        options={"num_predict": max_output_tokens},
    )

    compressed = response["message"]["content"]
    with open("memory/brain.json", "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "timestamp": datetime.now().isoformat(),
                    "prompt": None,
                    "actions": [],
                    "response": compressed,
                    "compressed": True,
                }
            ],
            f,
            indent=2,
        )

    return compressed


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

    compressed = response["message"]["content"]
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
