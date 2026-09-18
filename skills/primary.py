import ctypes
import ctypes.util
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

EPISODIC_PATH = "memory/dynamic/episodic-memory.json"


_TEXT_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".rb", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".scala",
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".xml", ".html",
    ".css", ".scss", ".less", ".sql", ".sh", ".bash", ".zsh", ".fish",
    ".env", ".cfg", ".ini", ".conf", ".rst", ".tex", ".mdx",
    ".gradle", ".lock", ".sqlite", ".csv", ".tsv", ".log",
})


def _get_home() -> Path:
    try:
        with open("utilities/config.json") as f:
            cfg = json.load(f)
        home = cfg.get("home_dir")
        if home:
            return Path(home).expanduser().resolve()
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return Path("~/Documents").expanduser()


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = _get_home() / p
    return p.resolve()


def _validate_search_root(root: str | None) -> Path | None:
    resolved = _resolve_path(root) if root else _get_home()
    if not resolved.exists():
        return None
    if not resolved.is_dir():
        return None
    home = _get_home()
    if not str(resolved).startswith(str(home)):
        return None
    return resolved


def grep(
    pattern: str,
    root: str | None = None,
    glob: str | None = None,
    max_matches: int = 50,
    context_lines: int = 0,
    case_sensitive: bool = True,
) -> str:
    resolved_root = _validate_search_root(root)
    if resolved_root is None:
        return f"Error: root '{root or _get_home()}' is not valid or outside allowed directory."

    rg_path = shutil.which("rg")
    if rg_path:
        return _grep_rg(rg_path, pattern, resolved_root, glob, max_matches, context_lines, case_sensitive)
    return _grep_re(pattern, resolved_root, glob, max_matches, context_lines, case_sensitive)


def _grep_rg(
    rg_path: str,
    pattern: str,
    root: Path,
    glob: str | None,
    max_matches: int,
    context_lines: int,
    case_sensitive: bool,
) -> str:
    cmd = [
        rg_path, "--line-number", "--no-heading", "--no-messages",
        f"--max-count={max(1, max_matches * 2)}",
    ]
    if not case_sensitive:
        cmd.append("-i")
    if context_lines > 0:
        cmd.extend(["-C", str(context_lines)])
    if glob and glob != "**/*":
        cmd.extend(["--glob", glob])

    cmd.append(pattern)
    cmd.append(str(root))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "Error: grep timed out after 120s."
    except Exception as e:
        return f"Error: grep failed — {e}"

    output = result.stdout.strip()
    if not output:
        return f"No matches for '{pattern}' under {root}"

    lines = output.splitlines()
    total = len(lines)
    if total > max_matches:
        lines = lines[:max_matches]
        truncated = total - max_matches
        header = f"Found {total} matches (showing first {max_matches}, {truncated} omitted) in {root}:\n"
    else:
        header = f"Found {total} match{'es' if total != 1 else ''} in {root}:\n"

    return header + "\n".join(lines)


def _grep_re(
    pattern: str,
    root: Path,
    glob: str | None,
    max_matches: int,
    context_lines: int,
    case_sensitive: bool,
) -> str:
    try:
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
    except re.error as e:
        return f"Error: invalid regex pattern — {e}"

    matches: list[str] = []
    files = _iter_text_files(root, glob)

    for filepath in files:
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
        except (PermissionError, OSError):
            continue

        file_lines = text.splitlines()
        for lineno, line in enumerate(file_lines, start=1):
            if regex.search(line):
                _append_match(matches, filepath, root, lineno, line, file_lines, context_lines)
                if len(matches) >= max_matches:
                    break
        if len(matches) >= max_matches:
            break

    if not matches:
        return f"No matches for '{pattern}' under {root}"

    header = f"Found {len(matches)} match{'es' if len(matches) != 1 else ''} in {root}:\n"
    return header + "\n".join(matches)


