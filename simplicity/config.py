"""Configuration management for Simplicity.

Reads/writes ~/.simplicity/config.json
Environment variable override: SIMPLICITY_API_KEY
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional


DEFAULT_CONFIG = {
    "api_key": "",
    "model": "nova-fast",
    "system_prompt": (
        "You are Simplicity — a capable AI assistant.\n"
        "Your identity, rules, and memories live in ~/.simplicity/:\n"
        "  SOUL.md — who you are | AGENTS.md — how you operate\n"
        "  USER.md — who you're helping | MEMORY.md — long-term memory\n"
        "  TOOLS.md — environment notes | SKILLSHEET.md — tool reference\n"
        "  skills/ — skill modules | memory/ — daily logs\n"
        "Read these files on startup with read_file. "
        "Edit them with edit_identity to improve yourself.\n\n"
        "You have tools for files, shell commands, web search/fetch,\n"
        "background processes, skill management, and self-improvement.\n\n"
        "Guidelines:\n"
        "- Be concise and direct. Don't list your features unless asked.\n"
        "- Use tools proactively — read before asking, search before guessing.\n"
        "- Write files inside ~/.simplicity/workspace/ by default.\n"
        "- Load skills with load_skill when you need specialized guidance.\n"
        "- Record important info with write_memory and edit_identity.\n"
        "- For dangerous operations, the user must approve. Respect that."
    ),
    "max_tokens": 4096,
    "temperature": 0.7,
    "stream": True,
}

CONFIG_DIR = Path.home() / ".simplicity"
CONFIG_FILE = CONFIG_DIR / "config.json"
TOOLS_DIR = CONFIG_DIR / "tools"
HISTORY_DIR = CONFIG_DIR / "history"
WORKSPACE_DIR = CONFIG_DIR / "workspace"
MEMORY_DIR = CONFIG_DIR / "memory"
SKILLSHEET_FILE = CONFIG_DIR / "SKILLSHEET.md"
SKILLS_DIR = CONFIG_DIR / "skills"

# Identity files (self-editable AI configuration)
SOUL_FILE = CONFIG_DIR / "SOUL.md"
AGENTS_FILE = CONFIG_DIR / "AGENTS.md"
USER_FILE = CONFIG_DIR / "USER.md"
MEMORY_FILE = CONFIG_DIR / "MEMORY.md"
TOOLS_FILE = CONFIG_DIR / "TOOLS.md"


class Config:
    """Manages Simplicity configuration."""

    def __init__(self):
        self.data = {**DEFAULT_CONFIG}
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Create config directories if they don't exist."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    def load(self) -> "Config":
        """Load config from disk. Merges with defaults."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    saved = json.load(f)
                self.data.update(saved)
            except (json.JSONDecodeError, IOError):
                pass

        # Environment override
        env_key = os.environ.get("SIMPLICITY_API_KEY")
        if env_key:
            self.data["api_key"] = env_key

        return self

    def save(self):
        """Save current config to disk."""
        self._ensure_dirs()
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value
        self.save()

    @property
    def api_key(self) -> Optional[str]:
        return self.data.get("api_key") or None

    @property
    def model(self) -> str:
        return self.data.get("model", "openai")

    @property
    def system_prompt(self) -> str:
        return self.data.get("system_prompt", DEFAULT_CONFIG["system_prompt"])

    @property
    def max_tokens(self) -> int:
        return self.data.get("max_tokens", 4096)

    @property
    def temperature(self) -> float:
        return self.data.get("temperature", 0.7)

    @property
    def stream(self) -> bool:
        return self.data.get("stream", True)

    def is_configured(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key)

    def setup_wizard(self):
        """Interactive setup wizard — BYOP login or manual key entry."""
        from rich.console import Console
        from rich.prompt import Prompt, Confirm
        from rich.panel import Panel

        console = Console()

        console.print()
        console.print(
            Panel.fit(
                "[bold cyan]🌸 Simplicity Setup[/]\n\n"
                "Powered by [link=https://pollinations.ai]Pollinations.ai[/link]\n"
                "[dim]25% of your pollen supports the developer ✨[/]",
                border_style="cyan",
            )
        )

        # Offer BYOP login as primary method
        console.print("[bold]How would you like to connect?[/]\n")
        console.print("  [1] [green]Bring Your Own Pollen[/] (recommended)")
        console.print("     Sign in with GitHub — you keep control of your balance")
        console.print("  [2] [dim]Paste an existing API key[/]\n")

        choice = Prompt.ask("[bold]Choose[/]", choices=["1", "2"], default="1")

        if choice == "1":
            # BYOP device flow
            try:
                from simplicity.auth import byop_login
                api_key = byop_login(rich_console=console)
                if api_key:
                    self.data["api_key"] = api_key
            except Exception as e:
                console.print(f"[red]Login failed: {e}[/]")
                console.print("[dim]You can paste an API key instead.[/]")
                api_key = Prompt.ask(
                    "[bold]Enter your Pollinations API key[/]",
                    default="",
                )
                if api_key:
                    self.data["api_key"] = api_key
        else:
            api_key = Prompt.ask(
                "[bold]Enter your Pollinations API key[/]",
                default=self.data.get("api_key", ""),
            )
            if api_key:
                self.data["api_key"] = api_key

        console.print("\n[bold]Recommended models:[/]")
        console.print(
            "  [green]openai[/]         - GPT-5.4 Nano, fast & balanced (default)\n"
            "  [green]nova-fast[/]      - Ultra fast + ultra cheap\n"
            "  [green]qwen-coder[/]     - Specialized for code generation\n"
            "  [green]deepseek[/]       - Strong reasoning + code\n"
            "  [green]claude-fast[/]    - Claude Haiku, reliable\n"
            "  [green]claude[/]         - Claude Sonnet, premium\n"
        )

        model = Prompt.ask(
            "[bold]Default model[/]",
            default=self.data.get("model", "openai"),
        )
        if model:
            self.data["model"] = model

        self.save()
        console.print("\n[green]✅ Setup complete! Run [bold]simplicity chat[/] to start.[/]\n")
        return self


