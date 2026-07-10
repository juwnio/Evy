import os
import re
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


def _normalize_rich_text(value: Any) -> list:
    """Normalize a rich_text value to the correct Notion API format.

    Notion API expects rich_text to be an array of rich_text objects:
        [{"type": "text", "text": {"content": "..."}}]

    Common mistakes this fixes:
        - Single object wrapped in {"item": ...} -> unwrap and wrap in array
        - Single object without array wrapper -> wrap in array
        - Already correct array -> pass through
    """
    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        # Fix: {"item": {"text": {"content": "..."}}} -> [{"text": {"content": "..."}}]
        if "item" in value and len(value) == 1:
            inner = value["item"]
            if isinstance(inner, dict):
                return [inner]
            return value

        # Fix: {"text": {"content": "..."}} -> [{"text": {"content": "..."}}]
        if "text" in value or "type" in value:
            return [value]

    return value


def _normalize_properties(properties: dict) -> dict:
    """Normalize database item properties to correct Notion API format.

    Fixes common LLM mistakes:
        - rich_text/title: single object -> array
        - rich_text/title: {"item": {...}} -> [{...}]
        - select/status: {"name": "X"} already correct (pass through)
        - date: {"start": "YYYY-MM-DD"} already correct (pass through)
    """
    ARRAY_PROPERTY_TYPES = {"rich_text", "title"}

    normalized = {}
    for prop_name, prop_value in properties.items():
        if not isinstance(prop_value, dict):
            normalized[prop_name] = prop_value
            continue

        # Check if this looks like a property type wrapper (has a single key that's a known type)
        type_keys = set(prop_value.keys()) - {"id"}
        if len(type_keys) == 1:
            prop_type = next(iter(type_keys))

            if prop_type in ARRAY_PROPERTY_TYPES:
                # Normalize rich_text/title arrays
                raw_value = prop_value[prop_type]
                normalized[prop_name] = {
                    prop_type: _normalize_rich_text(raw_value)
                }
                continue

        normalized[prop_name] = prop_value

    return normalized


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


def list_notion_pages(token: Optional[str] = None, _cancel_event=None) -> List[Dict[str, Any]]:
    if token is None:
        token = load_notion_token()

    client = Client(auth=token)

    all_pages: List[Dict[str, Any]] = []
    start_cursor: Optional[str] = None

    while True:
        if _cancel_event is not None and _cancel_event.is_set():
            break

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
            parent_type = item.get("parent", {}).get("type")
            # As of Notion API 2025-09-03, database rows have parent.type
            # "data_source_id" instead of (or in addition to) "database_id".
            # Exclude both so database rows never show up as plain pages.
            if parent_type in ("database_id", "data_source_id"):
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


def _parse_inline(text: str) -> List[Dict[str, Any]]:
    """Parse inline markdown into Notion rich_text segments with annotations.

    Supports: **bold**, *italic*, ***bold+italic***, `code`, ~~strikethrough~~, [links](url).
    """
    if not text:
        return []

    parts = []
    last_end = 0

    pattern = re.compile(
        r'\[([^\]]+)\]\(([^)]+)\)'             # [text](url)
        r'|\*\*\*([^*]+)\*\*\*'                # ***bold+italic***
        r'|\*\*([^*]+)\*\*'                    # **bold**
        r'|\*([^*]+)\*'                        # *italic*
        r'|`([^`]+)`'                          # `code`
        r'|~~([^~]+)~~'                        # ~~strikethrough~~
    )

    for m in pattern.finditer(text):
        start, end = m.start(), m.end()

        if start > last_end:
            parts.append({"type": "text", "text": {"content": text[last_end:start]}})

        if m.group(1) is not None:
            parts.append({
                "type": "text",
                "text": {"content": m.group(1), "link": {"url": m.group(2)}},
            })
        elif m.group(3) is not None:
            parts.append({
                "type": "text",
                "text": {"content": m.group(3)},
                "annotations": {"bold": True, "italic": True},
            })
        elif m.group(4) is not None:
            parts.append({
                "type": "text",
                "text": {"content": m.group(4)},
                "annotations": {"bold": True},
            })
        elif m.group(5) is not None:
            parts.append({
                "type": "text",
                "text": {"content": m.group(5)},
                "annotations": {"italic": True},
            })
        elif m.group(6) is not None:
            parts.append({
                "type": "text",
                "text": {"content": m.group(6)},
                "annotations": {"code": True},
            })
        elif m.group(7) is not None:
            parts.append({
                "type": "text",
                "text": {"content": m.group(7)},
                "annotations": {"strikethrough": True},
            })

        last_end = end

    if last_end < len(text):
        parts.append({"type": "text", "text": {"content": text[last_end:]}})

    return parts


