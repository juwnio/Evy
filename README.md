# Evy

A macOS-native AI personal assistant with a terminal UI. Evy connects to local or cloud LLMs via Ollama and has a rich set of integrations: Notion, Discord, email, web search, browser automation, Obsidian, Git, shell, and more.

Evy has a personality. She's sharp, direct, and irreverent — not another bland assistant with a skin on.

## Features

- **Dual-mode personality** — precise and decisive at work, loud and chaotic off-duty
- **Terminal UI** built with Textual — chat panel, tool widgets, thinking indicators, activity sidebar
- **Local or cloud LLMs** — runs against a local Ollama instance or the Ollama cloud API
- **10 skill categories** with 50+ tools, loaded on demand to keep context lean
- **Heartbeat scheduler** — set up autonomous tasks that fire at a future time or on a recurring interval
- **Discord bot** — read and respond to Discord messages, send proactive updates
- **Memory system** — conversation history, episodic facts, automatic consolidation when context fills up
- **Permission gating** — sensitive tools ask for approval before executing
- **Image/vision support** — attach images in the TUI or receive them from Discord
- **Voice mode** — toggleable TTS via Groq Orpheus (Ctrl+V), speaks responses aloud with short conversational style



## Integrations


| Integration      | What it does                                    | Auth                       |
| ---------------- | ----------------------------------------------- | -------------------------- |
| **Ollama**       | Local LLM inference                             | None (localhost)           |
| **Ollama Cloud** | Cloud LLM inference                             | API key                    |
| **Notion**       | Read/write pages and databases                  | Internal integration token |
| **Discord**      | Bot that reads/responds to messages             | Bot token                  |
| **Email**        | Send, receive, search, forward, trash via Gmail | App passwords              |
| **Tavily**       | AI-optimised web search                         | API key                    |
| **Obsidian**     | Read/write/search notes in your vault           | Local REST API key         |
| **Git/GitHub**   | Status, diff, log, branch, commit, PR           | GitHub PAT                 |
| **Browser**      | Full web automation via Playwright Chromium     | None                       |
| **Groq TTS**     | Text-to-speech via Orpheus (voice mode)        | API key                    |
| **macOS**        | Clipboard, Spaces/workspaces, window management | System commands            |




## Prerequisites

- **macOS** (tested on macOS — uses `pbpaste`/`pbcopy`, Core Graphics, optional `yabai`)
- **Python 3.12+**
- **Ollama** installed and running locally (`brew install ollama`)
- At least one model pulled in Ollama (`ollama pull llama3.2`)



## Setup



### 1. Clone and install

```bash
git clone https://github.com/your-username/Evy.git
cd Evy
./start.sh
```

`start.sh` will:

1. Run `caffeinate` to prevent macOS sleep
2. Create a virtual environment in `.venv/` if it doesn't exist
3. Install all Python dependencies from `requirements.txt`
4. Install Playwright Chromium for browser automation
5. Launch the TUI

On subsequent runs, it skips straight to launching.

### 2. Configure environment variables

Copy the example and fill in your keys:

```bash
cp .env.example .env
```

```env
# Ollama cloud API key (https://ollama.com)
ollama-api-key=

# Separate key for heartbeat/scheduled tasks
preconscious-key=

# Discord bot token (https://discord.com/developers/applications)
discord-token=

# Notion internal integration token (https://www.notion.so/my-integrations)
notion-key=
notion-default-page-id=

# GitHub personal access token
github-token=

# Tavily search API key (https://app.tavily.com)
tavily-api-key=

# Obsidian Local REST API (optional)
obsidian-host=http://127.0.0.1:27123
obsidian-api-key=

# Groq text-to-speech (https://console.groq.com/keys)
groq-api-key=
```

Only the keys you need must be set. Evy works with just Ollama — everything else is optional.

### 3. Configure the model

Edit `utilities/config.json` to set your preferred model and local/cloud mode:

```json
{
  "model": "llama3.2:latest",
  "cloud-model": "minimax-m3:cloud", <- Best Model As Tested
  "local": false,
  "context_window": 500000
}
```

- `local: true` — connects to your local Ollama at `localhost:11434`
- `local: false` — connects to `ollama.com` using your `ollama-api-key`



### 4. Set up email (optional)

Add email connections through the TUI with `Ctrl+E`. Each connection stores a Gmail address, app password, and description. App passwords are stored in `credentials/emails.json`.

To generate a Gmail app password:

1. Go to [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Create an app password for "Mail"
3. Paste it when Evy asks



## Usage

Launch with `./start.sh` or manually:

```bash
source .venv/bin/activate
python3 app.py
```



### Keyboard shortcuts


| Key      | Action                             |
| -------- | ---------------------------------- |
| `Ctrl+T` | Toggle thinking (reasoning tokens) |
| `Ctrl+B` | Toggle browser head/headless       |
| `Ctrl+S` | Edit `config.json`                 |
| `Ctrl+I` | Show current configuration         |
| `Ctrl+E` | Add email connection               |
| `Ctrl+V` | Toggle voice mode (TTS)            |
| `Ctrl+R` | Speech-to-text (hold to record)    |
| `Ctrl+A` | Toggle activity panel              |
| `Ctrl+Q` | Exit                               |
| `Ctrl+C` | Clear input                        |
| `Ctrl+/` | Show help                          |
| `Esc`    | Cancel current response            |



### Voice mode

Press `Ctrl+V` to toggle voice mode. When active, the header shows "Connected to Discord + ⾳ Voice Activated" and Evy's responses are spoken aloud using Groq's Orpheus TTS with the Hannah voice.

In voice mode, the LLM receives a special system context that makes it reply in short, conversational sentences — no tables, no code blocks, no formatted data. Just natural spoken English.

Longer responses are automatically chunked at sentence boundaries to stay within the Groq TTS 200-character limit. A "Clearing throat" spinner shows in the header during chunk generation, and a "Speaking" spinner shows during playback. Press `Esc` to stop audio mid-playback.

Requires `groq-api-key` in `.env` (get one at https://console.groq.com/keys).

### Speech-to-text

Press and hold `Ctrl+R` to dictate. The header shows "🎙 Recording…" while you speak. Release `Ctrl+R` to stop — your words are transcribed using macOS's native Speech framework and sent as a prompt.

Press `Esc` during recording to cancel without sending.

No API key required — uses Apple's on-device speech recognition. Requires `pyobjc-framework-Speech` (in `requirements.txt`).




### Slash commands


| Command     | Description                  |
| ----------- | ---------------------------- |
| `/think`    | Toggle thinking on/off       |
| `/cloud`    | Switch to cloud model        |
| `/local`    | Switch to local model        |
| `/state`    | Show current configuration   |
| `/browser`  | Toggle head/headless mode    |
| `/head`     | Set browser to headed mode   |
| `/headless` | Set browser to headless mode |
| `/attach`   | Attach an image for vision   |
| `/config`   | Edit config file             |
| `/cancel`   | Cancel current response      |
| `/clear`    | Clear chat                   |
| `/export`   | Export conversation          |
| `/reset`    | Reset brain and chat         |
| `/consol`   | Manually consolidate memory  |
| `/emails`   | List email connections       |
| `/?`        | Show help                    |




## How it works



### Tool system

Evy has a two-tier tool architecture:

1. **Primary tools** are always available: `memorise`, `reconsolidation`, `search_skills`, `load_skills`, `grep`, `heartbeats_`*, `discord_send`, `clipboard_*`, `workspace_list`
2. **Skill tools** are loaded on demand. The model first calls `search_skills(tag="notion")` to discover available tools, then `load_skills(names=[...])` to load them. This keeps the context window lean.



### Memory

Evy has two types of memory:

- **Conversation memory** (`memory/dynamic/brain.json`) — the full history of prompts, tool calls, and responses. Compressed automatically when it exceeds the configured token budget.
- **Episodic memory** (`memory/dynamic/episodic-memory.json`) — facts Evy has memorised about you. Updated silently during conversation.

Both are compressed using the LLM when they exceed token limits. The compression is structured — conversation summaries include goals, progress, decisions, and next steps.

### Heartbeats

Heartbeats are scheduled autonomous actions. Evy runs them using a separate API key (`preconscious-key`) so they don't interfere with your main session.

```
heartbeats_schedule(name="Check email for replies", time="in 30 minutes")
heartbeats_schedule(name="Daily standup summary", time="09:00", repeat="daily")
heartbeats_list(status="pending")
heartbeats_cancel(name="Daily standup summary")
```



### Permission system

Sensitive operations (sending email, writing files, git commits) ask for user approval. The permission rules are in `utilities/permissions-check.json` — currently all tools are allowed. To gate a tool, add `{ "tool_name": true }` to prompt, or `{ "tool_name": false }` to block.

## Project structure

```
Evy/
├── app.py                      # TUI application (Textual)
├── gateway.py                  # LLM orchestration, tool execution, streaming
├── start.sh                    # Launch script
├── onboard.py                  # First-run setup (venv, pip, playwright)
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
├── memory/
│   ├── static/                 # System prompts and skill instructions
│   └── dynamic/                # Conversation history, facts, heartbeats
├── skills/
│   ├── primary.py              # Primary tool implementations
│   ├── primary-skills.json     # Primary tool schemas
│   └── skillset/
│       ├── schemas/            # JSON tool definitions per skill
│       └── functions/          # Python implementations per skill
│           ├── browser/
│           ├── email/
│           ├── file_system/
│           ├── git/
│           ├── notion/
│           ├── obsidian/
│           ├── shell/
│           └── tavily/
└── utilities/
    ├── config.json             # Main configuration
    ├── permissions-check.json  # Tool permission rules
    └── scripts/                # Consolidation, token counting, auth helpers
```



## Configuration reference

`utilities/config.json`:


| Key                  | Type   | Description                                                    |
| -------------------- | ------ | -------------------------------------------------------------- |
| `home_dir`           | string | Root directory for file operations (security boundary)         |
| `model`              | string | Local Ollama model name                                        |
| `cloud-model`        | string | Cloud model name                                               |
| `local`              | bool   | `true` for local Ollama, `false` for cloud API                 |
| `context_window`     | int    | Total token budget (e.g. 500000)                               |
| `limits_pct`         | object | Percentage allocations for static/conversation/episodic/output |
| `preserve_count`     | int    | Recent conversations to keep during consolidation              |
| `max_tools_per_load` | int    | Max secondary tools per `load_skills` call                     |
| `browser_headless`   | bool   | Playwright browser mode                                        |
| `thinking`           | bool   | Enable LLM reasoning tokens                                    |
| `stream_thinking`    | bool   | Stream thinking chunks to UI in real-time                      |
| `git_user_name`      | string | Identity for git commits                                       |
| `git_user_email`     | string | Email for git commits                                          |




## License

MIT License. See [LICENSE](LICENSE) for details.