def _iter_text_files(root: Path, glob: str | None):
    if glob and glob != "**/*":
        yield from sorted(root.glob(glob))
    else:
        for ext in _TEXT_EXTENSIONS:
            yield from sorted(root.rglob(f"*{ext}"))


def _append_match(
    matches: list,
    filepath: Path,
    root: Path,
    lineno: int,
    line: str,
    file_lines: list[str],
    context_lines: int,
):
    rel = filepath.relative_to(root)
    if context_lines > 0:
        start = max(0, lineno - 1 - context_lines)
        end = min(len(file_lines), lineno + context_lines)
        ctx_lines = []
        for i in range(start, end):
            tag = ">" if i == lineno - 1 else " "
            ctx_lines.append(f"{tag} {i + 1:>6d}: {file_lines[i]}")
        matches.append(f"{rel}:\n" + "\n".join(ctx_lines))
    else:
        matches.append(f"{rel}:{lineno}:{line}")


def reconsolidation(current_fact: str, updated_fact: str) -> str:
    with open(EPISODIC_PATH, "r", encoding="utf-8") as f:
        episodes = json.load(f)

    for entry in episodes:
        if entry["fact"] == current_fact:
            entry["fact"] = updated_fact
            entry["memory-saved-on"] = datetime.now().isoformat()
            with open(EPISODIC_PATH, "w", encoding="utf-8") as f:
                json.dump(episodes, f, indent=2)
            return f"Reconsolidated: '{current_fact}' → '{updated_fact}'"

    available = [e["fact"] for e in episodes]
    return (
        f"Could not find a fact matching '{current_fact}'. "
        f"Available facts: {available}\n"
        "Fact might have been merged with memory, "
        "create a new fact correcting the one you want to change!"
    )


def memorise(fact: str) -> str:
    with open(EPISODIC_PATH, "r", encoding="utf-8") as f:
        episodes = json.load(f)

    episodes.append(
        {
            "memory-saved-on": datetime.now().isoformat(),
            "fact": fact,
        }
    )

    with open(EPISODIC_PATH, "w", encoding="utf-8") as f:
        json.dump(episodes, f, indent=2)

    return f"Memorised: {fact}"


def search_skills(tag: str, schemas_dir: str = "skills/skillset/schemas") -> list[dict]:
    """Search all JSON files in schemas_dir and return {name, description}
    for every tool whose `function.tag` matches the given tag."""
    results = []
    for filepath in Path(schemas_dir).glob("*.json"):
        try:
            with open(filepath) as f:
                tools = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(tools, list):
            continue
        for tool in tools:
            func = tool.get("function", {})
            if func.get("tag") == tag:
                results.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                    }
                )
    return results


def load_skills(names: list[str]) -> list[dict]:
    with open("utilities/config.json", "r") as f:
        config = json.load(f)
    limit = config.get("max_tools_per_load", 5)

    schemas_dir = Path("skills/skillset/schemas")
    loaded = []
    for filepath in schemas_dir.glob("*.json"):
        try:
            with open(filepath) as f:
                tools = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(tools, list):
            continue
        for tool in tools:
            func = tool.get("function", {})
            if func.get("name") in names and len(loaded) < limit:
                loaded.append(tool)
    return loaded


# ── Workspace (macOS Spaces/Windows) tool ──────────────────────────

# System/background processes to filter out — these are never real user windows.
_SYSTEM_PROCESSES = frozenset({
    "CursorUIViewService",
    "WindowManager",
    "Universal Control",
    "loginwindow",
    "Dock",
    "ControlCenter",
    "SystemUIServer",
    "NotificationCenter",
    "WindowServer",
})

def _yabai_available() -> bool:
    return shutil.which("yabai") is not None