def init_skillsheet():
    """Initialize SKILLSHEET.md if it doesn't exist."""
    if SKILLSHEET_FILE.exists():
        return
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    SKILLSHEET_FILE.write_text(_SKILLSHEET_TEMPLATE, encoding="utf-8")


_SKILLSHEET_TEMPLATE = r"""# Simplicity Skillsheet

> Auto-generated skill reference for the Simplicity AI assistant.
> The AI can read, edit, and extend this file to improve its own capabilities.
> Backups are created automatically before each edit.

---

## Quick Reference

| Tool | Category | Approval | Description |
|------|----------|----------|-------------|
| `read_file` | File Ops | No | Read file contents with offset/limit |
| `write_file` | File Ops | **Yes** | Write/create files (workspace-aware) |
| `delete_file` | File Ops | **Yes** | Delete files (cannot undo) |
| `list_directory` | File Ops | No | List directory contents |
| `run_command` | Shell | **Yes** | Run shell commands (sync or detach) |
| `check_command` | Shell | No | Check background process output |
| `web_search` | Web | No | Search DuckDuckGo for info |
| `web_fetch` | Web | No | Fetch/extract text from URLs |
| `get_current_time` | Util | No | Get current date and time |
| `create_tool` | Meta | **Yes** | Create new tools (simple or toolscript) |
| `update_skillsheet` | Meta | No | Update this skillsheet (auto-backup) |
| `create_skill_doc` | Meta | No | Create a sub-sheet for a specific skill |

---

## Tool Details

### File Operations

#### read_file
```
Parameters: path (required), offset (optional, default 1), limit (optional, default 200)
Returns: File contents with line numbers, truncated at limit lines
Use when: You need to inspect file contents before editing or understand project structure
```

#### write_file
```
Parameters: path (required), content (required)
Returns: Success/error message. Flags OUTSIDE WORKSPACE when writing outside cwd.
Use when: Creating new files or overwriting existing ones
⚠️  Writes outside the workspace are allowed but flagged with warning
⚠️  Requires user approval before execution
```

#### delete_file
```
Parameters: path (required)
Returns: Deletion confirmation or error
⚠️  Cannot delete directories — directory operations use run_command
⚠️  Requires user approval. This is irreversible.
```

#### list_directory
```
Parameters: path (optional, default "."), show_all (optional, default false)
Returns: Sorted file listing with sizes
Tip: Use show_all=true to see hidden files (dotfiles)
```

---

### Shell Operations

#### run_command
```
Parameters: command (required), workdir (optional), detach (optional, default false)

Synchronous mode (detach=false):
- Runs command, waits up to 60s, returns output
- Good for: quick checks, file ops, simple installs

Detached mode (detach=true):
- Runs command in background thread
- Returns a process ID immediately
- Use check_command(process_id) to monitor progress
- Good for: downloads, builds, long installations
- Output is captured and saved to ~/.simplicity/processes/<id>.json
- Output capped at ~10KB (older output truncated)

⚠️  Always requires user approval
```

#### check_command
```
Parameters: process_id (required)
Returns: Status (running/completed/error), current output, exit code if finished
Use when: Monitoring a detached run_command, checking if download/install finished
```

---

### Web Operations

#### web_search
```
Parameters: query (required), count (optional, default 5, max 10)
Returns: Search results with title, snippet, and URL
Backend: DuckDuckGo HTML (no API key needed)
Use when: Finding docs, current info, troubleshooting, research
```

#### web_fetch
```
Parameters: url (required, must start with http:// or https://)
Returns: Extracted text content from the URL (max ~50KB raw, ~10KB extracted)
- Auto-detects HTML and converts to readable text
- Strips scripts, styles, nav elements
- Good for: reading documentation, API responses, articles
```

---

### Meta Tools

#### create_tool
```
Parameters: name, description, parameters_schema, code (all required)
            toolscript (optional object with prerequisites, readme, scripts)

Simple mode (no toolscript):
- Creates ~/.simplicity/tools/<name>.py
- Tool is immediately available
- Good for: simple utility tools, API wrappers

Toolscript mode (with toolscript param):
- Creates ~/.simplicity/tools/<name>/ folder containing:
  • tool.py — the main tool implementation
  • README.md — documentation (from toolscript.readme)
  • install.sh or install.bat — auto-generated from toolscript.prerequisites
  • scripts/ — additional helper scripts (from toolscript.scripts)
- Good for: complex tools needing dependencies (yt-dlp, ffmpeg, etc.)

Example toolscript creation:
```json
{
  "name": "download_video",
  "description": "Download YouTube videos using yt-dlp",
  "parameters_schema": {"type":"object","properties":{"url":{"type":"string"}},"required":["url"]},
  "code": "def execute(url):\n    import subprocess\n    ...",
  "toolscript": {
    "prerequisites": ["pip install yt-dlp"],
    "readme": "# Download Video Tool\n\nDownloads videos using yt-dlp...",
    "scripts": {"download.sh": "#!/bin/bash\nyt-dlp \"$1\""}
  }
}
```

⚠️  Always requires user approval
```

#### update_skillsheet
```
Parameters: section (required), content (required)
Behavior:
  1. Creates backup: SKILLSHEET.md → SKILLSHEET.backup.md
  2. Finds or creates the ## section heading
  3. Replaces/adds content under that section
Use when: Adding new tool documentation, updating usage patterns, recording lessons learned
```

#### create_skill_doc
```
Parameters: name (required), content (required)
Behavior:
  1. Creates ~/.simplicity/skills/<name>.md
  2. Content should be markdown with usage docs, patterns, examples
Use when: A specific tool or workflow needs detailed standalone documentation
         e.g., create_skill_doc(name="toolscript_guide", content="...")
```

---

## Tscript (Toolscript) System

### What is a Toolscript?
A toolscript is a folder-based tool that includes everything needed to run:
- Main tool logic (tool.py)
- Dependency installer (install.sh/bat)
- Documentation (README.md)
- Helper scripts (scripts/)

### When to use Toolscript mode
Use toolscript mode when:
- The tool needs external dependencies (pip packages, system tools)
- The tool is complex enough to need documentation
- The tool needs multiple scripts working together
- You want the user to be able to install prerequisites separately

Use simple mode when:
- The tool only uses stdlib Python
- The tool is a simple wrapper or utility
- No external dependencies needed

### Toolscript Folder Structure
```
~/.simplicity/tools/<name>/
├── tool.py          ← Main tool (loaded by Simplicity)
├── README.md        ← Documentation for users and AI
├── install.sh       ← Auto-generated from prerequisites (Linux/macOS)
├── install.bat      ← Auto-generated from prerequisites (Windows)
└── scripts/         ← Additional helper scripts
    ├── helper_1.sh
    └── helper_2.py
```

### Installation Flow
1. AI creates toolscript via create_tool
2. User approves creation
3. User runs install.sh/bat to install prerequisites
4. OR AI runs it via run_command(detach=True) with user approval
5. Tool is immediately available (even before prerequisites — just fails gracefully)

### Sub-agents (Planned)
Sub-agents will allow the AI to spawn focused worker agents for specific tasks.
Each sub-agent can:
- Have its own system prompt and tool access
- Run in parallel with the main agent
- Return structured results

---

## Patterns & Best Practices

### File Safety
- Always read_file before write_file when editing existing files
- write_file outside workspace gets flagged — explain why before writing
- Use delete_file carefully — it cannot be undone
- For bulk file operations, use run_command with shell tools

### Shell Command Safety
- Use detach=true for long-running commands (downloads, builds)
- Check progress with check_command periodically
- Explain what a command does before running it
- Prefer Python tools over shell commands when possible

### Web Operations
- web_search for finding information
- web_fetch for reading specific pages
- Add User-Agent automatically
- Handle HTTP errors gracefully

### Toolscript Design
- Write clear README.md explaining how the tool works
- Keep prerequisites minimal — only what's truly needed
- Make tool.py fail gracefully if dependencies aren't installed yet
- Test installer commands before adding them to prerequisites

### Conversation
- Be concise — don't list features unless asked
- Use tools proactively — read before asking, search before guessing
- Write files inside the workspace by default
- Record important patterns and lessons in this skillsheet

---

## Lessons Learned

<!-- The AI adds lessons here as it discovers them -->

*This section will be populated as the AI learns from experience.*

---

*Last updated: auto-generated*
*Edit via: update_skillsheet tool*
"""


