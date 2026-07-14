from __future__ import annotations

import difflib
import json
import os
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rich.text import Text

from textual.worker import Worker
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Provider
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    Label,
    Markdown,
    Static,
    TextArea,
)

from utilities.scripts.states import TOOL_FRAMES
from utilities.scripts.google_auth import list_connections, add_connection

import gateway as _gateway_mod
from gateway import (
    call_evy_stream,
    load_config,
    load_memory,
)
from utilities.scripts.conversion import count_tokens
from skills.primary import load_heartbeats, save_heartbeats, _heartbeats_lock, _parse_interval
from skills.skillset.functions.browser import browser as _browser_mod

BRAIN_PATH = "memory/dynamic/brain.json"

WATERMARK = """\
########################################################################
#####################+%#################################################
###################=+*###############%###%##############################
##################*+=##+#######-##=###############################%#####
#################++=#=#-###-=+-+-#######################################
###############+*++###-====-==::-+##*###+###############################
##############+++*+=--:===#*=:-==#++-#+=#####################%####%#####
######+#####=*+**+###+::=++#*+%#-*+::=:#+##=##=#########################
#####%++#*++*#*****+-==++=%%+=+=--=:::+##::+-:#+=+#############*#*######
#####++++++#*#********%%%%%%%%%#--:=:::-##=:=::##=#-###########*#####%##
#####+++++##*####*%%%%%%###%%#%%%%%#-#+#+=::::-#=::=#=*#################
#####*++++*-::=###%%#%%%%%%%#%#%#######+#=+#-+==+=::###%=####=++++++####
#####+++###+:::*%%%%%%%%%%%#%##%###########==###=+#=-=#######=++++++####
############+::%%%%%%%%%%#%####%#%###%**#*##%=+++=+#-*#######+++++++####
##############%%%%%%%%%%%%##%#%%###%###-:#*###%###+#+########=++++++####
#############%#%%%%%%%#####+####%%##%%##**######%############-++++++####
##############%%%%%###*#=#*::=+-###%###%::*#%#%#%###########%#++++++####
##############%#%%###:=#=**#---**=#######-#%#%##%#%##%##################
#############%%%%#%##+::*===*+**=--*##*##%:#%%#%%%#%%##########*%#######
#############%%%%%%###-::*:=::::::::=+%=#=+##%%%%+==##%#################
#########%###%%%%%#%#*-*+:::::::::::::*=#=***#%%##*##*#*%%##############
##############%%#%###*---+=*::::::::::***********%%##%####%#############
#########%####%%##%%###===:-::::-::-:-**#%%#####***##*#%#####%##########
######%###%##%%#%#%#**##***--:::===-+########%####*###**#%#%##%####%####
##############%##%%#***=::::::::::::-::######%#%**#####=+%###%#########
###############%###%##:::::::::::::-:#:-#############*#####+%#%%####%=**
####################%:::::::::+:::-:+:-#:*######%##########=+%%##%+=++**
#####%#############%::::-%%####--::=:+:*#:=###-=*##+##=#+##**+###***++**
################%##::::-+%####-:---:=:::*++-+*+-*#####=*##++##%#+#-+****
########%#%##%%%##::::=++*=*-+=::--+=:--:---=*-+=-#####+##+*##=+*=#**=**
##########%%####+-*+=+:**=+-*+:-====+=+=:-:::-+++=--##%####+##++*+#-+*:*
########%%####****++:::=#=+=*--::==-====-=::-:-+=-:::::#%###****=**=***#
#######%#%###*#:::::::########*#::----++===-:::+=-:::::#%####*=+++:#=###
###########***::::::::########+###::--*========--::--==%######*#**######
#########%#*=#-:::::-=####=########-==--------::-=:--##########*#*=#####
##%#####%##**#-:-::-+######%######=+=::-:-:::-**+:+#############*#*##%#+
#########%+###---:-#%#+#######%%####-:#*+*+*=+===*#%##############*#=*+*
##############+---%%#####**###%#%%####%****=:+**=*##############*==****=
##########**##=###########*############=*+*.**=.#+**+*=++***-*+**+*****-

"""

# ── TCSS ──────────────────────────────────────────────────────────────────

