import json
import os

import requests
from dotenv import load_dotenv


def _load_obsidian_config():
    load_dotenv()
    host = os.getenv("obsidian-host", "http://127.0.0.1:27123")
    api_key = os.getenv("obsidian-api-key", "")
    return host, api_key


def _request(method, endpoint, **kwargs):
    host, api_key = _load_obsidian_config()
    if not api_key:
        return (
            "Obsidian API key not configured. "
            "Add obsidian-api-key to your .env file "
            "(find it in Obsidian → Settings → Local REST API)."
        )
    url = f"{host}{endpoint}"
    headers = {"Authorization": f"Bearer {api_key}"}
    if "headers" in kwargs:
        headers.update(kwargs.pop("headers"))
    try:
        resp = requests.request(method, url, headers=headers, timeout=15, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204:
            return "OK"
        return resp.text
    except requests.RequestException as e:
        return f"Obsidian error: {e}"


def obsidian_read(path: str) -> str:
    return _request(
        "GET",
        f"/vault/{path.lstrip('/')}",
        headers={"Accept": "application/vnd.olrapi.note+json"},
    )


def obsidian_write(path: str, content: str) -> str:
    return _request(
        "PUT",
        f"/vault/{path.lstrip('/')}",
        data=content.encode("utf-8"),
        headers={"Content-Type": "text/markdown"},
    )


def obsidian_append(path: str, content: str) -> str:
    return _request(
        "POST",
        f"/vault/{path.lstrip('/')}",
        data=content.encode("utf-8"),
        headers={"Content-Type": "text/markdown"},
    )


def obsidian_search(query: str) -> str:
    return _request("POST", "/search/simple/", params={"query": query})


def obsidian_list(path: str = "") -> str:
    p = path.strip("/")
    endpoint = f"/vault/{p}/" if p else "/vault/"
    resp = _request("GET", endpoint)
    if resp.startswith("Obsidian error") or resp.startswith("Obsidian API key"):
        return resp
    try:
        data = json.loads(resp)
        files = data.get("files", [])
        return "\n".join(files) if files else "(empty)"
    except (json.JSONDecodeError, KeyError) as e:
        return f"Obsidian error: failed to parse directory listing: {e}"


def obsidian_open(path: str) -> str:
    return _request("POST", f"/open/{path.lstrip('/')}")
