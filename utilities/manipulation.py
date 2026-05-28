import json
import os


# Load system context from system-context.json
def load_system_context():
    with open("memory/system-context.json", "r") as f:
        system_context = json.load(f)

    system_prompt = "\n".join(
        f"{key}: {value}" for key, value in system_context.items()
    )
    return system_prompt


# Load skills context from skills-context.json
def load_skills_context():
    with open("memory/skills-context.json", "r") as f:
        skills_context = json.load(f)

    system_prompt = "\n".join(
        f"{key}: {value}" for key, value in skills_context.items()
    )
    return system_prompt


# Load consolidation context from consolidation-context.json
def load_consolidation_context():
    with open("memory/system/consolidation-context.json", "r") as f:
        consolidation_context = json.load(f)

    system_prompt = "\n".join(
        f"{key}: {value}" for key, value in consolidation_context.items()
    )
    return system_prompt


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
