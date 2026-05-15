"""Tool system for Simplicity.

Built-in tools:
  - read_file: Read file contents
  - write_file: Create or overwrite a file (workspace-aware)
  - delete_file: Delete a file (requires approval)
  - list_directory: List files in a directory
  - run_command: Execute a shell command
  - web_search: Search the web for information
  - web_fetch: Fetch and extract text from a URL
  - get_current_time: Get current date and time

Custom tools: drop Python files in ~/.simplicity/tools/
Each tool file must expose:
  TOOL_DEFINITION: dict (OpenAI function format)
  execute(kwargs) -> str
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


# ── Built-in tool definitions (OpenAI function format) ──────────────

BUILT_IN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_tool",
            "description": (
                "Create a new custom tool that extends your capabilities. "
                "The tool is saved as a Python file and becomes immediately available. "
                "Use this when you need a capability that doesn't exist yet. "
                "Optional: include a 'toolscript' to create a folder-based tool with "
                "prerequisites (dependencies to install), documentation, and helper scripts. "
                "REQUIRES USER APPROVAL before the tool is created."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Unique tool name (snake_case, e.g. 'get_weather')",
                    },
                    "description": {
                        "type": "string",
                        "description": "What this tool does, in one sentence",
                    },
                    "parameters_schema": {
                        "type": "object",
                        "description": (
                            "JSON Schema for the tool's parameters. "
                            "Must have 'type': 'object', 'properties': {...}, and 'required': [...]"
                        ),
                    },
                    "code": {
                        "type": "string",
                        "description": (
                            "Python code for the execute function. Must define:\n"
                            "def execute(**kwargs) -> str:\n"
                            "    # your code here\n"
                            "    return result\n\n"
                            "The function receives keyword arguments matching the parameters schema. "
                            "Return a string result. Use stdlib modules only (urllib, json, etc). "
                            "Handle errors gracefully — return error messages as strings, don't raise."
                        ),
                    },
                    "toolscript": {
                        "type": "object",
                        "description": ("Optional. Create a folder-based toolscript with prerequisites "
                            "and documentation. Use this when the tool needs external dependencies "
                            "(like yt-dlp, ffmpeg) or helper scripts."),
                        "properties": {
                            "prerequisites": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Shell commands to install dependencies (e.g. ['pip install yt-dlp', 'sudo apt install ffmpeg'])"
                            },
                            "readme": {
                                "type": "string",
                                "description": "Markdown documentation explaining how the tool works and how to use it"
                            },
                            "scripts": {
                                "type": "object",
                                "description": "Additional script files (filename → content) that the tool needs"
                            },
                        },
                    },
                },
                "required": ["name", "description", "parameters_schema", "code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file. Returns the file content as text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read (absolute or relative)",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-indexed, optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read (optional, default 200)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": ("Write content to a file. Files are written inside the current "
                "working directory (workspace) by default. Writing outside the workspace "
                "is allowed but will be flagged with a warning — only do this when "
                "specifically asked or when necessary for the task. "
                "Creates parent directories as needed."),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories in a given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list (default: current directory)",
                    },
                    "show_all": {
                        "type": "boolean",
                        "description": "Include hidden files (starting with .). Default: false",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": ("Delete a file. REQUIRES USER APPROVAL. "
                "Only use when explicitly asked to delete something. "
                "Be careful — this cannot be undone."),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to delete",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": ("Execute a shell command and return the output. "
                "Set detach=True for long-running commands (downloads, installs, builds) "
                "to run in the background — then use check_command to monitor progress."),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    },
                    "workdir": {
                        "type": "string",
                        "description": "Working directory for the command (optional)",
                    },
                    "detach": {
                        "type": "boolean",
                        "description": "Run command in background. Returns a process ID for check_command.",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_command",
            "description": ("Check the status and live output of a background command "
                "started with run_command(detach=True). Returns whether the command "
                "is still running, its current output, and exit code if finished."),
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {
                        "type": "string",
                        "description": "The process ID returned by run_command(detach=True)",
                    },
                },
                "required": ["process_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": ("Search the web for information and return results with "
                "titles, URLs, and snippets. Use this to find current information, "
                "documentation, or answer questions about recent events."),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 10)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": ("Fetch and extract readable text content from a URL. "
                "Use this to read documentation, articles, API responses, or any web page. "
                "Returns the extracted text (max ~50KB). Supports HTML to text conversion."),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch (must be HTTP or HTTPS)",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": ("Get the current date and time. Useful when you need to know "
                "what day it is or the exact current time for time-sensitive tasks."),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_skillsheet",
            "description": ("Update the SKILLSHEET.md skill reference. "
                "Creates an automatic backup before editing. "
                "Use this to document new tools, patterns, lessons learned, or improve documentation. "
                "The section parameter names the heading (e.g. 'Patterns & Best Practices'), "
                "and content replaces/adds content under that section."),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": "Section heading to update (e.g. 'Lessons Learned', 'Patterns & Best Practices')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown content to place under the section heading. Replaces existing content.",
                    },
                },
                "required": ["section", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_skill_doc",
            "description": ("Create a focused sub-sheet for a specific skill or tool. "
                "Saved to ~/.simplicity/skills/<name>.md. "
                "Use this for detailed standalone documentation on specific topics "
                "like toolscript creation, debugging workflows, or integration guides."),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Filename for the skill doc (without .md, e.g. 'toolscript_guide')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full markdown content for the skill document",
                    },
                },
                "required": ["name", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": ("Load and read a skill module from ~/.simplicity/skills/<name>/SKILL.md. "
                "Skills are Claude-style modules with instructions for specific tasks. "
                "Use this when you need specialized guidance for a task category. "
                "Skills load only when invoked — their content doesn't occupy context otherwise."),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The skill name (directory name under skills/, e.g. 'debug' or 'web_scraping')",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_skill",
            "description": ("Create a new Claude-style skill module in ~/.simplicity/skills/<name>/SKILL.md. "
                "Skills extend your capabilities with specialized instructions for specific tasks. "
                "Include a description header so you know when to load it automatically."),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name (directory name, e.g. 'debug' or 'web_scraping')",
                    },
                    "description": {
                        "type": "string",
                        "description": "When to use this skill (e.g. 'Use when debugging Python code or investigating errors')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full SKILL.md markdown content with instructions, workflows, and examples",
                    },
                },
                "required": ["name", "description", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_identity",
            "description": ("Edit one of your identity files (SOUL.md, AGENTS.md, USER.md, MEMORY.md, TOOLS.md). "
                "Creates an automatic backup before editing. "
                "Use this to update your personality, rules, user info, or environment notes."),
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Which identity file to edit: 'soul', 'agents', 'user', 'memory', or 'tools'",
                        "enum": ["soul", "agents", "user", "memory", "tools"],
                    },
                    "content": {
                        "type": "string",
                        "description": "New full content for the file (replaces existing)",
                    },
                },
                "required": ["file", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_memory",
            "description": ("Write or append to a daily memory file. "
                "Use memory/YYYY-MM-DD.md for daily logs. "
                "This is your short-term memory — record what happened, decisions made, lessons learned."),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format (defaults to today)",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to append to the daily memory file",
                    },
                },
                "required": ["content"],
            },
        },
    },
]


# ── Built-in tool implementations ──────────────────────────────────

def _read_file(path: str, offset: int = 1, limit: int = 200) -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: File not found: {path}"
    if p.is_dir():
        return f"Error: Path is a directory: {path}"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)
        start = max(0, offset - 1)
        end = start + limit
        selected = lines[start:end]
        result = "\n".join(
            f"{i+1:4} | {line}" for i, line in enumerate(selected, start)
        )
        if end < total:
            result += f"\n... ({total - end} more lines)"
        return result
    except Exception as e:
        return f"Error reading file: {e}"


def _write_file(path: str, content: str) -> str:
    from simplicity.config import WORKSPACE_DIR
    p = Path(path).expanduser().resolve()
    workspace = WORKSPACE_DIR.resolve()
    # Check if target is outside workspace
    try:
        is_in_workspace = p == workspace or p.relative_to(workspace)
    except ValueError:
        is_in_workspace = False
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        msg = f"Successfully wrote {len(content)} bytes to {p}"
        if not is_in_workspace:
            msg = "⚠️  OUTSIDE WORKSPACE ⚠️\n" + msg + f"\n(workspace is: {workspace})"
        return msg
    except Exception as e:
        return f"Error writing file: {e}"


def _delete_file(path: str) -> str:
    """Delete a file. Requires user approval."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: File not found: {path}"
    if p.is_dir():
        return f"Error: Cannot delete directory with delete_file: {path}"
    try:
        p.unlink()
        return f"Deleted: {p}"
    except Exception as e:
        return f"Error deleting file: {e}"


