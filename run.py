import json

from rich.console import Console

from gateway import call_evy

console = Console()


def set_thinking(value: bool):
    with open("config.json", "r") as f:
        config = json.load(f)
    config["thinking"] = value
    with open("config.json", "w") as f:
        json.dump(config, f, indent=2)


def get_thinking_state() -> bool:
    with open("config.json", "r") as f:
        config = json.load(f)
    return config.get("thinking", False)


while True:
    prompt = console.input("\n[cyan]You: [/cyan]")
    if prompt == "/?":
        console.print("\nHelpful Commands:\n")
        console.print("[dim]    /bye     - Close Evy[/dim]")
        console.print("[dim]    /think   - Enable thinking ✱[/dim]")
        console.print("[dim]    /nothink - Disable thinking ✳[/dim]")
        console.print("[dim]    /state   - Show thinking state[/dim]")
        continue
    if prompt == "/think":
        set_thinking(True)
        console.print("\n[#eb9b34]✱[/#eb9b34] [dim]Set thinking mode to true[/dim]")
        continue
    if prompt == "/nothink":
        set_thinking(False)
        console.print("\n[#eb9b34]✳[/#eb9b34] [dim]Set thinking mode to false[/dim]")
        continue
    if prompt == "/state":
        console.print(
            "\n[#eb9b34]✱[/#eb9b34] [dim]Evy is really thinking about it![/dim]"
        ) if get_thinking_state() else (
            "\n[#eb9b34]✳[/#eb9b34] [dim]Evy is not thinking about it.[/dim]"
        )
        continue
    print()
    if prompt == "/bye":
        console.print("\n[dim]Goodbye![/dim]")
        break
    response = call_evy(prompt)
    console.print(f"[#1c9dff]{response}[/#1c9dff]\n")
    console.print("[dim]/?       - Help[/dim]")
