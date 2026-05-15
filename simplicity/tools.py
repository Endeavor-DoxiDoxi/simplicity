"""Tool system for Simplicity.

Built-in tools:
  - read_file: Read file contents
  - write_file: Create or overwrite a file
  - list_directory: List files in a directory
  - run_command: Execute a shell command

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
                "Use this when you need a capability that doesn't exist yet — "
                "like accessing a specific API, performing specialized calculations, "
                "or integrating with an external service. "
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
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command and return the output. Use with caution.",
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
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information. Returns search results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                },
                "required": ["query"],
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
    p = Path(path).expanduser().resolve()
    workspace = Path.cwd().resolve()
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


def _list_directory(path: str = ".") -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: Directory not found: {path}"
    if not p.is_dir():
        return f"Error: Not a directory: {path}"
    try:
        items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        lines = []
        for item in items:
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


def _run_command(command: str, workdir: str = ".") -> str:
    """Execute a shell command. Requires user approval for safety."""
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


def _web_search(query: str) -> str:
    """Perform a web search and return results."""
    # Use DuckDuckGo HTML search (no API key needed)
    import urllib.request
    import html as html_module

    encoded = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    req = urllib.request.Request(url, headers={"User-Agent": "Simplicity/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"Search failed: {e}"

    # Basic extraction of result snippets
    results = []
    import re
    # Extract result titles and snippets
    snippets = re.findall(
        r'<a[^>]*class="result__a"[^>]*>(.*?)</a>.*?<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )
    for title, snippet in snippets[:8]:
        title = re.sub(r"<[^>]+>", "", title).strip()
        snippet = re.sub(r"<[^>]+>", "", snippet).strip()
        title = html_module.unescape(title)
        snippet = html_module.unescape(snippet)
        if title:
            results.append(f"• {title}\n  {snippet}")

    if not results:
        return f"No results found for: {query}"
    return "\n\n".join(results)


# ── Tool registry ──────────────────────────────────────────────────

def _create_tool(name: str, description: str, parameters_schema: dict, code: str) -> str:
    """Create a new custom tool by writing a Python file to the tools directory."""
    import re
    
    # Validate name
    if not re.match(r'^[a-z][a-z0-9_]*$', name):
        return f"Error: Invalid tool name '{name}'. Use snake_case (lowercase letters, numbers, underscores)."
    
    tools_dir = Path.home() / ".simplicity" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    
    tool_path = tools_dir / f"{name}.py"
    if tool_path.exists():
        return f"Error: Tool '{name}' already exists at {tool_path}. Use a different name or delete the existing one."
    
    # Build the tool definition
    tool_def = {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters_schema,
        },
    }
    
    # Generate the tool file
    import json as _json
    tool_file = f'''"""Custom tool: {name} — {description}"""

import json

TOOL_DEFINITION = {_json.dumps(tool_def, indent=2)}

{code}
'''
    
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
    "list_directory": _list_directory,
    "run_command": _run_command,
    "web_search": _web_search,
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
        dangerous = {"run_command", "write_file", "create_tool"}
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
