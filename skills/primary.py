import json
from datetime import datetime

BRAIN_PATH = "memory/brain.json"


def memorise(fact: str) -> str:
    with open(BRAIN_PATH, "r", encoding="utf-8") as f:
        memory = json.load(f)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "memorised-fact": fact,
    }
    memory.append(entry)

    with open(BRAIN_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)

    return f"Memorised: {fact}"
