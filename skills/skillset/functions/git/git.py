import json
import os
import subprocess
import tempfile
import stat
import urllib.request
import urllib.error
from dotenv import load_dotenv


def _get_home() -> str:
    try:
        with open("utilities/config.json") as f:
            cfg = json.load(f)
        home = cfg.get("home_dir")
        if home:
            return os.path.expanduser(home)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return os.path.expanduser("~/Documents")


def _find_repo(path: str | None = None) -> str | None:
    p = os.path.abspath(path or _get_home())
    while True:
        if os.path.isdir(os.path.join(p, ".git")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def _git(*args: str, path: str | None = None, token: str | None = None) -> str:
    repo = _find_repo(path)
    if not repo:
        return "Error: not inside a Git repository."
    env = os.environ.copy()
    askpass = None
    if token:
        fd, askpass_path = tempfile.mkstemp(prefix="git-askpass-")
        with os.fdopen(fd, "w") as f:
            f.write("#!/bin/sh\n")
            f.write('if [ "$1" = "Password:" ] || [ "$1" = "Password for \'https://eveagnt-byte@github.com\':" ]; then\n')
            f.write(f'  echo "{token}"\n')
            f.write("else\n")
            f.write('  echo "eveagnt-byte"\n')
            f.write("fi\n")
        os.chmod(askpass_path, stat.S_IRWXU)
        env["GIT_ASKPASS"] = askpass_path
        askpass = askpass_path
    try:
        r = subprocess.run(
            ["git"] + list(args),
            capture_output=True,
            text=True,
            timeout=30,
            cwd=repo,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return "Error: git command timed out after 30s."
    except FileNotFoundError:
        return "Error: git is not installed."
    except Exception as e:
        return f"Error: {e}"
    finally:
        if askpass and os.path.exists(askpass):
            os.unlink(askpass)

    output = r.stdout or ""
    if r.stderr:
        output += f"\n[stderr]\n{r.stderr}"
    if r.returncode != 0:
        output = f"Exit code: {r.returncode}\n{output}"
    return output.strip() or "(empty output)"


def _current_branch(path: str | None = None) -> str | None:
    repo = _find_repo(path)
    if not repo:
        return None
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=repo,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _get_token() -> str | None:
    load_dotenv()
    return os.environ.get("github-token") or None


def _get_remote_url(repo: str, remote: str = "origin") -> str | None:
    try:
        r = subprocess.run(
            ["git", "remote", "get-url", remote],
            capture_output=True, text=True, timeout=10, cwd=repo,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _parse_github_url(url: str) -> tuple[str, str] | None:
    import re
    m = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2)
    return None


def _github_api(method: str, path: str, data: dict | None = None, token: str | None = None) -> dict:
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "eveagnt-byte",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        try:
            return json.loads(error_body)
        except json.JSONDecodeError:
            return {"message": error_body}


def git_status(path: str | None = None) -> str:
    return _git("status", path=path)


def git_diff(path: str | None = None, staged: bool = False) -> str:
    args = ["diff"]
    if staged:
        args.append("--staged")
    return _git(*args, path=path)


def git_log(path: str | None = None, count: int = 10, file: str | None = None) -> str:
    args = ["log", "--oneline", f"-{count}"]
    if file:
        args.extend(["--", file])
    return _git(*args, path=path)


def git_branch(path: str | None = None, all: bool = False) -> str:
    args = ["branch"]
    if all:
        args.append("-a")
    return _git(*args, path=path)


def git_pull(path: str | None = None, remote: str | None = None, branch: str | None = None) -> str:
    args = ["pull"]
    if remote:
        args.append(remote)
        if branch:
            args.append(branch)
    return _git(*args, path=path)


def git_checkout(path: str | None = None, branch: str = "", create: bool = False) -> str:
    if not branch.strip():
        return "Error: branch name is required."
    args = ["checkout"]
    if create:
        args.append("-b")
    args.append(branch)
    return _git(*args, path=path)


def git_commit(path: str | None = None, message: str = "") -> str:
    if not message.strip():
        return "Error: commit message cannot be empty."
    if "--amend" in message:
        return "Error: --amend is not allowed in commit messages."
    stage = _git("add", "-A", path=path)
    if stage.startswith("Error"):
        return stage
    return _git("commit", "-m", message, path=path)


def git_create_pr(path: str | None = None, title: str = "", body: str = "", branch: str | None = None, base: str = "main") -> str:
    if not title.strip():
        return "Error: PR title is required."

    token = _get_token()
    if not token:
        return "Error: GitHub token not found. Add github-token to .env"

    repo = _find_repo(path)
    if not repo:
        return "Error: not inside a Git repository."

    remote_url = _get_remote_url(repo)
    if not remote_url:
        return "Error: could not determine remote URL."

    parsed = _parse_github_url(remote_url)
    if not parsed:
        return f"Error: unsupported remote URL format: {remote_url}"
    owner, repo_name = parsed

    current_branch = branch or _current_branch(path)
    if not current_branch:
        return "Error: could not determine current branch. Specify branch."

    # Push the branch first
    push_args = ["push", "-u", "origin", current_branch]
    push_result = _git(*push_args, path=path, token=token)
    if push_result.startswith("Error"):
        return push_result

    # Create the PR via GitHub API
    data = {"title": title, "head": current_branch, "base": base}
    if body.strip():
        data["body"] = body
    result = _github_api("POST", f"/repos/{owner}/{repo_name}/pulls", data, token)

    if "html_url" in result:
        return f"PR created: {result['html_url']}"
    if "message" in result:
        return f"Error creating PR: {result['message']}"
    return f"Error creating PR: {json.dumps(result)}"