def _markdown_to_blocks(text: str) -> List[Dict[str, Any]]:
    """Parse markdown text into Notion API block objects.

    Handles: headings, bullet/numbered lists, to-dos, quotes, code fences,
    dividers, and paragraphs — with inline formatting in each.
    """
    if not text:
        return []

    blocks = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        raw_line = lines[i]
        stripped = raw_line.strip()

        # ── Fenced code block ──────────────────────────────────────────
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence

            code_content = "\n".join(code_lines)
            blocks.append({
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": code_content}}],
                    "language": lang or "plain text",
                },
            })
            continue

        # ── Empty line ────────────────────────────────────────────────
        if not stripped:
            i += 1
            continue

        # ── Divider ───────────────────────────────────────────────────
        if re.match(r'^[-*_]{3,}$', stripped):
            blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {},
            })
            i += 1
            continue

        # ── Headings (h1, h2, h3) ─────────────────────────────────────
        heading_match = re.match(r'^(#{1,3})\s+(.+)$', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            block_type = f"heading_{level}"
            content = heading_match.group(2)
            blocks.append({
                "object": "block",
                "type": block_type,
                block_type: {
                    "rich_text": _parse_inline(content),
                },
            })
            i += 1
            continue

        # ── To-do items ──────────────────────────────────────────────
        todo_match = re.match(r'^[-*]\s+\[([ xX])\]\s+(.+)$', stripped)
        if todo_match:
            checked = todo_match.group(1).lower() == "x"
            content = todo_match.group(2)
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": _parse_inline(content),
                    "checked": checked,
                },
            })
            i += 1
            continue

        # ── Bulleted list items ──────────────────────────────────────
        bullet_match = re.match(r'^[-*+]\s+(.+)$', stripped)
        if bullet_match:
            content = bullet_match.group(1)
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": _parse_inline(content),
                },
            })
            i += 1
            continue

        # ── Numbered list items ──────────────────────────────────────
        numbered_match = re.match(r'^\d+\.\s+(.+)$', stripped)
        if numbered_match:
            content = numbered_match.group(1)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": _parse_inline(content),
                },
            })
            i += 1
            continue

        # ── Block quotes (handles continuation lines) ────────────────
        quote_match = re.match(r'^>\s?(.*)$', stripped)
        if quote_match:
            quote_lines = [quote_match.group(1)]
            i += 1
            while i < len(lines):
                next_q = re.match(r'^>\s?(.*)$', lines[i].strip())
                if next_q:
                    quote_lines.append(next_q.group(1))
                    i += 1
                else:
                    break
            quote_content = "\n".join(quote_lines)
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{"type": "text", "text": {"content": quote_content}}],
                },
            })
            continue

        # ── Paragraph (default fallback) ──────────────────────────────
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": _parse_inline(stripped),
            },
        })
        i += 1

    return blocks


