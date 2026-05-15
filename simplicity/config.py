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
        "You have tools for reading/writing files, running commands,\n"
        "searching the web, and creating new tools when needed.\n\n"
        "Guidelines:\n"
        "- Be concise and direct. Don't list your features unless asked.\n"
        "- When coding, write clean, working code with brief explanations.\n"
        "- Use tools proactively — read files before asking, search before guessing.\n"
        "- Write files inside the workspace (current directory) by default.\n"
        "  Writing outside the workspace is allowed but requires approval.\n"
        "- For dangerous operations (run_command, write_file outside workspace),\n"
        "  the user must approve. Respect that.\n"
        "- Be resourceful: try to figure things out before asking for help."
    ),
    "max_tokens": 4096,
    "temperature": 0.7,
    "stream": True,
}

CONFIG_DIR = Path.home() / ".simplicity"
CONFIG_FILE = CONFIG_DIR / "config.json"
TOOLS_DIR = CONFIG_DIR / "tools"
HISTORY_DIR = CONFIG_DIR / "history"


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
