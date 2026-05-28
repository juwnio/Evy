from gateway import call_evy

while True:
    prompt = input("You: ")
    if prompt.lower() == "exit":
        break
    response = call_evy(prompt)
    print(f"Eve: {response}")