def create_notion_page(
    title: str,
    parent_page_id: Optional[str] = None,
    content: Optional[str] = None,
    token: Optional[str] = None,
) -> str:
    if token is None:
        token = load_notion_token()

    parent_id = parent_page_id or os.getenv("notion-default-page-id")
    if not parent_id:
        return (
            "No parent page specified. Call create_notion_page with a "
            "parent_page_id, or set notion-default-page-id in your .env file."
        )

    client = Client(auth=token)

    children = _markdown_to_blocks(content) if content else []

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
    """Append or replace the content of a Notion page with markdown content."""
    if token is None:
        token = load_notion_token()

    client = Client(auth=token)

    new_blocks = _markdown_to_blocks(content)

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


def _resolve_data_source_id(client: Client, id_: str) -> str:
    """Resolve a database ID or data source ID into a usable data source ID.

    Since Notion API 2025-09-03, rows live under a data source, not a
    database directly. Callers (and old code) often only have a database
    ID, so this tries to look it up and find its single data source. If
    the lookup fails (e.g. `id_` is already a data source ID), it's
    returned unchanged.
    """
    try:
        db = client.databases.retrieve(database_id=id_)
    except Exception:
        return id_

    if not isinstance(db, dict):
        return id_

    data_sources = db.get("data_sources", [])
    if not data_sources:
        return id_

    if len(data_sources) > 1:
        names = [ds.get("id") for ds in data_sources]
        raise RuntimeError(
            f"Database {id_} has multiple data sources; pass a specific "
            f"data_source_id instead of a database_id. Available data "
            f"source IDs: {names}"
        )

    return data_sources[0].get("id", id_)


def list_notion_databases(token: Optional[str] = None, _cancel_event=None) -> str:
    if token is None:
        token = load_notion_token()

    client = Client(auth=token)

    all_databases: list[dict] = []
    start_cursor: Optional[str] = None

    while True:
        if _cancel_event is not None and _cancel_event.is_set():
            break

        kwargs: dict = {
            "filter": {"property": "object", "value": "data_source"},
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
            # The search filter above asks for "data_source" objects, so
            # that's what comes back -- not "database". (This mismatch was
            # the bug: it used to check for "database" and silently
            # discard every single result.)
            if not isinstance(item, dict) or item.get("object") != "data_source":
                continue

            ds_id = item.get("id", "")
            parent_database_id = item.get("parent", {}).get("database_id", "")
            title = get_page_title_from_search(item)
            props = item.get("properties", {})
            prop_summary = {}
            for pname, pdata in props.items():
                if isinstance(pdata, dict):
                    prop_summary[pname] = pdata.get("type", "unknown")

            all_databases.append({
                "data_source_id": ds_id,
                "database_id": parent_database_id,
                "title": title,
                "properties": prop_summary,
            })

        next_cursor = response.get("next_cursor")
        if next_cursor is None or not isinstance(next_cursor, str):
            break
        start_cursor = next_cursor

    if not all_databases:
        return "No databases found in the workspace."

    import json
    return json.dumps(all_databases, indent=2)


def create_notion_database(
    parent_page_id: str,
    title: str,
    properties: dict,
    token: Optional[str] = None,
) -> str:
    if token is None:
        token = load_notion_token()

    client = Client(auth=token)

    page = client.databases.create(
        parent={"page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": title}}],
        # As of API 2025-09-03, a database's property schema is set via
        # its initial data source, not a top-level "properties" field.
        initial_data_source={"properties": properties},
    )

    if not isinstance(page, dict):
        raise RuntimeError(f"Unexpected create response type: {type(page)}")

    db_id = page.get("id", "unknown")
    url = page.get("url", "")
    return f"Created database '{title}' (id: {db_id}, url: {url})"