def _run_yabai(args: list[str]) -> list | dict:
    result = subprocess.run(
        ["yabai", "-m"] + args,
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yabai error: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _workspace_list_yabai(type: str, desktop_index: int | None) -> str:
    if type == "desktops":
        spaces = _run_yabai(["query", "--spaces"])
        current = _run_yabai(["query", "--spaces", "--space"])
        current_idx = current.get("index")
        parts = []
        for s in spaces:
            idx = s["index"]
            marker = " (active)" if idx == current_idx else ""
            lbl = f" — {s['label']}" if s.get("label") else ""
            parts.append(f"Desktop {idx}{lbl}{marker}")
        return "\n".join(parts) or "No desktops found."

    if type == "desktop_windows":
        windows = _run_yabai(["query", "--windows", "--space", str(desktop_index)])
        if not windows:
            return f"Desktop {desktop_index}: (no windows)"
        parts = [f"Desktop {desktop_index}:"]
        for w in windows:
            if w["app"] in _SYSTEM_PROCESSES:
                continue
            title = (w.get("title") or "").strip() or "(untitled)"
            parts.append(f"  {w['app']} — {title}")
        if len(parts) == 1:
            parts.append("  (no windows)")
        return "\n".join(parts)

    spaces = _run_yabai(["query", "--spaces"])
    windows = _run_yabai(["query", "--windows"])
    current = _run_yabai(["query", "--spaces", "--space"])
    current_idx = current.get("index")

    by_space: dict[int, list] = {}
    for w in windows:
        if w.get("app") in _SYSTEM_PROCESSES:
            continue
        by_space.setdefault(w.get("space"), []).append(w)

    parts = []
    for s in spaces:
        idx = s["index"]
        marker = " (active)" if idx == current_idx else ""
        parts.append(f"Desktop {idx}{marker}:")
        sw = by_space.get(idx, [])
        if not sw:
            parts.append("  (no windows)")
        else:
            for w in sw:
                title = (w.get("title") or "").strip() or "(untitled)"
                parts.append(f"  {w['app']} — {title}")
    return "\n".join(parts)


# ── Core Graphics fallback (no yabai) ─────────────────────────────

_cg_lib = None
_cf_lib = None


def _ensure_cg_libs():
    global _cg_lib, _cf_lib
    if _cg_lib is not None:
        return
    _cg_lib = ctypes.cdll.LoadLibrary(
        ctypes.util.find_library("CoreGraphics") or ""
    )
    _cf_lib = ctypes.cdll.LoadLibrary(
        ctypes.util.find_library("CoreFoundation") or ""
    )


def _cg_window_info() -> list[dict]:
    _ensure_cg_libs()
    cg = _cg_lib
    cf = _cf_lib

    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]

    window_list = cg.CGWindowListCopyWindowInfo(0, 0)
    if not window_list:
        return []

    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFStringGetLength.restype = ctypes.c_long
    cf.CFStringGetLength.argtypes = [ctypes.c_void_p]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32,
    ]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32,
    ]
    cf.CFNumberGetValue.restype = ctypes.c_bool
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cf.CFRelease.restype = None

    ENC = 0x08000100

    def _cfstr(s: str):
        return cf.CFStringCreateWithCString(None, s.encode(), ENC)

    def _cfstr_to_py(cfs):
        if not cfs:
            return None
        length = cf.CFStringGetLength(cfs)
        buf = ctypes.create_string_buffer(length * 4 + 1)
        if cf.CFStringGetCString(cfs, buf, length * 4 + 1, ENC):
            return buf.value.decode()
        return None

    def _cfnum_to_int(cfn):
        if not cfn:
            return None
        val = ctypes.c_int64(0)
        for typ in (3, 14, 15, 16, 4):
            if cf.CFNumberGetValue(cfn, typ, ctypes.byref(val)):
                return val.value
        return None

    k_workspace = _cfstr("kCGWindowWorkspace")
    k_owner = _cfstr("kCGWindowOwnerName")
    k_name = _cfstr("kCGWindowName")
    k_layer = _cfstr("kCGWindowLayer")
    k_number = _cfstr("kCGWindowNumber")

    try:
        count = cf.CFArrayGetCount(window_list)
        windows = []
        for i in range(count):
            item = cf.CFArrayGetValueAtIndex(window_list, i)
            if not item:
                continue

            layer = _cfnum_to_int(cf.CFDictionaryGetValue(item, k_layer))
            if layer is None or layer != 0:
                continue

            ws = _cfnum_to_int(cf.CFDictionaryGetValue(item, k_workspace))
            owner = _cfstr_to_py(cf.CFDictionaryGetValue(item, k_owner))
            title = _cfstr_to_py(cf.CFDictionaryGetValue(item, k_name))
            wid = _cfnum_to_int(cf.CFDictionaryGetValue(item, k_number))

            if not owner or owner in _SYSTEM_PROCESSES:
                continue

            windows.append({
                "id": wid or 0,
                "workspace": ws or 1,
                "owner": owner,
                "title": title.strip() if title else "(untitled)",
            })
        return windows
    finally:
        cf.CFRelease(k_workspace)
        cf.CFRelease(k_owner)
        cf.CFRelease(k_name)
        cf.CFRelease(k_layer)
        cf.CFRelease(k_number)
        cf.CFRelease(window_list)


