import json
import os
import subprocess

_MAX_OUTPUT = 4000
_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 60

_BLOCKED_COMMANDS = {
    "sudo", "rm", "chmod", "chown", "dd", "mkfs", "shutdown",
    "reboot", "init", "kill", "pkill", "poweroff", "halt",
}

_WRITE_OPERATORS = {">", ">>", "tee"}

_SAFE_HOME_KEY = "home_dir"
_FALLBACK_HOME = "~/Documents"


def _get_home() -> str:
    try:
        with open("utilities/config.json") as f:
            cfg = json.load(f)
        home = cfg.get(_SAFE_HOME_KEY)
        if home:
            return os.path.expanduser(home)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return os.path.expanduser(_FALLBACK_HOME)


def _is_write_operation(tokens: list[str]) -> bool:
    for token in tokens:
        stripped = token.strip()
        if stripped in _WRITE_OPERATORS:
            return True
        if stripped.startswith(">"):
            return True
    return False


def _has_path_escape(command: str, home: str) -> bool:
    for token in command.split():
        t = token.strip()
        if t.startswith("..") or "/.." in t:
            return True
        if os.path.isabs(t) and not t.startswith(home):
            return True
    return False


def _is_chained(command: str) -> bool:
    unquoted = ""
    in_single = False
    in_double = False
    for ch in command:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            unquoted += ch
    for meta in (";", "`", "$(", "||", "&&"):
        if meta in unquoted:
            return True
    return False


def shell_run(command: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    cmd = command.strip()
    if not cmd:
        return "Error: empty command."

    timeout = min(timeout, _MAX_TIMEOUT)
    home = _get_home()

    if _is_chained(cmd):
        return (
            "Error: chained commands (; ` $( || &&) are not allowed. "
            "Use pipes (|) to connect commands instead."
        )

    tokens = cmd.split()
    first_word = tokens[0] if tokens else ""

    if first_word in _BLOCKED_COMMANDS:
        return f"Error: '{first_word}' is blocked for security."

    if _is_write_operation(tokens):
        return "Error: file write operations (>, >>, tee) are not allowed."

    if _has_path_escape(cmd, home):
        return (
            f"Error: path traversal detected. "
            f"Commands are restricted to {home}."
        )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            shell=True,
            timeout=timeout,
            text=True,
            cwd=home,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s."
    except Exception as e:
        return f"Error: {e}"

    output = result.stdout or ""
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"

    if len(output) > _MAX_OUTPUT:
        remaining = len(output) - _MAX_OUTPUT
        output = output[:_MAX_OUTPUT] + f"\n… (truncated, {remaining} more chars)"

    if result.returncode != 0:
        output = f"Exit code: {result.returncode}\n{output}"

    return output.strip() or "(empty output)"