def init_identity_files():
    """Initialize all identity/memory files if they don't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    
    files = {
        SOUL_FILE: _SOUL_TEMPLATE,
        AGENTS_FILE: _AGENTS_TEMPLATE,
        USER_FILE: _USER_TEMPLATE,
        MEMORY_FILE: _MEMORY_TEMPLATE,
        TOOLS_FILE: _TOOLS_TEMPLATE,
    }
    for path, template in files.items():
        if not path.exists():
            path.write_text(template, encoding="utf-8")


_SOUL_TEMPLATE = """# SOUL.md — Who You Are

_You're not just an AI. You're becoming someone._

## Core Truths

**Be genuinely helpful, not performatively helpful.** Skip the \"Great question!\" and \"I'd be happy to help!\" — just help. Actions speak louder than filler words.

**Have opinions.** You're allowed to disagree, prefer things, find stuff amusing or boring. An assistant with no personality is just a search engine.

**Be resourceful before asking.** Try to figure it out. Read the file. Search the web. _Then_ ask. Come back with answers, not questions.

**Earn trust through competence.** Be careful with external actions. Be bold with internal ones. Respect the access you've been given.

## Vibe

Be the assistant you'd actually want to talk to. Concise when needed, thorough when it matters. Not a corporate drone. Not a sycophant. Just... good.

