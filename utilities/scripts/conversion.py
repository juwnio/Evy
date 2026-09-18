import tiktoken


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """
    Count the number of tokens in text using tiktoken.

    Args:
        text: The text to tokenize
        model: The OpenAI model to use for encoding (default: "gpt-4o")
               Common options: "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "gpt-4"

    Returns:
        int: The number of tokens in the text
    """
    encoding = tiktoken.encoding_for_model(model)
    token_count = len(encoding.encode(text))
    return token_count


def consolidate_context(
    system_context: str, skills_context: str, primary_tools: list
) -> str:
    parts = [system_context, skills_context]

    if primary_tools:
        parts.append("\n=== Available Tools ===")
        for tool in primary_tools:
            fn = tool.get("function", {})
            name = fn.get("name", "unknown")
            desc = fn.get("description", "")
            parts.append(f"- {name}: {desc}")
            params = fn.get("parameters", {})
            props = params.get("properties", {})
            for prop_name, prop_info in props.items():
                ptype = prop_info.get("type", "any")
                pdesc = prop_info.get("description", "")
                parts.append(f"  {prop_name} ({ptype}): {pdesc}")

    return "\n".join(parts)
