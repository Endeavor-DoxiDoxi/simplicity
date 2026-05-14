"""Rich terminal output formatting for Simplicity."""

import re
import textwrap
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.columns import Columns


console = Console()
_DEBUG = False


def debug(msg: str):
    """Print debug message if debug mode is on."""
    if _DEBUG:
        console.print(f"[dim]🔧 {msg}[/]")


def welcome():
    """Print the welcome banner."""
    banner = r"""
  🌸  [bold cyan]S I M P L I C I T Y[/]
  [dim]AI Chat CLI · Powered by Pollinations.ai[/]
  [dim]Type /help for commands · /quit to exit[/]"""
    console.print(banner)


def thinking():
    """Show thinking indicator."""
    return console.status("[dim]🤔 Thinking...[/]", spinner="dots")


def tool_call_indicator(name: str, args: dict):
    """Show tool being called."""
    short_args = ", ".join(f"{k}={str(v)[:40]}" for k, v in args.items())
    console.print(f"  [yellow]🔧[/] [bold yellow]{name}[/] [dim]({short_args})[/]")


def tool_result(result: str, max_lines: int = 8):
    """Show tool result."""
    lines = result.strip().splitlines()
    if len(lines) > max_lines:
        preview = "\n".join(lines[:max_lines])
        console.print(f"  [dim]├─ {preview}[/]")
        console.print(f"  [dim]└─ ... ({len(lines) - max_lines} more lines)[/]")
    else:
        for line in lines:
            console.print(f"  [dim]├─ {line}[/]")


def approval_prompt(name: str, args: dict) -> bool:
    """Ask user to approve a dangerous tool call."""
    console.print()
    console.print(
        Panel(
            f"[bold yellow]⚠️  Tool requires approval[/]\n\n"
            f"[bold]{name}[/]\n"
            + "\n".join(f"  {k}: [cyan]{v}[/]" for k, v in args.items()),
            border_style="yellow",
            title="Approval Required",
        )
    )
    response = input("  Allow? [y/N] ").strip().lower()
    return response in ("y", "yes")


def render_assistant_message(content: str):
    """Render the assistant's message with markdown and syntax highlighting."""
    if not content.strip():
        return
    # Don't use rich Markdown for the full text because it's slow for large
    # outputs. Instead, we manually handle code blocks for syntax highlighting.
    rendered = _render_with_code_blocks(content)
    console.print(rendered)


def _render_with_code_blocks(text: str) -> Text:
    """Process text, syntax-highlighting code blocks."""
    parts = re.split(r"(```\w*\n.*?```)", text, flags=re.DOTALL)
    result = Text()

    for part in parts:
        if part.startswith("```"):
            # Extract language and code
            match = re.match(r"```(\w*)\n(.*?)```", part, re.DOTALL)
            if match:
                lang = match.group(1) or "text"
                code = match.group(2).rstrip()
                if lang in ("bash", "sh", "shell", "zsh"):
                    syntax = Syntax(code, "bash", theme="monokai", line_numbers=False)
                elif lang in ("python", "py"):
                    syntax = Syntax(code, "python", theme="monokai", line_numbers=False)
                elif lang in ("javascript", "js", "typescript", "ts"):
                    syntax = Syntax(code, "javascript", theme="monokai", line_numbers=False)
                elif lang in ("json"):
                    syntax = Syntax(code, "json", theme="monokai", line_numbers=False)
                elif lang in ("html", "css"):
                    syntax = Syntax(code, lang, theme="monokai", line_numbers=False)
                elif lang in ("rust", "rs"):
                    syntax = Syntax(code, "rust", theme="monokai", line_numbers=False)
                elif lang in ("go"):
                    syntax = Syntax(code, "go", theme="monokai", line_numbers=False)
                elif lang in ("java", "kotlin", "scala"):
                    syntax = Syntax(code, lang, theme="monokai", line_numbers=False)
                elif lang in ("sql"):
                    syntax = Syntax(code, "sql", theme="monokai", line_numbers=False)
                elif lang in ("yaml", "yml", "toml", "ini", "cfg"):
                    syntax = Syntax(code, "ini", theme="monokai", line_numbers=False)
                elif lang in ("diff"):
                    syntax = Syntax(code, "diff", theme="monokai", line_numbers=False)
                else:
                    syntax = Syntax(code, "text", theme="monokai", line_numbers=False)
                result.append("\n")
                result.append(syntax)
                result.append("\n")
            else:
                result.append(part)
        else:
            # Regular text — use rich Markdown for inline formatting
            md = Markdown(part.strip(), inline_code_lexer="python")
            result.append(md) if part.strip() else None

    return result