APP_CSS = """
$accent: #eee;
$accent2: #ccc;
$evy-user: #fff;
$evy-dim: #666;

EvyApp {
    background: #111;
}

#main-area {
    height: 1fr;
}

#chat-pane {
    background: #111;
    border: solid $evy-dim;
    height: 1fr;
    width: 1fr;
    overflow-x: hidden;
}

#chat-body {
    height: 1fr;
    position: relative;
}

#watermark {
    position: absolute;
    width: 100%;
    height: 100%;
    opacity: 0.35;
    color: #444;
    text-align: center;
    overflow: hidden;
    padding: 1 2;
}

#watermark.-hidden {
    display: none;
}

#thinking-content {
    display: none;
    padding: 0 1;
    background: $surface;
    border-top: thick #444;
    overflow-y: auto;
    max-height: 15;
}
#thinking-content.-visible {
    display: block;
}

#chat-messages {
    padding: 0 1;
    overflow-x: hidden;
    overflow-y: scroll;
    scrollbar-size: 0 0;
    height: 1fr;
}

.user-message {
    color: $evy-user;
    margin: 0 0 1 0;
}

.evy-message {
    color: white;
    margin: 0 0 1 0;
}

.evy-message MarkdownTable {
    margin: 1 0;
    width: 100%;
}

.evy-message MarkdownTH {
    background: #333;
    color: #eee;
    text-style: bold;
    padding: 0 1;
}

.evy-message MarkdownTD {
    padding: 0 1;
}

.system-message {
    color: $evy-dim;
    margin: 0 0 1 0;
}

.discord-message {
    color: #a855f7;
    margin: 0 0 1 0;
}

.tool-widget {
    margin: 0 0 1 0;
}

.tool-widget.-tool {
    background: #333;
    padding: 0 1;
}

.tool-widget-body {
    display: none;
    padding: 0 1 0 2;
    color: $evy-dim;
    max-height: 10;
    overflow-y: scroll;
    border-left: solid $evy-dim;
    margin: 0 0 0 2;
}

.tool-widget-body.-visible {
    display: block;
}

#activity-panel {
    background: #1a1a1a;
    border: solid $evy-dim;
    width: 48;
    display: none;
    layout: vertical;
}

#activity-panel.-visible {
    display: block;
}

#commands-section {
    height: 1fr;
    overflow-y: scroll;
    padding: 0 1;
}

#commands-title {
    color: $accent;
    text-style: bold;
    padding: 0 1;
    height: 1;
}

#commands-list {
    height: auto;
    overflow-y: auto;
}

.command-entry {
    padding: 0 1;
    height: 1;
}

.segment-header {
    padding: 0 1;
    height: 1;
    color: $evy-dim;
    text-style: bold;
}

.command-entry .command-key {
    color: $evy-dim;
}

.command-entry.-enabled .command-status {
    color: $accent;
}

.command-entry.-disabled .command-status {
    color: $evy-dim;
}

#input-bar {
    height: 5;
    padding: 0 1;
    background: #1a1a1a;
    border: solid $evy-dim;
}

#input-bar Input {
    background: #2a2a2a;
    color: #eee;
    border: none;
    padding: 1 1;
}

#input-bar Input:focus {
    border: none;
}

#attach-bar {
    height: auto;
    min-height: 2;
    padding: 0 1;
    background: #1a1a1a;
    border-top: solid $evy-dim;
    display: none;
    align: left middle;
}
#attach-bar.-visible {
    display: block;
}
.attach-chip {
    margin: 0 1 0 0;
    background: #2a2a2a;
    color: $accent;
    border: none;
    padding: 0 1;
}
.attach-chip:hover {
    background: $evy-dim;
}

#brain-occupation {
    height: 1;
    padding: 0 1;
    background: #1a1a1a;
}

#brain-cancel {
    width: auto;
    color: $evy-dim;
}

#brain-label {
    width: 1fr;
    text-align: center;
    color: $accent;
}

#brain-toggle {
    width: auto;
    color: $evy-dim;
}

#chat-header {
    height: 1;
    background: #1a1a1a;
    padding: 0 1;
}

.chat-header-item {
    width: 1fr;
    text-align: center;
    color: #eee;
}

.chat-header-sep {
    width: 3;
    text-align: center;
    color: #666;
}

.chat-user {
    color: $evy-user;
}

.chat-evy {
    color: $accent2;
}

.chat-dim {
    color: $evy-dim;
}

.chat-system {
    color: $accent;
}

/* ── State Modal ───────────────────────────────────────────────────── */

#state-modal {
    align: center middle;
}

#state-dialog {
    width: 60;
    height: auto;
    padding: 2;
    background: #1a1a1a;
    border: thick #555;
}

/* ── Config Modal ──────────────────────────────────────────── */

#config-modal {
    align: center middle;
}

#config-dialog {
    width: 70;
    height: 55%;
    padding: 0 1;
    background: #1a1a1a;
    border: thick #555;
}

#config-dialog > Label {
    margin-bottom: 0;
}

#config-editor {
    height: 1fr;
    margin-bottom: 0;
    border: solid $evy-dim;
}

#config-buttons {
    align: center middle;
}

#config-button-gap {
    width: 1fr;
}
"""

# ── Modals ─────────────────────────────────────────────────────────────────

