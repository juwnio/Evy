import json
from datetime import datetime
from pathlib import Path

EPISODIC_PATH = "memory/episodic-memory.json"


def memorise(fact: str) -> str:
    with open(EPISODIC_PATH, "r", encoding="utf-8") as f:
        episodes = json.load(f)

    episodes.append(
        {
            "memory-saved-on": datetime.now().isoformat(),
            "fact": fact,
        }
    )

    with open(EPISODIC_PATH, "w", encoding="utf-8") as f:
        json.dump(episodes, f, indent=2)

    return f"Memorised: {fact}"


def search_skills(tag: str, schemas_dir: str = "skills/skillset/schemas") -> list[dict]:
    """Search all JSON files in schemas_dir and return {name, description}
    for every tool whose `function.tag` matches the given tag."""
    results = []
    for filepath in Path(schemas_dir).glob("*.json"):
        try:
            with open(filepath) as f:
                tools = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(tools, list):
            continue
        for tool in tools:
            func = tool.get("function", {})
            if func.get("tag") == tag:
                results.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                    }
                )
    return results


def load_skills(names: list[str]) -> list[dict]:
    with open("config.json", "r") as f:
        config = json.load(f)
    limit = config.get("max_tools_per_load", 5)

    schemas_dir = Path("skills/skillset/schemas")
    loaded = []
    for filepath in schemas_dir.glob("*.json"):
        try:
            with open(filepath) as f:
                tools = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(tools, list):
            continue
        for tool in tools:
            func = tool.get("function", {})
            if func.get("name") in names and len(loaded) < limit:
                loaded.append(tool)
    return loaded