def stream_token(token: str):
    """Print a single streaming token. Called repeatedly during streaming."""
    console.print(token, end="", highlight=False)


def stream_done():
    """Called when streaming is complete."""
    console.print()  # final newline


def show_models(models_data):
    """Display available models in a table."""
    if not models_data:
        console.print("[red]Failed to fetch models[/]")
        return

    # Handle both array and object responses
    if isinstance(models_data, list):
        models = models_data
    elif isinstance(models_data, dict):
        # Could be {models: [...]} or {data: [...]}
        models = models_data.get("models") or models_data.get("data") or []
    else:
        models = []

    if not models:
        console.print("[yellow]No models found[/]")
        return

    table = Table(title="🌸 Available Pollinations Models", border_style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Pricing", style="yellow")
    table.add_column("Description", style="dim")

    for m in models:
        if isinstance(m, str):
            table.add_row(m, "", "")
        elif isinstance(m, dict):
            name = m.get("name") or m.get("id") or m.get("model", "?")
            pricing = m.get("pricing", {})
            if not pricing:
                price_str = ""
            else:
                prompt_price = float(pricing.get("promptTextTokens", 0))
                comp_price = float(pricing.get("completionTextTokens", 0))
                if prompt_price > 0:
                    price_str = f"{prompt_price*1e6:.2f}/{comp_price*1e6:.2f} µ🌸/tok"
                else:
                    # Image/video/audio model
                    img_price = pricing.get("completionImageTokens")
                    vid_price = pricing.get("completionVideoSeconds")
                    aud_price = pricing.get("completionAudioSeconds")
                    if img_price:
                        price_str = f"{img_price}🌸/img"
                    elif vid_price:
                        price_str = f"{vid_price}🌸/sec"
                    elif aud_price:
                        price_str = f"{aud_price}🌸/sec"
                    else:
                        price_str = "?"
            desc = (m.get("description") or "")[:70]
            table.add_row(name, price_str, desc)

    console.print(table)


def show_balance(balance_data: dict):
    """Display pollen balance."""
    balance = balance_data.get("balance", "?")
    console.print(f"[green]🌸 Pollen balance: {balance}[/]")


def model_info(model: str):
    """Show current model info."""
    console.print(f"[dim]Model:[/] [green]{model}[/]")


def error_message(msg: str):
    """Show an error message."""
    console.print(f"\n[red]❌ {msg}[/]\n")


def warn_message(msg: str):
    """Show a warning."""
    console.print(f"[yellow]⚠️  {msg}[/]")


def success_message(msg: str):
    """Show a success message."""
    console.print(f"[green]✅ {msg}[/]")


def help_text():
    """Show help for chat mode."""
    help_content = """
[bold]Chat Commands:[/]
  [cyan]/help[/]      Show this help
  [cyan]/quit[/]      Exit chat
  [cyan]/clear[/]     Clear conversation history
  [cyan]/model[/]     Show/set current model
  [cyan]/balance[/]   Check pollen balance
  [cyan]/tools[/]     List available tools
  [cyan]/save[/]      Save conversation to file
  [cyan]/system[/]    Set custom system prompt

[bold]Keyboard Shortcuts:[/]
  [cyan]Ctrl+C[/]     Interrupt generation
  [cyan]Ctrl+D[/]     Exit chat
"""
    console.print(help_content)


def save_confirmation(path: str, messages: int):
    """Confirm conversation saved."""
    console.print(f"[green]💾 Saved {messages} messages to {path}[/]")
