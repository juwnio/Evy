import json
from datetime import datetime

import ollama

from utilities.manipulation import load_config, load_consolidation_context


# Call Model for consolidation
def consolidate(memory):

    # Load configuration
    config = load_config()
    model = config["model"]

    # Load system context
    system_context = load_consolidation_context()

    response = ollama.chat(
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
        options={"num_predict": config.get("max_output_tokens", 512)},
    )

    ## Get memory and consolidate it
    # Append response to memory-brain.json
    brain_path = "memory/brain.json"

    # Create new entry
    new_memory = {
        "timestamp": datetime.now().isoformat(),
        "compressed-memory": response["message"]["content"],
    }

    # Overwrite the file with only the new entry (wrapped in list for consistency)
    with open(brain_path, "w", encoding="utf-8") as f:
        json.dump([new_memory], f, indent=2)

    return response["message"]["content"]