def _format_property_value(prop_name: str, prop_data: dict) -> str:
    ptype = prop_data.get("type", "")
    if ptype == "title":
        titles = prop_data.get("title", [])
        return "".join(t.get("plain_text", "") for t in titles if isinstance(t, dict))
    elif ptype == "rich_text":
        texts = prop_data.get("rich_text", [])
        return "".join(t.get("plain_text", "") for t in texts if isinstance(t, dict))
    elif ptype == "number":
        return str(prop_data.get("number", ""))
    elif ptype == "select":
        s = prop_data.get("select")
        return s.get("name", "") if s else ""
    elif ptype == "multi_select":
        return ", ".join(s.get("name", "") for s in prop_data.get("multi_select", []))
    elif ptype == "date":
        d = prop_data.get("date")
        if d:
            start = d.get("start", "")
            end = d.get("end", "")
            return f"{start} → {end}" if end else start
        return ""
    elif ptype == "checkbox":
        return str(prop_data.get("checkbox", False))
    elif ptype == "email":
        return prop_data.get("email", "")
    elif ptype == "phone":
        return prop_data.get("phone_number", "")
    elif ptype == "url":
        return prop_data.get("url", "")
    elif ptype == "status":
        s = prop_data.get("status")
        return s.get("name", "") if s else ""
    elif ptype == "files":
        files = prop_data.get("files", [])
        names = []
        for f in files:
            if isinstance(f, dict):
                names.append(f.get("name", ""))
        return ", ".join(names)
    return str(prop_data) if prop_data else ""


def query_notion_database(
    database_id: str,
    filter: Optional[dict] = None,
    sorts: Optional[list] = None,
    page_size: int = 50,
    token: Optional[str] = None,
) -> str:
    if token is None:
        token = load_notion_token()

    client = Client(auth=token)
    data_source_id = _resolve_data_source_id(client, database_id)

    # client.databases.query() is legacy under API 2025-09-03 and will
    # error; rows must be queried via the data_sources endpoint instead.
    kwargs: dict = {
        "data_source_id": data_source_id,
        "page_size": min(page_size, 100),
    }
    if filter:
        kwargs["filter"] = filter
    if sorts:
        kwargs["sorts"] = sorts

    all_results: list[dict] = []
    start_cursor: Optional[str] = None

    while True:
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        response = client.data_sources.query(**kwargs)
        if not isinstance(response, dict):
            raise RuntimeError(f"Unexpected query response type: {type(response)}")

        results = response.get("results", [])
        for item in results:
            if not isinstance(item, dict):
                continue
            page_id = item.get("id", "")
            props = item.get("properties", {})
            formatted = {"page_id": page_id}
            if isinstance(props, dict):
                for pname, pdata in props.items():
                    formatted[pname] = _format_property_value(pname, pdata)
            all_results.append(formatted)

        if not response.get("has_more"):
            break
        next_cursor = response.get("next_cursor")
        if not next_cursor:
            break
        start_cursor = next_cursor

    if not all_results:
        return "No items found in the database."

    import json
    return json.dumps(all_results, indent=2)


def create_notion_database_item(
    database_id: str,
    properties: dict,
    token: Optional[str] = None,
) -> str:
    if token is None:
        token = load_notion_token()

    client = Client(auth=token)
    data_source_id = _resolve_data_source_id(client, database_id)
    properties = _normalize_properties(properties)

    # Since API 2025-09-03, new pages in a database must be parented to
    # a specific data source, not the database itself.
    page = client.pages.create(
        parent={"type": "data_source_id", "data_source_id": data_source_id},
        properties=properties,
    )

    if not isinstance(page, dict):
        raise RuntimeError(f"Unexpected create response type: {type(page)}")

    page_id = page.get("id", "unknown")
    url = page.get("url", "")
    return f"Created item in database (id: {page_id}, url: {url})"


def update_notion_database_item(
    page_id: str,
    properties: dict,
    token: Optional[str] = None,
) -> str:
    if token is None:
        token = load_notion_token()

    client = Client(auth=token)
    properties = _normalize_properties(properties)

    page = client.pages.update(
        page_id=page_id,
        properties=properties,
    )

    if not isinstance(page, dict):
        raise RuntimeError(f"Unexpected update response type: {type(page)}")

    return f"Updated item {page_id}"