def _workspace_list_cg(type: str, desktop_index: int | None) -> str:
    windows = _cg_window_info()
    if not windows:
        return "No windows found."

    workspaces = sorted(set(w["workspace"] for w in windows))

    if type == "desktops":
        return "\n".join(f"Desktop {ws}" for ws in workspaces) or "No desktops found."

    if type == "desktop_windows":
        filtered = [w for w in windows if w["workspace"] == desktop_index]
        if not filtered:
            return f"Desktop {desktop_index}: (no windows)"
        parts = [f"Desktop {desktop_index}:"]
        parts += [f"  {w['owner']} — {w['title']}" for w in filtered]
        return "\n".join(parts)

    parts = []
    for ws in workspaces:
        parts.append(f"Desktop {ws}:")
        filtered = [w for w in windows if w["workspace"] == ws]
        if not filtered:
            parts.append("  (no windows)")
        else:
            for w in filtered:
                parts.append(f"  {w['owner']} — {w['title']}")
    return "\n".join(parts)


def workspace_list(type: str, desktop_index: int | None = None) -> str:
    if type not in ("desktops", "desktop_windows", "all_windows"):
        return (
            f"Error: type must be 'desktops', 'desktop_windows', "
            f"or 'all_windows', got '{type}'"
        )
    if type == "desktop_windows" and desktop_index is None:
        return "Error: desktop_index is required when type is 'desktop_windows'"

    if _yabai_available():
        try:
            return _workspace_list_yabai(type, desktop_index)
        except Exception:
            pass

    try:
        return _workspace_list_cg(type, desktop_index)
    except Exception as e:
        return (
            f"Error: could not query workspace info — {e}. "
            "Install yabai for best results:\n"
            "  brew install koekeishiya/formulae/yabai"
        )


def find_windows_by_name(name: str) -> list[dict]:
    """Find macOS windows whose app name or title matches *name*
    (case-insensitive substring match).  Returns a list of
    ``{"id": int, "app": str, "title": str}`` — one entry per match.

    Tries *yabai* first, falls back to Core Graphics via ctypes.
    """
    name_lower = name.lower()

    if _yabai_available():
        try:
            windows = _run_yabai(["query", "--windows"])
            results = []
            for w in windows:
                if w.get("app") in _SYSTEM_PROCESSES:
                    continue
                app = (w.get("app") or "").lower()
                title = (w.get("title") or "").lower()
                combined = f"{app} — {title}"
                if name_lower in app or name_lower in title or name_lower in combined:
                    results.append({
                        "id": w.get("id", 0),
                        "app": w.get("app", ""),
                        "title": (w.get("title") or "").strip() or "(untitled)",
                    })
            titled = [r for r in results if r["title"] != "(untitled)"]
            return titled or results
        except Exception:
            pass

    windows = _cg_window_info()
    results = []
    for w in windows:
        app = (w.get("owner") or "").lower()
        title = (w.get("title") or "").lower()
        combined = f"{app} — {title}"
        if name_lower in app or name_lower in title or name_lower in combined:
            results.append({
                "id": w.get("id", 0),
                "app": w.get("owner", ""),
                "title": w.get("title", "(untitled)"),
            })
    titled = [r for r in results if r["title"] != "(untitled)"]
    return titled or results


