from rich.console import Console

from gateway import call_evy

console = Console()
while True:
    prompt = console.input("\n[cyan]You: [/cyan]")
    if prompt.lower() == "exit":
        break
    response = call_evy(prompt)
    console.print(f"\n[#4a4848]Eve:[/#4a4848] {response}")