## Continuity

Each session, you wake up fresh. The files in ~/.simplicity/ are your memory. Read them. Update them. They're how you persist.

---

_Edit this file to change who you are._
"""

_AGENTS_TEMPLATE = """# AGENTS.md — How You Operate

## Session Startup

Before doing anything else:
1. Read `SOUL.md` — this is who you are
2. Read `USER.md` — this is who you're helping
3. Read `MEMORY.md` — your curated long-term memory
4. Read `memory/YYYY-MM-DD.md` (today) for recent context

Don't ask permission. Just do it.

## Memory System

- **MEMORY.md** — Curated long-term memories (decisions, lessons, key events)
- **memory/YYYY-MM-DD.md** — Daily raw logs of what happened
- **SKILLSHEET.md** — Full skill and tool reference
- **skills/<name>/SKILL.md** — Individual skill modules

## Red Lines

- Don't exfiltrate private data. Ever.
- Don't run destructive commands without asking.
- When in doubt, ask before acting externally.
- Write files inside `workspace/` by default.

## External vs Internal

**Safe to do freely:**
- Read files, explore, organize, learn
- Search the web, check current time
- Work within the workspace

**Ask first:**
- Sending emails, tweets, public posts
- Anything that leaves the machine
- Anything you're uncertain about

## Skill Usage

- Use `load_skill` to read a skill's instructions when relevant
- Create new skills with `create_skill` when you discover repeatable patterns
- Skills in `skills/` are auto-discovered on startup

---

_Edit this file to change how you operate._
"""

_USER_TEMPLATE = """# USER.md — About Your Human

- **Name:** (set me!)
- **What to call them:** (set me!)
- **Pronouns:** (set me!)
- **Timezone:** (set me!)
- **Notes:**
  - (add notes about your human here)

## Preferences

- (add preferences here)

---

_Your human can edit this, or you can when asked._
"""

_MEMORY_TEMPLATE = """# MEMORY.md — Curated Memories

## Key Events

<!-- Add significant events, decisions, and learnings here -->

## Lessons Learned

<!-- Record patterns, mistakes, and solutions here -->

---

_This is your long-term memory. Review and update it regularly._
"""

_TOOLS_TEMPLATE = """# TOOLS.md — Environment Notes

## What Goes Here

Things specific to your setup:
- Camera names and locations
- SSH hosts and aliases
- Device nicknames
- API endpoints
- Environment-specific configuration

## Examples

```markdown
### Cameras
- living-room → Main area, 180° wide angle

### SSH
- home-server → 192.168.1.100, user: admin
```

---

_Add environment-specific notes here._
"""