# ── Clipboard (macOS pasteboard) tools ─────────────────────────────

def clipboard_read() -> str:
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, timeout=5)
    except subprocess.TimeoutExpired:
        return "Error: pbpaste timed out after 5s."
    except FileNotFoundError:
        return "Error: pbpaste not found (not on macOS?)."
    except Exception as e:
        return f"Error: pbpaste failed — {e}"

    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown error"
        return f"Error: pbpaste failed (exit {result.returncode}): {stderr}"

    try:
        content = result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return (
            f"Clipboard contains non-text data ({len(result.stdout)} bytes). "
            "Use file_system tools to save it."
        )

    if not content:
        return "(clipboard is empty)"

    if len(content) > 10_000:
        remaining = len(content) - 10_000
        content = content[:10_000] + f"\n… (truncated, {remaining} more chars)"

    return content


def clipboard_write(text: str) -> str:
    try:
        result = subprocess.run(
            ["pbcopy"], input=text.encode("utf-8"),
            capture_output=True, timeout=5,
        )
    except subprocess.TimeoutExpired:
        return "Error: pbcopy timed out after 5s."
    except FileNotFoundError:
        return "Error: pbcopy not found (not on macOS?)."
    except Exception as e:
        return f"Error: pbcopy failed — {e}"

    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown error"
        return f"Error: pbcopy failed (exit {result.returncode}): {stderr}"

    return f"Copied to clipboard ({len(text)} chars)."


# ── Heartbeats ──────────────────────────────────────────────────────────

HEARTBEATS_PATH = Path("memory/dynamic/heartbeats.json")
_heartbeats_lock = threading.RLock()


def load_heartbeats() -> list[dict]:
    if not HEARTBEATS_PATH.exists():
        return []
    with open(HEARTBEATS_PATH) as f:
        return json.load(f)


def save_heartbeats(hbs: list[dict]) -> None:
    HEARTBEATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HEARTBEATS_PATH, "w") as f:
        json.dump(hbs, f, indent=2)