def _list_directory(path: str = ".", show_all: bool = False) -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: Directory not found: {path}"
    if not p.is_dir():
        return f"Error: Not a directory: {path}"
    try:
        items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        lines = []
        for item in items:
            # Skip hidden files unless show_all is True
            if not show_all and item.name.startswith('.'):
                continue
            if item.is_dir():
                lines.append(f"📁 {item.name}/")
            else:
                size = item.stat().st_size
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size/1024:.1f}KB"
                else:
                    size_str = f"{size/1024/1024:.1f}MB"
                lines.append(f"📄 {item.name} ({size_str})")
        if not lines:
            return "(empty directory)"
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing directory: {e}"


def _run_command(command: str, workdir: str = ".", detach: bool = False) -> str:
    """Execute a shell command. Requires user approval for safety.
    
    When detach=True, runs the command in the background and returns a process ID
    that can be checked later with check_command. Useful for long-running tasks
    like downloads, installations, or builds.
    """
    if detach:
        from simplicity.tools import _ProcessManager
        pid = _ProcessManager.start(command, workdir)
        return (
            f"Started background process: {pid}\n"
            f"Command: {command}\n"
            f"Use check_command(id='{pid}') to check progress."
        )
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (60s)"
    except Exception as e:
        return f"Error running command: {e}"


