import json

from rich.console import Console

from gateway import call_evy

console = Console()


def _load_config():
    with open("config.json", "r") as f:
        return json.load(f)


def _save_config(config: dict):
    with open("config.json", "w") as f:
        json.dump(config, f, indent=2)


def set_browser_headless(value: bool):
    config = _load_config()
    config["browser_headless"] = value
    _save_config(config)


while True:
    prompt = console.input("\n[cyan]You: [/cyan]")
    if prompt == "/?":
        console.print("\nHelpful Commands:\n")
        console.print("[dim]    /bye          - Close Evy[/dim]")
        console.print("[dim]    /think/stream - Enable thinking & show thoughts[/dim]")
        console.print("[dim]    /think/quet   - Enable thinking, hide thoughts[/dim]")
        console.print("[dim]    /nothink      - Disable thinking entirely[/dim]")
        console.print("[dim]    /state        - Show current mode[/dim]")
        console.print("[dim]    /headless     - Set browser headless mode ⅏[/dim]")
        console.print("[dim]    /head         - Set browser head mode ࿂[/dim]")
        continue
    if prompt == "/think/stream":
        config = _load_config()
        if not config["thinking"]:
            config["thinking"] = True
            config["stream_thinking"] = True
            _save_config(config)
            console.print(
                "\n[#eb9b34]✱[/#eb9b34] [dim]Thinking enabled, thoughts will be shown[/dim]"
            )
        else:
            config["stream_thinking"] = not config["stream_thinking"]
            _save_config(config)
            state = "shown" if config["stream_thinking"] else "hidden"
            console.print(f"\n[#eb9b34]↻[/#eb9b34] [dim]Thoughts will be {state}[/dim]")
        continue
    if prompt == "/think/quet":
        config = _load_config()
        config["thinking"] = True
        config["stream_thinking"] = False
        _save_config(config)
        console.print(
            "\n[#eb9b34]✱[/#eb9b34] [dim]Thinking enabled, thoughts hidden[/dim]"
        )
        continue
    if prompt == "/nothink":
        config = _load_config()
        config["thinking"] = False
        config["stream_thinking"] = False
        _save_config(config)
        console.print("\n[#eb9b34]✳[/#eb9b34] [dim]Thinking disabled[/dim]")
        continue
    if prompt == "/state":
        config = _load_config()
        think = "on" if config["thinking"] else "off"
        stream = "show" if config.get("stream_thinking") else "hide"
        console.print(
            f"\n[#eb9b34]ⓘ[/#eb9b34] [dim]Thinking: {think}  |  Thoughts: {stream}[/dim]"
        )
        continue
    if prompt == "/headless":
        set_browser_headless(True)
        console.print(
            "\n[#eb9b34]⅏ [/#eb9b34] [dim]Evy will use browser in background[/dim]"
        )
        continue
    if prompt == "/head":
        set_browser_headless(False)
        console.print(
            "\n[#eb9b34]࿂[/#eb9b34] [dim]You can now see Evy run browser in action[/dim]"
        )
        continue
    print()
    if prompt == "/bye":
        console.print("\n[dim]Goodbye![/dim]")
        break
    response = call_evy(prompt)
    console.print(f"\n[#1c9dff]{response}[/#1c9dff]\n")
    console.print("[dim]/?          - Help[/dim]")
