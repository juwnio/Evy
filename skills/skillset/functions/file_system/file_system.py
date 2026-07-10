import json
import platform
import stat as stat_module
from datetime import datetime
from pathlib import Path


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


def _validate_write_path(path: str) -> str | None:
    resolved = _resolve_path(path)
    home = _get_home()
    if not str(resolved).startswith(str(home)):
        return f"Error: path '{resolved}' is outside the allowed directory ({home})."
    return None


def _format_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}" if unit != "B" else f"{size}B"
        size /= 1024
    return f"{size:.1f}TB"


def _format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _permissions_str(mode: int) -> str:
    bits = stat_module.filemode(mode)
    return bits


def file_system_read(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    lines: list[int] | None = None,
    max_chars: int = 200000,
) -> str:
    try:
        resolved = _resolve_path(path)
        if not resolved.exists():
            return f"Error: file not found: {resolved}"
        if not resolved.is_file():
            return f"Error: not a file: {resolved}"

        total_bytes = resolved.stat().st_size
        text = resolved.read_text(encoding="utf-8", errors="replace")

        if lines is not None:
            all_lines = text.splitlines()
            total_lines = len(all_lines)
            selected = []
            for lineno in sorted(set(lines)):
                if 1 <= lineno <= total_lines:
                    selected.append(f"{lineno:>6d}: {all_lines[lineno - 1]}")
                else:
                    selected.append(f"{lineno:>6d}: [line out of range — file has {total_lines} lines]")
            text = "\n".join(selected)
        elif start_line is not None or end_line is not None:
            split_lines = text.splitlines(keepends=True)
            total_lines = len(split_lines)
            start = (start_line - 1) if start_line is not None else 0
            end = end_line if end_line is not None else total_lines
            text = "".join(split_lines[start:end])

        total_chars = len(text)
        truncated = False
        omitted = 0
        if total_chars > max_chars:
            text = text[:max_chars]
            omitted = total_chars - max_chars
            truncated = True

        token_est = max(1, len(text) // 4)

        result = [
            f"File: {resolved}",
            f"Size: {_format_size(total_bytes)} ({total_bytes} bytes)",
            f"Chars returned: {len(text)}",
            f"~{token_est} tokens (est)",
        ]
        if truncated:
            result.append(
                f"[truncated: omitted ~{omitted} chars (~{omitted // 4} tokens est)]"
            )
        result.append("")
        result.append(text)
        return "\n".join(result)
    except PermissionError:
        return f"Error: permission denied reading: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


def file_system_list(path: str | None = None) -> str:
    try:
        resolved = _resolve_path(path) if path else _get_home()
        if not resolved.exists():
            return f"Error: path not found: {resolved}"
        if not resolved.is_dir():
            return f"Error: not a directory: {resolved}"

        entries = sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = [f"Directory: {resolved}\n"]
        for entry in entries:
            st = entry.stat(follow_symlinks=False)
            kind = "dir" if entry.is_dir() else "file"
            size = _format_size(st.st_size) if entry.is_file() else "-"
            mtime = _format_time(st.st_mtime)
            lines.append(f"{kind:4s} {_permissions_str(st.st_mode):10s} {size:>8s}  {mtime}  {entry.name}")
        total = len(entries)
        lines.append(f"\n{total} entr{'y' if total == 1 else 'ies'}")
        return "\n".join(lines)
    except PermissionError:
        return f"Error: permission denied listing: {path}"
    except Exception as e:
        return f"Error listing directory: {e}"


def file_system_search(pattern: str, root: str | None = None) -> str:
    try:
        resolved_root = _resolve_path(root) if root else _get_home()
        if not resolved_root.exists():
            return f"Error: root not found: {resolved_root}"
        if not resolved_root.is_dir():
            return f"Error: not a directory: {resolved_root}"

        matches = sorted(resolved_root.rglob(pattern))
        if not matches:
            return f"No files matching '{pattern}' found under {resolved_root}"

        lines = [f"Search: {pattern} under {resolved_root}\n"]
        for m in matches:
            size = _format_size(m.stat(follow_symlinks=False).st_size)
            rel = m.relative_to(resolved_root)
            lines.append(f"{size:>8s}  {rel}")
        lines.append(f"\n{len(matches)} match{'es' if len(matches) != 1 else ''}")
        return "\n".join(lines)
    except PermissionError:
        return f"Error: permission denied searching: {root or _get_home()}"
    except Exception as e:
        return f"Error searching files: {e}"


def file_system_info(path: str) -> str:
    try:
        resolved = _resolve_path(path)
        if not resolved.exists():
            return f"Error: path not found: {resolved}"

        st = resolved.stat(follow_symlinks=False)
        lines = [
            f"Path: {resolved}",
            f"Type: {'directory' if resolved.is_dir() else 'symlink' if resolved.is_symlink() else 'file'}",
            f"Size: {_format_size(st.st_size)} ({st.st_size} bytes)",
            f"Modified: {_format_time(st.st_mtime)}",
            f"Created: {_format_time(st.st_ctime)}",
            f"Permissions: {_permissions_str(st.st_mode)} ({oct(st.st_mode)})",
        ]
        return "\n".join(lines)
    except PermissionError:
        return f"Error: permission denied accessing: {path}"
    except Exception as e:
        return f"Error getting file info: {e}"


def file_system_write(path: str, content: str) -> str:
    error = _validate_write_path(path)
    if error:
        return error
    try:
        resolved = _resolve_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {resolved}"
    except PermissionError:
        return f"Error: permission denied writing: {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def file_system_append(path: str, content: str) -> str:
    error = _validate_write_path(path)
    if error:
        return error
    try:
        resolved = _resolve_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with resolved.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended {len(content)} chars to {resolved}"
    except PermissionError:
        return f"Error: permission denied appending: {path}"
    except Exception as e:
        return f"Error appending to file: {e}"


def file_system_create(path: str, content: str = "") -> str:
    error = _validate_write_path(path)
    if error:
        return error
    try:
        resolved = _resolve_path(path)
        if resolved.exists():
            return f"Error: file already exists: {resolved} (use file_system_write to overwrite)"
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        if content:
            return f"Created {resolved} with {len(content)} chars"
        return f"Created empty file {resolved}"
    except PermissionError:
        return f"Error: permission denied creating: {path}"
    except Exception as e:
        return f"Error creating file: {e}"


def file_system_trash(path: str) -> str:
    error = _validate_write_path(path)
    if error:
        return error
    try:
        resolved = _resolve_path(path)
        if not resolved.exists():
            return f"Error: path not found: {resolved}"

        if platform.system() != "Darwin":
            resolved.unlink()
            return f"Deleted file {resolved}"

        import shutil
        trash_dir = Path.home() / ".Trash"
        trash_dir.mkdir(exist_ok=True)
        dest = trash_dir / resolved.name
        counter = 1
        while dest.exists():
            stem = resolved.stem
            suffix = resolved.suffix
            if resolved.is_dir() and not suffix:
                dest = trash_dir / f"{stem}_{counter}"
            else:
                dest = trash_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        shutil.move(str(resolved), str(dest))
        return f"Moved to Trash: {dest}"
    except PermissionError:
        return f"Error: permission denied trashing: {path}"
    except Exception as e:
        return f"Error trashing: {e}"


def file_system_patch(path: str, old_text: str, new_text: str) -> str:
    error = _validate_write_path(path)
    if error:
        return error
    try:
        resolved = _resolve_path(path)
        if not resolved.exists():
            return f"Error: file not found: {resolved}"
        if not resolved.is_file():
            return f"Error: not a file: {resolved}"

        content = resolved.read_text(encoding="utf-8", errors="replace")
        if old_text not in content:
            preview = content[:200].replace("\n", "\\n")
            return (
                f"Error: old_text not found in {resolved}.\n"
                f"First ~200 chars of file:\n{preview}"
            )

        new_content = content.replace(old_text, new_text, 1)
        resolved.write_text(new_content, encoding="utf-8")
        old_len = len(old_text)
        new_len = len(new_text)
        diff = new_len - old_len
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        return f"Patched {resolved} ({old_len} chars -> {new_len} chars, {diff_str} chars)"
    except PermissionError:
        return f"Error: permission denied patching: {path}"
    except Exception as e:
        return f"Error patching file: {e}"
