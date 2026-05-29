import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from notion_client import Client


def load_notion_token(
    env_key: str = "notion-key", dotenv_path: Optional[Path] = None
) -> str:
    if dotenv_path is None:
        dotenv_path = Path(__file__).parent / ".env"
        if not dotenv_path.exists():
            dotenv_path = None

    load_dotenv(dotenv_path=dotenv_path)

    token = os.getenv(env_key)
    if not token:
        raise RuntimeError(
            f"Notion token not found. Make sure your .env file contains a line like:\n"
            f"{env_key}=secret_your_token_here\n"
        )
    return token


def get_page_title_from_search(item: Dict[str, Any]) -> str:
    properties = item.get("properties", {})
    if not isinstance(properties, dict):
        return "Untitled"

    for prop_name, prop_data in properties.items():
        if isinstance(prop_data, dict) and prop_data.get("type") == "title":
            title_obj = prop_data.get("title", [])
            if isinstance(title_obj, list):
                title_parts = [
                    t.get("plain_text", "") for t in title_obj if isinstance(t, dict)
                ]
                if title_parts:
                    return " ".join(title_parts)

    return "Untitled"


def list_notion_pages(token: Optional[str] = None) -> List[Dict[str, Any]]:
    if token is None:
        token = load_notion_token()

    client = Client(auth=token)

    all_pages: List[Dict[str, Any]] = []
    start_cursor: Optional[str] = None

    while True:
        kwargs = {
            "filter": {"property": "object", "value": "page"},
            "page_size": 100,
        }
        if start_cursor is not None:
            kwargs["start_cursor"] = start_cursor

        response = client.search(**kwargs)
        if not isinstance(response, dict):
            raise RuntimeError(f"Unexpected search response type: {type(response)}")

        results = response.get("results", [])
        if not results:
            break

        for item in results:
            if not isinstance(item, dict):
                continue

            page_id_raw = item.get("id")
            if page_id_raw is None or not isinstance(page_id_raw, str):
                # Skip items without a valid page_id
                continue

            page_id = page_id_raw

            title = get_page_title_from_search(item)

            # Fetch full page to check public_url
            page_data = client.pages.retrieve(page_id=page_id)
            if not isinstance(page_data, dict):
                raise RuntimeError(
                    f"Unexpected page retrieve response type: {type(page_data)}"
                )

            public_url = page_data.get("public_url")
            is_public = public_url is not None and public_url is not False

            all_pages.append(
                {
                    "title": title,
                    "is_public": is_public,
                }
            )

        next_cursor = response.get("next_cursor")
        if next_cursor is None or not isinstance(next_cursor, str):
            break
        start_cursor = next_cursor

    return all_pages