class StateModal(ModalScreen[None]):
    def compose(self) -> ComposeResult:
        config = load_config()
        lines = []
        for key, value in config.items():
            if key == "ollama-api-key":
                display = f"{value[:8]}..." if value else "(not set)"
                lines.append(f"  {key}: {display}")
            elif isinstance(value, bool):
                status = "yes" if value else "no"
                lines.append(f"  {key}: {status}")
            else:
                lines.append(f"  {key}: {value}")
        active = config.get("cloud-model", "?") if not config.get("local", True) else config.get("model", "?")
        lines.append(f"  active_model: {active}")

        with Vertical(id="state-modal"):
            with Vertical(id="state-dialog"):
                yield Label("[bold]ⓘ  Configuration[/bold]")
                for line in lines:
                    yield Label(f"[dim]{line}[/dim]")
                yield Button("Close", variant="default", id="state-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class ConfigModal(ModalScreen[bool]):
    def compose(self) -> ComposeResult:
        with Vertical(id="config-modal"):
            with Vertical(id="config-dialog"):
                yield Label("[bold]ⓘ  Configuration[/bold]")
                yield TextArea(id="config-editor", language="json", show_line_numbers=True)
                with Horizontal(id="config-buttons"):
                    yield Button("Save", variant="primary", id="config-save")
                    yield Static(id="config-button-gap")
                    yield Button("Cancel", variant="default", id="config-cancel")

    def on_mount(self) -> None:
        config = _load_config()
        self.query_one("#config-editor", TextArea).text = json.dumps(config, indent=2)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config-save":
            try:
                new_config = json.loads(self.query_one("#config-editor", TextArea).text)
                _save_config(new_config)
                self.dismiss(True)
            except json.JSONDecodeError as e:
                self.notify(f"Invalid JSON: {e}", severity="error", timeout=5)
        else:
            self.dismiss(False)


class AddEmailModal(ModalScreen[dict | None]):
    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="state-modal"):
            with Vertical(id="state-dialog"):
                yield Label("[bold]ⓘ  Add Email Connection[/bold]")
                yield Input(placeholder="Email address", id="email-input")
                yield Input(placeholder="App Password (from Gmail)", id="password-input", password=True)
                yield Input(placeholder="Description (e.g. 'Contacting leads')", id="desc-input")
                with Horizontal(id="config-buttons"):
                    yield Button("Save", variant="primary", id="email-save")
                    yield Static(id="config-button-gap")
                    yield Button("Cancel", variant="default", id="email-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "email-save":
            email = self.query_one("#email-input", Input).value.strip()
            password = self.query_one("#password-input", Input).value.strip()
            desc = self.query_one("#desc-input", Input).value.strip()
            if not email or not password or not desc:
                self.notify("All fields are required", severity="error", timeout=3)
                return
            self.dismiss({"email": email, "app_password": password, "description": desc})
        else:
            self.dismiss(None)


# ── Command Palette Provider ───────────────────────────────────────────────

class EvyCommands(Provider):
    async def search(self, query: str) -> None:
        commands: list[tuple[str, str]] = [
            ("/think", "Toggle thinking On/Off"),
            ("/cancel", "Cancel current response"),
            ("/browser", "Toggle browser head/headless"),
            ("/config", "Edit utilities/config.json"),
            ("/state", "Show current configuration"),
            ("/headless", "Set browser to headless mode"),
            ("/head", "Set browser to headed mode"),
            ("/cloud", "Switch to cloud model"),
            ("/local", "Switch to local model"),
            ("/attach", "Open file picker to attach an image"),
            ("/clear", "Clear chat log"),
            ("/export", "Export conversation to file"),
            ("/reset", "Reset brain.json and chat"),
            ("/consol", "Compress brain + episodic memory via LLM"),
            ("/emails", "List configured email connections"),
            ("/?", "Show help"),
            ("Config (Ctrl+S)", "Edit configuration file"),
        ]
        for cmd, desc in commands:
            if not query or query.lower() in cmd.lower() or query.lower() in desc.lower():
                self.add_command(cmd, lambda c=cmd: self.screen.app._handle_command(c), help_text=desc)


# ── Event messages (cross-thread) ──────────────────────────────────────────

class EvyEvent(Message):
    def __init__(self, event: dict) -> None:
        super().__init__()
        self.event = event


# ── Tool Widget ─────────────────────────────────────────────────────────────

class ToolWidget(Static):
    def __init__(self, name: str, icon: str, label: str, kind: str, args: dict | None = None) -> None:
        super().__init__(classes="tool-widget")
        self._name = name
        self._icon = icon
        self._label = label
        self._kind = kind
        self._args = args or {}
        self._expanded = False
        self._spinner_handle = None
        self._frame_index = 0
        self._result = None
        self._status = None
        if kind == "tool":
            self.add_class("-tool")
        self._update_display()

    def _preview(self, text: str, maxlen: int = 50) -> str:
        line = text.split("\n")[0].strip()
        if len(line) > maxlen:
            line = line[: maxlen - 1] + "…"
        return line

    def _main_line(self) -> str:
        if self._result is not None:
            if self._status == "success":
                return f"[dim]\u2192 {self._label}[/dim]"
            elif self._status == "error":
                return f"[bold]\u2717[/bold] [#eee]{self._label}[/#eee]"
            else:
                return f"[dim]\u2717[/dim] [#eee]{self._label}[/#eee]"
        else:
            frame = TOOL_FRAMES[self._frame_index % len(TOOL_FRAMES)]
            return f"[dim]{frame} {self._label}[/dim]"

    def _result_line(self) -> str:
        if self._result is not None:
            return f"↳ [dim]{self._preview(self._result)}[/dim]"
        return ""

    def _update_display(self) -> None:
        if self._kind == "tool" and self._result is not None and self._expanded:
            result = self._result
            if len(result) > 500:
                result = result[:500] + "\n… (truncated)"
            lines = result.split("\n")
            indented = "\n\t".join(lines)
            self.update(f"{self._main_line()}\n{self._result_line()}\n\n[dim]\t{indented}[/dim]")
        elif self._kind == "tool" and self._result is not None:
            self.update(f"{self._main_line()}\n{self._result_line()}")
        else:
            self.update(self._main_line())

    def on_click(self) -> None:
        if self._kind == "tool" and self._result is not None:
            self._expanded = not self._expanded
            self._update_display()

    def set_result(self, result: str, status: str) -> None:
        self._result = result
        self._status = status
        if self._spinner_handle:
            self._spinner_handle.stop()
            self._spinner_handle = None
        if self._kind == "tool":
            self.add_class("-clickable")
        self._update_display()

    def reuse(self) -> None:
        if self._spinner_handle:
            self._spinner_handle.stop()
            self._spinner_handle = None
        self._result = None
        self._status = None
        self._frame_index = 0
        self._expanded = False
        self.remove_class("-clickable")
        self.start_spinner()
        self._update_display()

    def start_spinner(self) -> None:
        self._spinner_handle = self.set_interval(0.15, self._tick_spinner)

    def _tick_spinner(self) -> None:
        self._frame_index += 1
        self._update_display()


class FileReadWidget(ToolWidget):
    def _update_display(self) -> None:
        if self._result is not None and self._kind == "tool" and self._expanded:
            self.update(self._format_content())
        else:
            super()._update_display()

    def _format_content(self) -> str:
        result = self._result
        lines = result.split("\n")

        file_path = ""
        for line in lines:
            if line.startswith("File: "):
                file_path = line[6:]
                break

        content_start = 0
        for i, line in enumerate(lines):
            if line == "" and i > 0 and i + 1 < len(lines):
                content_start = i + 1
                break

        clines = lines[content_start:] if content_start < len(lines) else []

        has_prefixes = bool(self._args.get("lines"))
        start_line = self._args.get("start_line", 1)

        rendered = []
        for i, line in enumerate(clines):
            if has_prefixes and line.strip() and ":" in line[:10]:
                num_part, _, rest = line.partition(":")
                rendered.append(f"[dim]{num_part}[/dim]:{rest}")
            else:
                rendered.append(f"[dim]{i + start_line:>6}[/dim]  {line}")

        body = "\n".join(rendered)
        if len(body) > 500:
            body = body[:500] + "\n[dim]… (truncated)[/dim]"

        return f"{self._main_line()}\n{self._result_line()}\n\n[dim]{file_path}[/dim]\n\n{body}"


class FileWriteWidget(ToolWidget):
    def _update_display(self) -> None:
        if self._result is not None and self._kind == "tool" and self._expanded:
            content = self._format_content()
            if content is not None:
                self.update(content)
                return
        super()._update_display()

    def _format_content(self) -> str | None:
        result = self._result
        if result.startswith("Error:"):
            return None

        if self._name == "file_system_patch":
            old_text = self._args.get("old_text", "")
            new_text = self._args.get("new_text", "")
            diff = difflib.Differ()
            dlines = list(diff.compare(old_text.splitlines(), new_text.splitlines()))
            body_lines = []
            for line in dlines:
                if line.startswith("  "):
                    body_lines.append(f"[dim]  {line[2:]}[/dim]")
                elif line.startswith("- "):
                    body_lines.append(f"[#eee on #333]- {line[2:]}[/#eee on #333]")
                elif line.startswith("+ "):
                    body_lines.append(f"[#eee on #555]+ {line[2:]}[/#eee on #555]")
            body = "\n".join(body_lines)
        else:
            content = self._args.get("content", "")
            body_lines = [
                f"[#eee on #555]+ {line}[/#eee on #555]"
                for line in content.split("\n")
            ]
            body = "\n".join(body_lines)

        if len(body) > 500:
            body = body[:500] + "\n[dim]… (truncated)[/dim]"

        return f"{self._main_line()}\n{self._result_line()}\n\n{body}"


# ── Main App ───────────────────────────────────────────────────────────────

class EvyApp(App[None]):
    CSS = APP_CSS
    BINDINGS = [
        Binding("escape", "cancel_response", "Cancel", priority=True),
        Binding("ctrl+t", "toggle_thinking", "Think"),
        Binding("ctrl+b", "toggle_browser", "Browser"),
        Binding("ctrl+s", "edit_config", "Config"),
        Binding("ctrl+i", "show_state", "State"),
        Binding("ctrl+q", "quit", "Exit"),
        Binding("ctrl+c", "clear_input", "Clear", priority=True),
        Binding("ctrl+a", "toggle_activity", "Activity", priority=True),
        Binding("cmd+a", "toggle_activity", "Activity"),
        Binding("ctrl+e", "add_email_connection", "Email", priority=True),
        Binding("ctrl+slash", "show_help", "Help"),
    ]
    COMMANDS = {EvyCommands}

    _permission_event: threading.Event | None = None
    _permission_allowed: bool = False
    _thinking_spinner_handle = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-area"):
            with Vertical(id="chat-pane"):
                with Horizontal(id="chat-header"):
                    yield Static(id="user-status", classes="chat-header-item")
                    yield Static("┃", classes="chat-header-sep")
                    yield Static(id="evy-status", classes="chat-header-item")
                    yield Static("┃", classes="chat-header-sep")
                    yield Static("[dim]㆝ Dreaming[/dim]", id="load-status", classes="chat-header-item")
                with Vertical(id="chat-body"):
                    yield VerticalScroll(id="chat-messages")
                    with VerticalScroll(id="thinking-content"):
                        yield Static("", id="thinking-text")
                    yield Static(WATERMARK, id="watermark")
            with Vertical(id="activity-panel"):
                with Vertical(id="commands-section"):
                    yield Label("Commands", id="commands-title")
                    yield VerticalScroll(id="commands-list")
        with Horizontal(id="input-bar"):
            yield Input(placeholder="Converse with Evy…", id="prompt-input")
        with Horizontal(id="attach-bar"):
            pass
        with Horizontal(id="brain-occupation"):
            yield Static("[bold]Cancel[/bold] [dim]esc[/dim]", id="brain-cancel")
            yield Static(id="brain-label")
            yield Static("[dim]Toggle Commands[/dim] [dim]ctrl+a[/dim]", id="brain-toggle")

    def on_mount(self) -> None:
        self.query_one("#prompt-input", Input).focus()
        self._update_email_header()
        self._update_commands()
        self._update_brain_occupation()

        # Inject email connections into gateway context so the model sees them
        conns = list_connections()
        if conns:
            lines = ["Available email connections:"]
            for c in conns:
                lines.append(f"  id={c['id']} email={c['email']} description=\"{c['description']}\"")
            lines.append("Pass connection_id when calling email tools. Omit if only one connection exists.")
            _gateway_mod._email_connections_context = "\n".join(lines)

        # Wire permission handler for TUI
        _gateway_mod._permission_handler = self._tui_permission_handler

        # Start heartbeat scheduler
        self._start_heartbeat_scheduler()

        # Start Discord bot daemon thread
        discord_token = os.environ.get("discord-token")
        if discord_token:
            from skills.discord_bot import DiscordBot

            bot = DiscordBot(
                discord_token,
                self._agent_lock,
                self,
            )
            t = threading.Thread(target=bot.run, daemon=True)
            t.start()

        self._update_discord_header(bool(discord_token))

        # Configure Evy's git identity in this repo
        try:
            cfg = json.load(open("utilities/config.json"))
            name = cfg.get("git_user_name")
            email = cfg.get("git_user_email")
            if name and email:
                subprocess.run(
                    ["git", "config", "user.name", name],
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "config", "user.email", email],
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    capture_output=True,
                )
        except Exception:
            pass

    def _update_email_header(self) -> None:
        conns = list_connections()
        count = len(conns)
        self.query_one("#user-status", Static).update(
            f"⾃ : [bold]{count}[/bold]" if count else "⾃ : [dim]0[/dim]"
        )

    def _update_discord_header(self, connected: bool) -> None:
        status = "[bold]Connected to Discord[/bold]" if connected else "[dim]Not connected to Discord[/dim]"
        self.query_one("#evy-status", Static).update(status)

    def _update_commands(self) -> None:
        config = load_config()
        clist = self.query_one("#commands-list", VerticalScroll)
        clist.remove_children()

        def gap() -> None:
            for _ in range(4):
                clist.mount(Static("", classes="command-entry"))

        def seg(title: str) -> None:
            clist.mount(Static(f"[dim]── {title} ──[/dim]", classes="segment-header"))

        def entry(name: str, key: str = "", status: str = "") -> None:
            parts = [f"  {name}"]
            if key:
                parts.append(f"  [dim]{key}[/dim]")
            if status:
                parts.append(f"  {status}")
            clist.mount(Static("".join(parts), classes="command-entry"))

        # Model & Thinking
        seg("Model & Thinking")
        thinking_on = config.get("thinking", True)
        t_status = "[bold]On[/bold]" if thinking_on else "[dim]Off[/dim]"
        entry("Toggle Think", "ctrl+t", t_status)
        local = config.get("local", True)
        entry("Cloud", "/cloud", "●" if not local else "○")
        entry("Local", "/local", "○" if not local else "●")
        entry("State", "ctrl+i")

        gap()

        # Email
        seg("Email")
        conns = list_connections()
        entry(f"Connections ({len(conns)})", "")
        entry("Add connection", "ctrl+e")
        entry("List connections", "/emails")

        gap()

        # Browser
        seg("Browser")
        headless = config.get("browser_headless", True)
        b_status = "[bold]Head[/bold]" if not headless else "[dim]Headless[/dim]"
        entry("Toggle", "ctrl+b", b_status)

        gap()

        # Vision
        seg("Vision")
        entry("/attach", "⌘ + O")

        gap()

        # Config
        seg("Config")
        entry("Edit config", "ctrl+s")

        gap()

        # Conversation
        seg("Conversation")
        entry("Cancel", "esc")
        entry("Clear chat", "ctrl+c")

        gap()

        # System
        seg("System")
        entry("Exit", "ctrl+q")

    # ── Permission handler (called from worker thread) ────────────────

    def _format_tool_args(self, tool_args: dict | None) -> str:
        if not tool_args:
            return ""
        parts = []
        for key, value in tool_args.items():
            val_str = str(value)
            if len(val_str) > 100:
                val_str = val_str[:97] + "..."
            parts.append(f'[dim]{key}=[/][#eee]"{val_str}"[/]')
        return "   " + ", ".join(parts)



    def _tui_permission_handler(self, tool_name: str, tool_args: dict | None = None) -> bool:
        self._permission_event = threading.Event()
        self._permission_allowed = False
        self.call_from_thread(self._show_permission_prompt, tool_name, tool_args)
        self._permission_event.wait()
        return self._permission_allowed

    def _show_permission_prompt(self, tool_name: str, tool_args: dict | None = None) -> None:
        self._awaiting_permission = True
        self._add_system_message(f"[bold]ⓘ  Evy wants to use: {tool_name}[/bold]")
        if tool_name == "file_system_patch" and tool_args:
            path_val = str(tool_args.get("path", ""))
            if len(path_val) > 100:
                path_val = path_val[:97] + "..."
            self._add_system_message(f"[bold]   path:[/] {path_val}")
            old_text = tool_args.get("old_text", "")
            new_text = tool_args.get("new_text", "")
            self._add_system_message("   [#666]Old text:[/]")
            for ln in old_text.rstrip("\n").split("\n"):
                self._add_system_message(f"   [dim]{ln}[/]")
            self._add_system_message("   [#666]New text:[/]")
            for ln in new_text.rstrip("\n").split("\n"):
                self._add_system_message(f"   [bold]{ln}[/]")
        elif tool_args:
            self._add_system_message(self._format_tool_args(tool_args))
        self._add_system_message(f"[bold]   Give permission 'yes' or 'no'[/bold]")
        inp = self.query_one("#prompt-input", Input)
        inp.placeholder = "Type 'yes' or 'no' to give permission"

    # ── Prompt submission ────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt:
            return
        event.input.clear()

        if self._awaiting_permission:
            if prompt.lower() in ("yes", "y"):
                self._permission_allowed = True
            else:
                self._permission_allowed = False
            inp = self.query_one("#prompt-input", Input)
            inp.placeholder = "Converse with Evy…"
            self._awaiting_permission = False
            if self._permission_event:
                self._permission_event.set()
            return

        if prompt.startswith("/"):
            self._handle_command(prompt)
            return

        self._submit_prompt(prompt)

    def _submit_prompt(self, prompt: str, images: list[str] | None = None) -> None:
        watermark = self.query_one("#watermark", Static)
        watermark.add_class("-hidden")
        bar = self.query_one("#attach-bar")
        bar.remove_children()
        bar.remove_class("-visible")
        self._add_user_message(prompt)
        self._current_prompt = prompt
        self._cancel_event.clear()
        imgs = images or self._attached_images
        self._attached_images = []
        self._agent_gen = call_evy_stream(prompt, images=imgs)
        self._agent_worker = self.run_agent()

    @work(thread=True, exclusive=True)
    def run_agent(self) -> None:
        gen = self._agent_gen
        self._agent_lock.acquire()
        try:
            for event in gen:
                if self._cancel_event.is_set():
                    gen.close()
                    break
                self.post_message(EvyEvent(event))
        except Exception as exc:
            self.call_from_thread(
                self._add_system_message,
                f"[#888]Agent error: {exc}[/#888]",
            )
        finally:
            self._agent_lock.release()
            self._agent_gen = None

    @work(thread=True, exclusive=True)
    def run_consolidation(self) -> None:
        from utilities.scripts.consolidation import consolidate_conversation, consolidate_episodic
        config = load_config()
        pct = config.get("limits_pct", {})
        window = config["context_window"]
        max_output = int(window * pct.get("output", 0) / 100)
        preserve = config.get("preserve_count", 5)
        try:
            consolidate_conversation(
                load_memory(BRAIN_PATH, []),
                max_output_tokens=max_output,
                preserve_count=preserve,
            )
            consolidate_episodic(
                load_memory("memory/episodic-memory.json", []),
                max_output_tokens=max_output,
            )
        except Exception as exc:
            self.call_from_thread(self._add_system_message, f"[#888]Consolidation error: {exc}[/#888]")
            return
        self.call_from_thread(self._update_brain_occupation)
        self.call_from_thread(self._add_system_message, "[bold]✓ Memory consolidated[/bold]")

    # ── Heartbeat scheduler ──────────────────────────────────────────

    def _start_heartbeat_scheduler(self) -> None:
        self._heartbeat_handle = self.set_interval(15, self._tick_heartbeats)

    def _tick_heartbeats(self) -> None:
        with _heartbeats_lock:
            try:
                hbs = load_heartbeats()
            except (json.JSONDecodeError, OSError):
                return
            if not hbs:
                return

            now = datetime.now(timezone.utc)
            due: list[dict] = []
            changed = False
            for hb in hbs:
                if hb.get("status") == "pending":
                    try:
                        t = datetime.fromisoformat(hb["time_of_occurrence"])
                        if t.tzinfo is None:
                            t = t.replace(tzinfo=timezone.utc)
                        if t <= now:
                            hb["status"] = "in-operation"
                            changed = True
                            due.append(hb)
                    except (ValueError, KeyError):
                        continue

            if changed:
                save_heartbeats(hbs)

        self._heartbeat_queue.extend(due)
        if self._heartbeat_queue:
            self._process_heartbeat_queue()

    def _process_heartbeat_queue(self) -> None:
        if not self._heartbeat_queue:
            return
        if self._agent_worker and self._agent_worker.is_running:
            return
        hb = self._heartbeat_queue.pop(0)
        self._run_heartbeat(hb["id"])

    @work(thread=True)
    def _run_heartbeat(self, hb_id: str) -> None:
        self._agent_lock.acquire()
        try:
            with _heartbeats_lock:
                try:
                    hbs = load_heartbeats()
                except (json.JSONDecodeError, OSError):
                    return
                hb = next((h for h in hbs if h["id"] == hb_id), None)
                if not hb:
                    return
                hb_name = hb["name"]
                hb_repeat = hb.get("repeat")

            self.call_from_thread(
                self._add_system_message,
                f"[bold]\u2661 Heartbeat:[/bold] [dim]{hb_name}[/dim]",
            )

            try:
                from gateway import execute_heartbeat
                final_text, status = execute_heartbeat(hb_name)
            except Exception as e:
                final_text = f"Heartbeat error: {e}"
                status = "fail"

            with _heartbeats_lock:
                try:
                    hbs = load_heartbeats()
                    for h in hbs:
                        if h["id"] == hb_id:
                            h["status"] = status
                            break
                    save_heartbeats(hbs)
                except (json.JSONDecodeError, OSError):
                    pass

            if status == "success" and hb_repeat:
                interval = _parse_interval(hb_repeat)
                if interval:
                    next_time = datetime.now(timezone.utc) + interval
                    new_hb = {
                        "id": f"hb_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}",
                        "name": hb_name,
                        "time_of_occurrence": next_time.isoformat(),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "status": "pending",
                        "repeat": hb_repeat,
                    }
                    with _heartbeats_lock:
                        try:
                            hbs = load_heartbeats()
                            hbs.append(new_hb)
                            save_heartbeats(hbs)
                        except (json.JSONDecodeError, OSError):
                            pass

            if final_text:
                self.call_from_thread(self._add_evy_message, final_text)

            status_icon = "[bold green]\u2713[/bold green]" if status == "success" else "[bold red]\u2717[/bold red]"
            self.call_from_thread(
                self._add_system_message,
                f"{status_icon} Heartbeat [bold]{hb_name}[/bold] → {status}",
            )
        finally:
            self._agent_lock.release()
            self.call_from_thread(self._process_heartbeat_queue)

    # ── Event handling ───────────────────────────────────────────────

    BRAILLE_FRAMES = ["⠁⠀⠀⠀⠀","⠈⠁⠀⠀⠀","⠐⠈⠁⠀⠀","⠠⠐⠈⠁⠀","⡀⠠⠐⠈⠁","⣀⡀⠠⠐⠈","⣄⣀⡀⠠⠐","⣤⣄⣀⡀⠠","⣦⣤⣄⣀⡀","⣶⣦⣤⣄⣀","⣷⣶⣦⣤⣄","⣿⣷⣶⣦⣤","⣿⣿⣷⣶⣦","⣿⣿⣿⣷⣶","⣿⣿⣿⣿⣷","⣿⣿⣿⣿⣿","⠿⣿⣿⣿⣿","⠀⠿⣿⣿⣿","⠀⠀⠿⣿⣿","⠀⠀⠀⠿⣿","⠀⠀⠀⠀⠿"]

    def __init__(self) -> None:
        super().__init__()
        self._current_prompt: str = ""
        self._thinking_buffer: list[str] = []
        self._thinking_flush_handle = None
        self._status_label: str = ""
        self._status_timer_handle = None
        self._status_braille_index: int = 0
        self._tool_widgets: dict[str, ToolWidget] = {}
        self._agent_worker: Worker | None = None
        self._cancel_event = threading.Event()
        self._agent_gen = None
        self._awaiting_permission: bool = False
        self._attached_images: list[str] = []
        self._heartbeat_handle = None
        self._heartbeat_queue: list[dict] = []
        self._last_tool_name: str | None = None
        self._last_tool_widget: ToolWidget | None = None
        self._agent_lock = threading.Lock()

    # ── Chat widget helpers ───────────────────────────────────────────

    def _add_user_message(self, text: str) -> None:
        container = self.query_one("#chat-messages", VerticalScroll)
        container.mount(Static(f"[#fff]{text}[/#fff]", classes="user-message"))
        container.scroll_end(animate=False)

    def _add_evy_message(self, text: str) -> None:
        container = self.query_one("#chat-messages", VerticalScroll)
        container.mount(Markdown(text, classes="evy-message"))
        container.scroll_end(animate=False)

    def _add_system_message(self, text: str) -> None:
        container = self.query_one("#chat-messages", VerticalScroll)
        container.mount(Static(text, classes="system-message"))
        container.scroll_end(animate=False)

    def _add_discord_message(self, text: str) -> None:
        container = self.query_one("#chat-messages", VerticalScroll)
        container.mount(Static(f"[#a855f7]{text}[/#a855f7]", classes="discord-message"))
        container.scroll_end(animate=False)

    def _add_tool_widget(
        self,
        name: str,
        icon: str,
        label: str,
        kind: str,
        widget_cls: type[ToolWidget] = ToolWidget,
        args: dict | None = None,
    ) -> ToolWidget:
        container = self.query_one("#chat-messages", VerticalScroll)
        widget = widget_cls(name, icon, label, kind, args=args)
        container.mount(widget)
        container.scroll_end(animate=False)
        self._tool_widgets[name] = widget
        widget.start_spinner()
        return widget

    def _clear_chat(self) -> None:
        container = self.query_one("#chat-messages", VerticalScroll)
        container.remove_children()

    def _flush_thinking(self) -> None:
        if not self._thinking_buffer:
            return
        text = "".join(self._thinking_buffer)
        self.query_one("#thinking-text", Static).update(Text(text, style="dim"))

    def _set_status(self, label: str) -> None:
        self._status_label = label
        if not self._status_timer_handle:
            self._status_braille_index = 0
            self._tick_status()
            self._status_timer_handle = self.set_interval(0.15, self._tick_status)

    def _tick_status(self) -> None:
        bar = self.query_one("#load-status", Static)
        frame = self.BRAILLE_FRAMES[self._status_braille_index % len(self.BRAILLE_FRAMES)]
        self._status_braille_index += 1
        bar.update(f"{frame} {self._status_label}")

    def _clear_status(self) -> None:
        if self._status_timer_handle:
            self._status_timer_handle.stop()
            self._status_timer_handle = None
        bar = self.query_one("#load-status", Static)
        bar.update("[dim]㆝[/dim]")
        self._status_label = ""

    def _update_brain_occupation(self, char_count: int | None = None, token_count: int | None = None) -> None:
        if char_count is None or token_count is None:
            memory = load_memory(BRAIN_PATH, [])
            char_count = sum(len(json.dumps(e)) for e in memory)
            token_count = count_tokens(json.dumps(memory))
        if char_count >= 1_000_000:
            formatted = f"{char_count / 1_000_000:.1f}M"
        elif char_count >= 1_000:
            formatted = f"{char_count / 1_000:.0f}k"
        else:
            formatted = str(char_count)
        config = load_config()
        pct = config.get("limits_pct", {})
        window = config["context_window"]
        max_conv_tokens = int(window * pct.get("conversation", 0) / 100)
        percentage = min(100, int(token_count / max_conv_tokens * 100))
        label = f"⌘ Brain occupation - {formatted} ({percentage}%)"
        self.query_one("#brain-label", Static).update(label)

    def on_evy_event(self, message: EvyEvent) -> None:
        event = message.event
        t = event["type"]

        if t == "consolidating":
            self._set_status("Consolidating memory…")

        elif t == "warning":
            self._add_system_message(event["text"])

        elif t == "thinking_chunk":
            self._set_status("Ruminating…")
            self._thinking_buffer.append(event["text"])
            self.query_one("#thinking-content", VerticalScroll).add_class("-visible")
            if not self._thinking_flush_handle:
                self._thinking_flush_handle = self.set_interval(0.3, self._flush_thinking)

        elif t == "thinking_flush":
            self._flush_thinking()
            self._thinking_buffer.clear()
            self.query_one("#thinking-content", VerticalScroll).remove_class("-visible")
            if self._thinking_flush_handle:
                self._thinking_flush_handle.stop()
                self._thinking_flush_handle = None

        elif t == "thinking_spinner":
            if event["state"] == "start":
                self._start_thinking_spinner()
            else:
                self._stop_thinking_spinner()

        elif t == "tool_start":
            name = event["name"]
            args = event["args"]
            kind = event["kind"]
            if kind == "load_skills":
                icon = "⊶"
                names = args.get("names", [])
                tag_prefix = names[0].split("_")[0] if names and "_" in names[0] else (names[0] if names else "?")
                label = f"Loading {len(names)} {tag_prefix} {'tool' if len(names) == 1 else 'tools'}"
                self._set_status(f"Loading {tag_prefix} skill…")
            elif kind == "search_skills":
                icon = "⌕"
                label = f"Searching {args.get('tag', '?')}"
                self._set_status("Looking for a tool…")
            elif name.startswith("browser_"):
                icon = "✱"
                label = name
                self._set_status("Browsing the web…")
            else:
                icon = "⧉"
                label = name
                self._set_status("Working…")
            tool_widget_map = {
                "file_system_read": FileReadWidget,
                "file_system_write": FileWriteWidget,
                "file_system_patch": FileWriteWidget,
                "file_system_append": FileWriteWidget,
                "file_system_create": FileWriteWidget,
            }
            if name == self._last_tool_name and self._last_tool_widget is not None:
                widget = self._last_tool_widget
                widget.reuse()
            else:
                widget_cls = tool_widget_map.get(name, ToolWidget)
                widget = self._add_tool_widget(name, icon, label, kind, widget_cls=widget_cls, args=args)
                self._last_tool_name = name
                self._last_tool_widget = widget

        elif t == "tool_result":
            name = event["name"]
            widget = self._last_tool_widget if name == self._last_tool_name else None
            if widget:
                result = event.get("result", "")
                status = event.get("status", "unknown")
                widget.set_result(str(result), status)

        elif t == "retry":
            self._add_system_message(f"[dim]Ollama error, retrying ({event['attempt']}/3)...[/dim]")

        elif t == "brain_update":
            self._update_brain_occupation(char_count=event["char_count"], token_count=event["token_count"])

        elif t == "final":
            self._flush_thinking()
            self._thinking_buffer.clear()
            self.query_one("#thinking-content", VerticalScroll).remove_class("-visible")
            if self._thinking_flush_handle:
                self._thinking_flush_handle.stop()
                self._thinking_flush_handle = None
            self._stop_thinking_spinner()
            self._clear_status()
            self._update_brain_occupation()
            self._add_evy_message(event["text"])

    # ── Thinking indicator ────────────────────────────────────────────

    def _start_thinking_spinner(self) -> None:
        pass

    def _stop_thinking_spinner(self) -> None:
        pass

    # ── Commands / Slash-command handling ─────────────────────────────

    def _handle_command(self, cmd: str) -> None:
        cmd = cmd.strip()

        if cmd in ("/?", "/help"):
            self._add_system_message("")
            lines = [
                "[bold]Model & Thinking[/bold]",
                "[dim]    /think        Toggle thinking On/Off[/dim]",
                "[dim]    /cloud        Switch to cloud model[/dim]",
                "[dim]    /local        Switch to local model[/dim]",
                "[dim]    /state        Show current configuration[/dim]",
                "[bold]Browser[/bold]",
                "[dim]    /browser      Toggle head/headless[/dim]",
                "[dim]    /head         Headed mode[/dim]",
                "[dim]    /headless     Headless mode[/dim]",
                "[bold]Vision[/bold]",
                "[dim]    /attach       Open file picker to attach an image[/dim]",
                "[bold]Config[/bold]",
                "[dim]    /config       Edit utilities/config.json[/dim]",
                "[bold]Conversation[/bold]",
                "[dim]    /cancel       Cancel current response[/dim]",
                "[dim]    /clear        Clear chat log[/dim]",
                "[dim]    /export       Export conversation to file[/dim]",
                "[dim]    /reset        Reset brain.json and chat[/dim]",
                "[bold]System[/bold]",
                "[dim]    /bye          Close Evy[/dim]",
                "[dim]    /consol       Manually consolidate brain and episodic memory[/dim]",
                "[bold]Email[/bold]",
                "[dim]    /emails       List configured email connections[/dim]",
                "[dim]    ctrl+e        Add a new email connection[/dim]",
            ]
            for line in lines:
                self._add_system_message(line)
        elif cmd == "/bye":
            self.exit()
            return
        elif cmd == "/cancel":
            self.action_cancel_response()
        elif cmd == "/think":
            config = load_config()
            if config.get("thinking", True):
                config["thinking"] = False
                config["stream_thinking"] = False
            else:
                config["thinking"] = True
                config["stream_thinking"] = True
            _save_config(config)
        elif cmd == "/state":
            config = load_config()
            self._add_system_message("[bold]ⓘ  Configuration[/bold]")
            for key, value in config.items():
                if key == "ollama-api-key":
                    display = f"{value[:8]}..." if value else "(not set)"
                    self._add_system_message(f"  [dim]{key}:[/dim] {display}")
                elif isinstance(value, bool):
                    self._add_system_message(f"  [dim]{key}:[/dim] {'[bold]yes[/bold]' if value else '[dim]no[/dim]'}")
                else:
                    self._add_system_message(f"  [dim]{key}:[/dim] {value}")
            active = config.get('cloud-model', '?') if not config.get('local', True) else config.get('model', '?')
            self._add_system_message(f"  [dim]active_model:[/dim] {active}")
            return
        elif cmd == "/browser":
            if self._agent_worker and self._agent_worker.is_running:
                self.notify("You can not change browser state while Evy is working", severity="warning", timeout=3)
                return
            config = load_config()
            headless = config.get("browser_headless", True)
            if headless:
                config["browser_headless"] = False
            else:
                config["browser_headless"] = True
                _browser_mod._close_browser()
            _save_config(config)
        elif cmd == "/headless":
            if self._agent_worker and self._agent_worker.is_running:
                self.notify("You can not change browser state while Evy is working", severity="warning", timeout=3)
                return
            _set_browser_headless(True)
        elif cmd == "/head":
            if self._agent_worker and self._agent_worker.is_running:
                self.notify("You can not change browser state while Evy is working", severity="warning", timeout=3)
                return
            _set_browser_headless(False)
        elif cmd == "/cloud":
            config = load_config()
            config["local"] = False
            _save_config(config)
        elif cmd == "/local":
            config = load_config()
            config["local"] = True
            _save_config(config)
        elif cmd == "/clear":
            self._clear_chat()
        elif cmd == "/export":
            import shutil
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = f"memory/brain-{ts}.json"
            shutil.copy(BRAIN_PATH, dst)
            self._add_system_message(f"[dim]Exported brain to {dst}[/dim]")
        elif cmd == "/reset":
            os.makedirs(os.path.dirname(BRAIN_PATH), exist_ok=True)
            with open(BRAIN_PATH, "w", encoding="utf-8") as f:
                json.dump([], f)
            self._clear_chat()
            self._update_brain_occupation()
            self._add_system_message("[bold]⌘[/bold] [dim]Conversation reset[/dim]")
        elif cmd == "/attach":
            if self._attached_images:
                self.notify("Already has an attached image. Click ✕ to remove it first.", severity="warning", timeout=3)
                return
            script = '''
set imageFile to choose file with prompt "Select an image" of type {"public.png", "public.jpeg", "public.webp"}
if imageFile is not "" then
    return POSIX path of imageFile
end if
'''
            try:
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True, timeout=10,
                )
                path = result.stdout.strip()
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                path = ""
            if not path:
                return
            self._attached_images = [path]
            bar = self.query_one("#attach-bar")
            bar.remove_children()
            filename = os.path.basename(path)
            btn = Button(f"✕ {filename}", id="attach-chip-0", classes="attach-chip")
            bar.mount(btn)
            bar.add_class("-visible")
            self.query_one("#prompt-input", Input).focus()
            return
        elif cmd == "/config":
            self.action_edit_config()
            return
        elif cmd == "/consol":
            self.run_consolidation()
            return
        elif cmd == "/emails":
            conns = list_connections()
            if not conns:
                self._add_system_message("[dim]No email connections configured. Use [bold]ctrl+e[/bold] to add one.[/dim]")
                return
            self._add_system_message("[bold]Configured Email Connections:[/bold]")
            for c in conns:
                self._add_system_message(f"  [dim]{c['id']}[/dim] — {c['email']}  ([italic]{c['description']}[/italic])")
            return
        elif cmd == "Config (Ctrl+S)":
            self.action_edit_config()
            return
        else:
            self._add_system_message(f"[dim]Unknown command: {cmd}[/dim]")
            return

        self._update_commands()

    # ── Attach chip click handler ────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("attach-chip-"):
            self._attached_images = []
            bar = self.query_one("#attach-bar")
            bar.remove_children()
            bar.remove_class("-visible")
            self.query_one("#prompt-input", Input).focus()

    # ── Action handlers (called by keybindings) ──────────────────────

    def action_toggle_browser(self) -> None:
        self._handle_command("/browser")

    def action_clear_input(self) -> None:
        inp = self.query_one("#prompt-input", Input)
        inp.clear()

    def action_cancel_response(self) -> None:
        if self._awaiting_permission:
            inp = self.query_one("#prompt-input", Input)
            inp.placeholder = "Converse with Evy…"
            self._permission_allowed = False
            self._awaiting_permission = False
            if self._permission_event:
                self._permission_event.set()
            return
        if not self._agent_worker or not self._agent_worker.is_running:
            return
        self._cancel_event.set()
        _gateway_mod.cancel_pending()
        self._agent_worker.cancel()
        self._agent_worker = None
        self._thinking_buffer.clear()
        self.query_one("#thinking-content", VerticalScroll).remove_class("-visible")
        if self._thinking_flush_handle:
            self._thinking_flush_handle.stop()
            self._thinking_flush_handle = None
        self._stop_thinking_spinner()
        self._clear_status()
        self._add_system_message("[bold]⽚ Evy was cut short[/bold]")

    def action_toggle_thinking(self) -> None:
        self._handle_command("/think")

    def action_show_state(self) -> None:
        self.push_screen(StateModal())

    def action_edit_config(self) -> None:
        self.push_screen(ConfigModal())

    def action_toggle_activity(self) -> None:
        panel = self.query_one("#activity-panel")
        if panel.has_class("-visible"):
            panel.remove_class("-visible")
        else:
            panel.add_class("-visible")

    def action_show_help(self) -> None:
        self._handle_command("/?")

    def action_add_email_connection(self) -> None:
        self.action_cancel_response()
        def on_result(result: dict | None) -> None:
            if result:
                conn = add_connection(result["email"], result["app_password"], result["description"])
                self._update_email_header()
                self._add_system_message(f"[bold]\u2713[/bold] Email connection added: [dim]{conn['id']}[/dim] ({conn['email']} — {conn['description']})")
                # Refresh gateway context
                conns = list_connections()
                lines = ["Available email connections:"]
                for c in conns:
                    lines.append(f"  id={c['id']} email={c['email']} description=\"{c['description']}\"")
                lines.append("Pass connection_id when calling email tools. Omit if only one connection exists.")
                _gateway_mod._email_connections_context = "\n".join(lines)
        self.push_screen(AddEmailModal(), on_result)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _load_config():
    with open("utilities/config.json", "r") as f:
        return json.load(f)


def _save_config(config: dict):
    with open("utilities/config.json", "w") as f:
        json.dump(config, f, indent=2)


def _set_browser_headless(value: bool):
    config = _load_config()
    config["browser_headless"] = value
    _save_config(config)


# ── Entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = EvyApp()
    app.run()
