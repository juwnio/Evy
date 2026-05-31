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
                continue

            page_id = page_id_raw

            title = get_page_title_from_search(item)

            page_data = client.pages.retrieve(page_id=page_id)
            if not isinstance(page_data, dict):
                raise RuntimeError(
                    f"Unexpected page retrieve response type: {type(page_data)}"
                )

            public_url = page_data.get("public_url")
            is_public = public_url is not None and public_url is not False

            all_pages.append(
                {
                    "id": page_id,
                    "title": title,
                    "is_public": is_public,
                }
            )

        next_cursor = response.get("next_cursor")
        if next_cursor is None or not isinstance(next_cursor, str):
            break
        start_cursor = next_cursor

    return all_pages


HEADING_TYPES = {"heading_1", "heading_2", "heading_3"}
HEADING_PREFIX = {"heading_1": "#", "heading_2": "##", "heading_3": "###"}

BLOCK_RENDERERS = {
    "heading_1": lambda b: f"# {_plain(b['heading_1'])}",
    "heading_2": lambda b: f"## {_plain(b['heading_2'])}",
    "heading_3": lambda b: f"### {_plain(b['heading_3'])}",
    "paragraph": lambda b: _plain(b["paragraph"]),
    "bulleted_list_item": lambda b: f"- {_plain(b['bulleted_list_item'])}",
    "numbered_list_item": lambda b: f"1. {_plain(b['numbered_list_item'])}",
    "to_do": lambda b: f"{'☑' if b['to_do']['checked'] else '☐'} {_plain(b['to_do'])}",
    "toggle": lambda b: f"> {_plain(b['toggle'])}",
    "quote": lambda b: f"| {_plain(b['quote'])}",
    "code": lambda b: f"`{_plain(b['code'])}`",
    "divider": lambda b: "---",
    "callout": lambda b: f"[{_plain(b['callout'])}]",
}


def _plain(block_content: dict) -> str:
    """Extract plain text from a block's rich_text list."""
    return "".join(
        segment.get("plain_text", "") for segment in block_content.get("rich_text", [])
    )


def _fetch_all_blocks(client, page_id: str) -> list:
    """Fetch all blocks for a page, handling pagination."""
    blocks = []
    cursor = None
    while True:
        kwargs = {"block_id": page_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = client.blocks.children.list(**kwargs)
        blocks.extend(response.get("results", []))
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    return blocks


def create_notion_page(
    title: str,
    content: Optional[str] = None,
    token: Optional[str] = None,
) -> str:
    """Create a new Notion page under the configured default parent, with optional text content."""
    if token is None:
        token = load_notion_token()

    parent_id = os.getenv("notion-default-page-id")
    if not parent_id:
        raise RuntimeError(
            "No default parent page configured. Add 'notion-default-page-id=<page_id>' to your .env file."
        )

    client = Client(auth=token)

    children: List[Dict[str, Any]] = []
    if content:
        for line in content.splitlines():
            line = line.strip()
            if line:
                children.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": line}}]
                        },
                    }
                )

    page = client.pages.create(
        parent={"page_id": parent_id},
        properties={"title": {"title": [{"type": "text", "text": {"content": title}}]}},
        children=children,
    )

    if not isinstance(page, dict):
        raise RuntimeError(f"Unexpected create response type: {type(page)}")

    page_id = page.get("id", "unknown")
    url = page.get("url", "")
    return f"Created page '{title}' (id: {page_id}, url: {url})"


TEXT_BLOCK_TYPES = {
    "heading_1",
    "heading_2",
    "heading_3",
    "paragraph",
    "bulleted_list_item",
    "numbered_list_item",
    "to_do",
    "toggle",
    "quote",
    "code",
    "callout",
}


def replace_notion_block(
    page_id: str,
    old_text: str,
    new_text: str,
    token: Optional[str] = None,
) -> str:
    """Find a block on a Notion page by its exact text and replace it with new text."""
    if token is None:
        token = load_notion_token()

    client = Client(auth=token)
    blocks = _fetch_all_blocks(client, page_id)

    matched = []
    for block in blocks:
        block_type = block.get("type")
        if block_type not in TEXT_BLOCK_TYPES:
            continue
        if _plain(block.get(block_type, {})) == old_text:
            matched.append((block.get("id"), block_type, block))

    if not matched:
        return f"No block found matching: '{old_text}'"

    for block_id, block_type, block in matched:
        rich_text = [{"type": "text", "text": {"content": new_text}}]
        if block_type == "to_do":
            checked = block.get("to_do", {}).get("checked", False)
            update_body = {"rich_text": rich_text, "checked": checked}
        else:
            update_body = {"rich_text": rich_text}
        client.blocks.update(block_id=block_id, **{block_type: update_body})

    return f"Replaced {len(matched)} block(s): '{old_text}' → '{new_text}'"


def write_notion_page_content(
    page_id: str,
    content: str,
    mode: str = "append",
    token: Optional[str] = None,
) -> str:
    """Append or replace the content of a Notion page."""
    if token is None:
        token = load_notion_token()

    client = Client(auth=token)

    new_blocks: List[Dict[str, Any]] = []
    for line in content.splitlines():
        line = line.strip()
        if line:
            new_blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": line}}]
                    },
                }
            )

    if mode == "replace":
        existing = _fetch_all_blocks(client, page_id)
        for block in existing:
            block_id = block.get("id")
            if block_id:
                client.blocks.delete(block_id=block_id)

    client.blocks.children.append(block_id=page_id, children=new_blocks)

    action = "Replaced" if mode == "replace" else "Appended"
    return f"{action} content on page {page_id} ({len(new_blocks)} block(s) written)"


def get_notion_page_content(
    page_id: str,
    filter: str = "all",
    token: Optional[str] = None,
) -> str:
    if token is None:
        token = load_notion_token()

    client = Client(auth=token)
    blocks = _fetch_all_blocks(client, page_id)

    lines = []
    for block in blocks:
        block_type = block.get("type")

        if filter == "headings" and block_type not in HEADING_TYPES:
            continue
        if filter == "todos" and block_type != "to_do":
            continue

        renderer = BLOCK_RENDERERS.get(block_type)
        if renderer:
            try:
                line = renderer(block)
                if line:
                    lines.append(line)
            except (KeyError, TypeError):
                continue

    if not lines:
        return f"No content found for filter '{filter}'."

    return "\n".join(lines)
