import os
import json

import requests
from dotenv import load_dotenv

TAVILY_API_URL = "https://api.tavily.com/search"
TAVILY_API_KEY_ENV = "tavily-api-key"
DEFAULT_MAX_RESULTS = 5


def _load_api_key() -> str:
    load_dotenv()
    key = os.getenv(TAVILY_API_KEY_ENV)
    if not key:
        return (
            "Tavily API key not configured. "
            "Add tavily-api-key to your .env file "
            "(get one at https://app.tavily.com)."
        )
    return key


def tavily_search(
    query: str,
    search_depth: str = "basic",
    max_results: int = DEFAULT_MAX_RESULTS,
    topic: str = "general",
    time_range: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    include_answer: str | None = None,
    include_raw_content: str | None = None,
    include_images: bool = False,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    country: str | None = None,
    auto_parameters: bool = False,
    exact_match: bool = False,
) -> str:
    api_key = _load_api_key()
    if api_key.startswith("Tavily API key not configured"):
        return api_key

    payload: dict = {
        "query": query,
        "search_depth": search_depth,
        "max_results": max(max_results, DEFAULT_MAX_RESULTS),
        "topic": topic,
        "include_images": include_images,
        "auto_parameters": auto_parameters,
        "exact_match": exact_match,
    }

    if time_range:
        payload["time_range"] = time_range
    if start_date:
        payload["start_date"] = start_date
    if end_date:
        payload["end_date"] = end_date
    if include_answer:
        payload["include_answer"] = include_answer
    if include_raw_content:
        payload["include_raw_content"] = include_raw_content
    if include_domains:
        payload["include_domains"] = include_domains
    if exclude_domains:
        payload["exclude_domains"] = exclude_domains
    if country:
        payload["country"] = country

    try:
        resp = requests.post(
            TAVILY_API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.Timeout:
        return "Error: Tavily search request timed out after 30s."
    except requests.RequestException as e:
        return f"Error: Tavily search request failed - {e}"

    results = data.get("results", [])
    answer = data.get("answer")
    response_time = data.get("response_time")
    images = data.get("images", [])

    lines = [f"Search results for: {query}"]
    if response_time is not None:
        lines.append(f"(completed in {response_time}s)")

    if answer:
        lines.append("")
        lines.append(f"[Answer] {answer}")

    if images and include_images:
        lines.append("")
        lines.append(f"[Images] ({len(images)} image(s) found)")
        for img in images[:5]:
            desc = img.get("description", "")
            url = img.get("url", "")
            lines.append(f"  - {desc}: {url}" if desc else f"  - {url}")

    if not results:
        lines.append("")
        lines.append("No results found.")
        return "\n".join(lines)

    for i, result in enumerate(results, 1):
        title = result.get("title", "(no title)")
        url = result.get("url", "")
        content = result.get("content", "")
        score = result.get("score", "")
        favicon = result.get("favicon", "")
        raw = result.get("raw_content", "")
        result_images = result.get("images", [])

        lines.append("")
        lines.append(f"{i}. {title}")
        lines.append(f"   URL: {url}")
        if favicon:
            lines.append(f"   Favicon: {favicon}")
        if score:
            lines.append(f"   Relevance: {score:.2f}")
        if content:
            lines.append(f"   Summary: {content}")
        if raw and include_raw_content:
            lines.append(f"   Raw content: {raw[:1500]}")
            if len(raw) > 1500:
                lines.append("   ... (raw content truncated)")
        if result_images and include_images:
            for img in result_images[:3]:
                desc = img.get("description", "")
                img_url = img.get("url", "")
                lines.append(f"   Image: {desc}: {img_url}" if desc else f"   Image: {img_url}")

    return "\n".join(lines)