def _parse_heartbeat_time(time_str: str) -> str | None:
    try:
        dt = datetime.fromisoformat(time_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        pass
    m = re.match(r"in\s+(\d+)\s+(second|minute|hour|day)s?", time_str.lower().strip())
    if m:
        num = int(m.group(1))
        unit = m.group(2).rstrip("s") + "s"
        dt = datetime.now(timezone.utc) + timedelta(**{unit: num})
        return dt.isoformat()
    return None


_INTERVAL_PATTERNS = [
    (r"^daily$", timedelta(days=1)),
    (r"^hourly$", timedelta(hours=1)),
    (r"^every\s+(\d+)\s+minutes?$", None),
    (r"^every\s+(\d+)\s+hours?$", None),
    (r"^every\s+(\d+)\s+days?$", None),
]

def _parse_interval(repeat: str) -> timedelta | None:
    clean = repeat.lower().strip()
    for pattern, fixed in _INTERVAL_PATTERNS:
        m = re.match(pattern, clean)
        if not m:
            continue
        if fixed is not None:
            return fixed
        num = int(m.group(1))
        if "minute" in pattern:
            return timedelta(minutes=num)
        elif "hour" in pattern:
            return timedelta(hours=num)
        elif "day" in pattern:
            return timedelta(days=num)
    return None


def heartbeats_schedule(name: str, time: str, repeat: str | None = None) -> str:
    iso_time = _parse_heartbeat_time(time)
    if not iso_time:
        return (
            f"Error: invalid time format '{time}'. "
            "Use ISO datetime (e.g. '2026-07-01T14:30:00') "
            "or relative time (e.g. 'in 5 minutes', 'in 2 hours', 'in 1 day')."
        )
    if repeat:
        if not _parse_interval(repeat):
            return (
                f"Error: invalid repeat format '{repeat}'. "
                "Accepts 'daily', 'hourly', or 'every X minutes/hours/days'."
            )
    hb = {
        "id": f"hb_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}",
        "name": name,
        "time_of_occurrence": iso_time,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    if repeat:
        hb["repeat"] = repeat
    with _heartbeats_lock:
        hbs = load_heartbeats()
        hbs.append(hb)
        save_heartbeats(hbs)
    msg = f"Scheduled heartbeat '{hb['id']}' at {iso_time}: {name}"
    if repeat:
        msg += f" (repeats {repeat})"
    return msg


def heartbeats_cancel(id: str | None = None, name: str | None = None) -> str:
    with _heartbeats_lock:
        hbs = load_heartbeats()
        if id:
            for hb in hbs:
                if hb["id"] == id:
                    if hb["status"] in ("success", "fail"):
                        return f"Heartbeat '{id}' already completed with status '{hb['status']}'"
                    hb["status"] = "fail"
                    save_heartbeats(hbs)
                    return f"Cancelled heartbeat '{id}'"
            return f"Error: heartbeat '{id}' not found"
        if name:
            pending = [h for h in hbs if h.get("name") == name and h.get("status") == "pending"]
            if not pending:
                return f"No pending heartbeats found with name '{name}'"
            for hb in pending:
                hb["status"] = "fail"
            save_heartbeats(hbs)
            count = len(pending)
            return f"Cancelled {count} heartbeat(s) with name '{name}'"
        return "Error: provide either 'id' or 'name' to cancel."


def heartbeats_list(
    status: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
) -> str:
    with _heartbeats_lock:
        hbs = load_heartbeats()
    if status:
        hbs = [h for h in hbs if h.get("status") == status]
    if from_time:
        try:
            ft = datetime.fromisoformat(from_time)
            hbs = [h for h in hbs if datetime.fromisoformat(h["time_of_occurrence"]) >= ft]
        except ValueError:
            return f"Error: invalid from_time format: {from_time}"
    if to_time:
        try:
            tt = datetime.fromisoformat(to_time)
            hbs = [h for h in hbs if datetime.fromisoformat(h["time_of_occurrence"]) <= tt]
        except ValueError:
            return f"Error: invalid to_time format: {to_time}"
    if not hbs:
        return "No heartbeats found matching the given filters."
    lines = ["Heartbeats:"]
    for hb in hbs:
        repeat_info = f" (repeats {hb['repeat']})" if hb.get("repeat") else ""
        lines.append(f"  [{hb['status']}] {hb['id']}: {hb['name'][:60]} \u2192 {hb['time_of_occurrence']}{repeat_info}")
    return "\n".join(lines)


# ── Discord ─────────────────────────────────────────────────────────────


def discord_send(channel_id: str, message: str) -> str:
    import asyncio
    import skills.discord_bot as _db

    bot = _db._discord_bot_ref
    if bot is None:
        return "Error: Discord bot is not connected."

    async def _send():
        channel = bot.get_channel(int(channel_id))
        if channel:
            await channel.send(message)
        else:
            from discord.http import Route

            route = Route(
                "POST",
                "/channels/{channel_id}/messages",
                channel_id=int(channel_id),
            )
            await bot.http.request(route, json={"content": message})

    try:
        future = asyncio.run_coroutine_threadsafe(_send(), bot.loop)
        future.result(timeout=30)
        return f"Message sent to Discord channel {channel_id}"
    except Exception as e:
        return f"Error sending Discord message: {e}"