def _web_search(query: str, count: int = 5) -> str:
    """Perform a web search using DuckDuckGo HTML."""
    import urllib.request
    import urllib.parse
    import html as html_module

    count = min(max(count, 1), 10)
    encoded = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    req = urllib.request.Request(url, headers={"User-Agent": "Simplicity/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"Search failed: {e}"

    # Extract result titles, URLs, and snippets
    results = []
    import re
    # Each result is a 'result__body' div with title link and snippet
    snippets = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )
    for url, title, snippet in snippets[:count]:
        title = re.sub(r"<[^>]+>", "", title).strip()
        snippet = re.sub(r"<[^>]+>", "", snippet).strip()
        title = html_module.unescape(title)
        snippet = html_module.unescape(snippet)
        url = html_module.unescape(url)
        if title:
            results.append(f"**{title}**\n  {snippet}\n  URL: {url}")

    if not results:
        return f"No results found for: {query}"
    return "\n\n".join(results)


def _web_fetch(url: str) -> str:
    """Fetch and extract text content from a URL."""
    import urllib.request
    import urllib.error

    if not url.startswith(("http://", "https://")):
        return f"Error: URL must start with http:// or https:// (got: {url})"

    req = urllib.request.Request(url, headers={"User-Agent": "Simplicity/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            # Check content type
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            # Limit to ~50KB
            if len(raw) > 50_000:
                raw = raw[:50_000]
            text = raw.decode("utf-8", errors="replace")

            # If HTML, try to extract readable text
            if "text/html" in content_type or text.strip().startswith(("<!DOCTYPE", "<html", "<HTML")):
                return _extract_text_from_html(text, url)
            else:
                return text[:10_000]
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.reason} for {url}"
    except urllib.error.URLError as e:
        return f"Connection error: {e.reason} for {url}"
    except Exception as e:
        return f"Fetch error: {e} for {url}"


def _extract_text_from_html(html: str, url: str = "") -> str:
    """Extract readable text from HTML, stripping tags and scripts."""
    import re
    # Remove script and style sections
    text = re.sub(r"<(script|style|nav|header|footer|iframe)[^>]*>[\s\S]*?</\1>", " ", html, flags=re.IGNORECASE)
    # Remove HTML comments
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    # Remove remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities
    import html as html_module
    text = html_module.unescape(text)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trim and limit
    text = text.strip()
    if len(text) > 10_000:
        text = text[:10_000] + "\n... (truncated)"
    if not text:
        return f"(No readable text content extracted from {url})"
    return f"Content from {url}:\n\n{text}"


def _get_current_time() -> str:
    """Return the current date and time."""
    from datetime import datetime
    now = datetime.now()
    return (
        f"Current date: {now.strftime('%A, %B %d, %Y')}\n"
        f"Current time: {now.strftime('%I:%M:%S %p %Z')}\n"
        f"ISO: {now.isoformat()}"
    )


# ── Process tracking for background commands ────────────────────

class _ProcessManager:
    """Tracks background processes for the check_command tool."""

    _dir = Path.home() / ".simplicity" / "processes"

    @classmethod
    def _ensure_dir(cls):
        cls._dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def start(cls, command: str, workdir: str) -> str:
        """Start a background process and return its ID."""
        import uuid
        import threading
        from datetime import datetime
        cls._ensure_dir()
        pid = uuid.uuid4().hex[:8]
        state_file = cls._dir / f"{pid}.json"

        state = {
            "id": pid, "command": command, "workdir": workdir,
            "status": "running", "started": datetime.now().isoformat(),
            "output": "", "exit_code": None
        }
        state_file.write_text(json.dumps(state))

        def _run():
            try:
                proc = subprocess.Popen(
                    command, shell=True, cwd=workdir,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True
                )
                state["pid"] = proc.pid
                for line in proc.stdout:
                    state["output"] += line
                    if len(state["output"]) > 10240:
                        state["output"] = "...(earlier output truncated)\n" + state["output"][-8192:]
                    state_file.write_text(json.dumps(state))
                proc.wait()
                state["exit_code"] = proc.returncode
                state["status"] = "completed" if proc.returncode == 0 else "error"
            except Exception as e:
                state["status"] = "error"
                state["output"] += f"\n[Process error: {e}]"
            state_file.write_text(json.dumps(state))

        threading.Thread(target=_run, daemon=True).start()
        return pid

    @classmethod
    def check(cls, pid: str) -> str:
        """Check the status and output of a background process."""
        cls._ensure_dir()
        state_file = cls._dir / f"{pid}.json"
        if not state_file.exists():
            return f"No process found with ID: {pid}"
        state = json.loads(state_file.read_text())
        status_emoji = {"running": "🔄", "completed": "✅", "error": "❌"}
        emoji = status_emoji.get(state["status"], "❓")
        lines = [
            f"{emoji} Process {pid}: {state['status'].upper()}",
            f"   Command: {state['command']}",
            f"   Started: {state['started']}",
        ]
        if state.get("pid"):
            lines.append(f"   PID: {state['pid']}")
        if state.get("exit_code") is not None:
            lines.append(f"   Exit code: {state['exit_code']}")
        if state["output"]:
            lines.append(f"\n--- output ---\n{state['output'].rstrip()}\n--- end ---")
        return "\n".join(lines)


def _check_command(process_id: str) -> str:
    """Check the status and output of a background command."""
    return _ProcessManager.check(process_id)


def _update_skillsheet(section: str, content: str) -> str:
    """Update a section of SKILLSHEET.md with automatic backup."""
    from simplicity.config import SKILLSHEET_FILE, SKILLS_DIR, init_skillsheet
    import re
    
    # Ensure skillsheet exists
    init_skillsheet()
    
    # Create backup
    backup = SKILLSHEET_FILE.with_suffix(".backup.md")
    backup.write_text(SKILLSHEET_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    
    current = SKILLSHEET_FILE.read_text(encoding="utf-8")
    
    # Find or create the section
    section_heading = f"## {section}"
    pattern = re.compile(
        rf"^(## {re.escape(section)}\s*\n)(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL
    )
    match = pattern.search(current)
    
    if match:
        # Replace existing section content
        new_content = f"{match.group(1)}{content.strip()}\n\n"
        updated = current[:match.start()] + new_content + current[match.end():]
    else:
        # Append new section at end
        updated = current.rstrip() + f"\n\n---\n\n## {section}\n\n{content.strip()}\n"
    
    SKILLSHEET_FILE.write_text(updated, encoding="utf-8")
    return f"✅ Updated skillsheet section '{section}' (backup saved to {backup.name})"


def _create_skill_doc(name: str, content: str) -> str:
    """Create a focused sub-sheet for a specific skill."""
    from simplicity.config import SKILLS_DIR
    import re
    
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Sanitize filename
    safe_name = re.sub(r'[^a-z0-9_-]', '_', name.lower())[:50]
    skill_path = SKILLS_DIR / f"{safe_name}.md"
    
    if skill_path.exists():
        # Backup existing
        backup = skill_path.with_suffix(".backup.md")
        backup.write_text(skill_path.read_text(encoding="utf-8"), encoding="utf-8")
    
    skill_path.write_text(content, encoding="utf-8")
    return f"✅ Created skill doc: {skill_path}\nRead it with read_file(path='{skill_path}')"


def _load_skill(name: str) -> str:
    """Load and read a Claude-style skill module."""
    from simplicity.config import SKILLS_DIR
    import re
    
    safe_name = re.sub(r'[^a-z0-9_-]', '_', name.lower())[:50]
    skill_file = SKILLS_DIR / safe_name / "SKILL.md"
    
    if not skill_file.exists():
        # Also try direct .md file (old format)
        skill_file = SKILLS_DIR / f"{safe_name}.md"
        if not skill_file.exists():
            available = []
            if SKILLS_DIR.exists():
                for d in SKILLS_DIR.iterdir():
                    if d.is_dir() and (d / "SKILL.md").exists():
                        available.append(d.name)
                    elif d.suffix == '.md':
                        available.append(d.stem)
            if available:
                return f"Skill '{name}' not found. Available skills: {', '.join(sorted(available))}"
            return f"Skill '{name}' not found at {skill_file}. Use create_skill to make one."
    
    content = skill_file.read_text(encoding="utf-8")
    return f"--- SKILL: {name} ---\n\n{content}\n\n--- End of skill: {name} ---"


def _create_skill(name: str, description: str, content: str) -> str:
    """Create a new Claude-style skill module."""
    from simplicity.config import SKILLS_DIR
    import re
    
    safe_name = re.sub(r'[^a-z0-9_-]', '_', name.lower())[:50]
    skill_dir = SKILLS_DIR / safe_name
    skill_file = skill_dir / "SKILL.md"
    
    if skill_file.exists():
        # Backup existing
        backup = skill_file.with_suffix(".backup.md")
        backup.write_text(skill_file.read_text(encoding="utf-8"), encoding="utf-8")
    
    skill_dir.mkdir(parents=True, exist_ok=True)
    
    full_content = f"""# {name}

> {description}

{content}
"""
    skill_file.write_text(full_content, encoding="utf-8")
    return f"✅ Created skill '{name}' at {skill_file}\nLoad it with: load_skill(name='{safe_name}')"


def _edit_identity(file: str, content: str) -> str:
    """Edit an identity file with automatic backup."""
    from simplicity.config import (
        SOUL_FILE, AGENTS_FILE, USER_FILE, MEMORY_FILE, TOOLS_FILE
    )
    
    file_map = {
        "soul": SOUL_FILE,
        "agents": AGENTS_FILE,
        "user": USER_FILE,
        "memory": MEMORY_FILE,
        "tools": TOOLS_FILE,
    }
    
    if file not in file_map:
        return f"Unknown identity file: {file}. Use: {', '.join(file_map.keys())}"
    
    target = file_map[file]
    
    # Backup if exists
    if target.exists():
        backup = target.with_suffix(".backup.md")
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    
    target.write_text(content, encoding="utf-8")
    return f"✅ Updated {target.name} (backup saved)"


def _write_memory(date: str = "", content: str = "") -> str:
    """Append to a daily memory file."""
    from simplicity.config import MEMORY_DIR
    from datetime import datetime
    
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    memory_file = MEMORY_DIR / f"{date}.md"
    
    timestamp = datetime.now().strftime("%H:%M")
    entry = f"\n## {timestamp}\n\n{content}\n"
    
    with open(memory_file, "a", encoding="utf-8") as f:
        f.write(entry)
    
    return f"✅ Appended to {memory_file}"


# ── Tool registry ──────────────────────────────────────────────────

def _create_tool(name: str, description: str, parameters_schema: dict, code: str, toolscript: dict = None) -> str:
    """Create a new custom tool. Supports simple tools and folder-based toolscripts."""
    import re
    import json as _json
    
    # Validate name
    if not re.match(r'^[a-z][a-z0-9_]*$', name):
        return f"Error: Invalid tool name '{name}'. Use snake_case (lowercase letters, numbers, underscores)."
    
    tools_dir = Path.home() / ".simplicity" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    
    # Build the tool definition
    tool_def = {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters_schema,
        },
    }
    
    tool_file = f'''"""Custom tool: {name} — {description}"""

import json

TOOL_DEFINITION = {_json.dumps(tool_def, indent=2)}

{code}
'''

    # ── Toolscript mode: folder-based tool with prerequisites ──
    if toolscript and isinstance(toolscript, dict):
        tool_dir = tools_dir / name
        if tool_dir.exists():
            return f"Error: Tool folder '{name}' already exists at {tool_dir}."
        tool_dir.mkdir(parents=True, exist_ok=True)
        
        # Write main tool.py
        (tool_dir / "tool.py").write_text(tool_file, encoding="utf-8")
        
        # Write README.md
        readme = toolscript.get("readme", "")
        if readme:
            (tool_dir / "README.md").write_text(readme, encoding="utf-8")
        
        # Write additional scripts
        scripts = toolscript.get("scripts", {})
        if scripts:
            scripts_dir = tool_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            for script_name, script_content in scripts.items():
                safe_name = Path(script_name).name  # prevent path traversal
                (scripts_dir / safe_name).write_text(script_content, encoding="utf-8")
        
        # Generate and write installer
        prerequisites = toolscript.get("prerequisites", [])
        if prerequisites:
            is_windows = sys.platform == "win32"
            if is_windows:
                installer = "@echo off\nREM Installer for {name}\n\n".format(name=name)
                for prereq in prerequisites:
                    installer += f"{prereq}\n"
                installer += f"\necho ✅ {name} prerequisites installed!\npause\n"
                (tool_dir / "install.bat").write_text(installer, encoding="utf-8")
            else:
                installer = "#!/bin/bash\n# Installer for {name}\nset -e\n\n".format(name=name)
                for prereq in prerequisites:
                    installer += f"{prereq}\n"
                installer += f"\necho '✅ {name} prerequisites installed!'\n"
                (tool_dir / "install.sh").write_text(installer, encoding="utf-8")
                # Make executable
                (tool_dir / "install.sh").chmod(0o755)
        
        return (
            f"✅ Toolscript '{name}' created at {tool_dir}\n"
            f"   Files: tool.py"
            + (f", README.md" if readme else "")
            + (f", {len(scripts)} script(s)" if scripts else "")
            + (f", installer" if prerequisites else "")
            + f"\n   Description: {description}"
        )
    
    # ── Simple mode: single .py file ──
    tool_path = tools_dir / f"{name}.py"
    if tool_path.exists():
        return f"Error: Tool '{name}' already exists at {tool_path}. Use a different name or delete the existing one."
    
    try:
        tool_path.write_text(tool_file, encoding="utf-8")
        return (
            f"✅ Tool '{name}' created successfully at {tool_path}.\n"
            f"The tool is now available in your next message.\n"
            f"Description: {description}"
        )
    except Exception as e:
        return f"Error creating tool: {e}"


BUILTIN_EXECUTORS = {
    "read_file": _read_file,
    "write_file": _write_file,
    "delete_file": _delete_file,
    "list_directory": _list_directory,
    "run_command": _run_command,
    "check_command": _check_command,
    "web_search": _web_search,
    "web_fetch": _web_fetch,
    "get_current_time": _get_current_time,
    "update_skillsheet": _update_skillsheet,
    "create_skill_doc": _create_skill_doc,
    "load_skill": _load_skill,
    "create_skill": _create_skill,
    "edit_identity": _edit_identity,
    "write_memory": _write_memory,
    "create_tool": _create_tool,
}


class ToolRegistry:
    """Manages available tools and their execution."""

    def __init__(self, tools_dir: Path):
        self.tools_dir = tools_dir
        self.custom_definitions: list[dict] = []
        self.custom_executors: dict[str, callable] = {}
        self._loaded = False

    def load_custom_tools(self):
        """Load custom tools from the tools directory."""
        if self._loaded:
            return
        self._loaded = True

        if not self.tools_dir.exists():
            return

        for py_file in sorted(self.tools_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"simplicity_tool_{py_file.stem}", py_file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, "TOOL_DEFINITION") and hasattr(module, "execute"):
                    tool_def = module.TOOL_DEFINITION
                    self.custom_definitions.append(tool_def)
                    name = tool_def.get("function", {}).get("name", py_file.stem)
                    self.custom_executors[name] = module.execute
            except Exception as e:
                print(f"⚠️  Failed to load tool {py_file.name}: {e}", file=sys.stderr)

    def get_definitions(self) -> list[dict]:
        """Get all tool definitions (built-in + custom)."""
        self.load_custom_tools()
        return BUILT_IN_TOOLS + self.custom_definitions

    def execute(self, name: str, arguments: dict) -> str:
        """Execute a tool by name with the given arguments."""
        self.load_custom_tools()

        executor = BUILTIN_EXECUTORS.get(name) or self.custom_executors.get(name)
        if not executor:
            return f"Error: Unknown tool '{name}'"

        try:
            return executor(**arguments)
        except TypeError as e:
            return f"Error: Invalid arguments for tool '{name}': {e}"
        except Exception as e:
            return f"Error executing tool '{name}': {e}"

    def requires_approval(self, name: str) -> bool:
        """Check if a tool needs user approval before execution."""
        dangerous = {"run_command", "write_file", "delete_file", "create_tool"}
        return name in dangerous

    def list_tools(self) -> list[dict]:
        """List all tools with names and descriptions."""
        result = []
        for tool in self.get_definitions():
            fn = tool.get("function", {})
            name = fn.get("name", "unknown")
            desc = fn.get("description", "")
            is_builtin = name in BUILTIN_EXECUTORS
            result.append(
                {
                    "name": name,
                    "description": desc,
                    "builtin": is_builtin,
                    "dangerous": self.requires_approval(name),
                }
            )
        return result

    def get_tool_names(self) -> list[str]:
        return [t["name"] for t in self.list_tools()]
