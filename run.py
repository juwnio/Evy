from rich.console import Console

from gateway import call_evy

console = Console()
while True:
    prompt = console.input("\n[cyan]You: [/cyan]")
    print()
    if prompt.lower() == "exit":
        break
    response = call_evy(prompt)
    console.print(f"\n[#346791]{response}[/#346791]")
