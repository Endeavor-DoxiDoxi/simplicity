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

from simplicity.providers import _strip_think_tags


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
    # Strip think tags before rendering
    content = _strip_think_tags(content)
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
            # Regular text — convert basic inline markdown to Rich markup
            if part.strip():
                text = part.strip()
                # Convert **bold** → Rich bold, *italic* → italic, `code` → dim
                text = re.sub(r'\*\*(.+?)\*\*', r'[bold]\1[/bold]', text)
                text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'[italic]\1[/italic]', text)
                text = re.sub(r'`([^`]+?)`', r'[dim]\1[/dim]', text)
                result.append(Text.from_markup(text))
                result.append("\n")

    return result


def stream_token(token: str):
    """Print a single streaming token. Called repeatedly during streaming."""
    clean = _strip_think_tags(token)
    if clean:
        console.print(clean, end="", highlight=False)


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
  [cyan]/setup[/]     Guided identity setup
  [cyan]/export[/]    Export agent to ZIP
  [cyan]/debug[/]     Run self-diagnostic
  [cyan]/clear[/]     Clear conversation history
  [cyan]/model[/]     Show/set current model
  [cyan]/models[/]    List available models
  [cyan]/balance[/]   Check pollen balance
  [cyan]/usage[/]     View balance + usage history
  [cyan]/tools[/]     List available tools
  [cyan]/save[/]      Save conversation to file
  [cyan]/system[/]    Set custom system prompt
  [cyan]/skillsheet[/] Read the skillsheet docs
  [cyan]/disconnect[/] Remove API key

[bold]Keyboard Shortcuts:[/]
  [cyan]Ctrl+C[/]     Interrupt generation
  [cyan]Ctrl+D[/]     Exit chat
"""
    console.print(help_content)


def show_models_detail(models_data):
    """Display text models with rich detail (authenticated endpoint)."""
    if not models_data:
        console.print("[red]Failed to fetch models[/]")
        return

    if isinstance(models_data, dict):
        models = models_data.get("models") or models_data.get("data") or []
    elif isinstance(models_data, list):
        models = models_data
    else:
        models = []

    if not models:
        console.print("[yellow]No models found[/]")
        return

    table = Table(title="🌸 Pollinations Text Models", border_style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Price", style="yellow")
    table.add_column("Context", style="blue")
    table.add_column("Tools", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Description", style="dim")

    for m in models:
        if not isinstance(m, dict):
            continue
        name = m.get("name", "?")
        pricing = m.get("pricing", {})
        if pricing:
            prompt_p = float(pricing.get("promptTextTokens", 0)) * 1e6
            comp_p = float(pricing.get("completionTextTokens", 0)) * 1e6
            if prompt_p > 0:
                price_str = f"{prompt_p:.1f}/{comp_p:.1f}"
            else:
                price_str = "?"
        else:
            price_str = "?"
        
        ctx = m.get("context_length", 0)
        if ctx >= 1_000_000:
            ctx_str = f"{ctx/1_000_000:.0f}M"
        elif ctx >= 1000:
            ctx_str = f"{ctx/1000:.0f}K"
        else:
            ctx_str = str(ctx) if ctx else "?"
        
        tools = "✓" if m.get("tools") else "-"
        reasoning = "🧠" if m.get("reasoning") else ""
        paid = m.get("paid_only", False)
        status = "[red]💳 paid[/]" if paid else "[green]free[/]"
        desc = (m.get("description") or "")[:60]
        
        table.add_row(name, price_str, ctx_str, f"{tools}{reasoning}", status, desc)

    console.print(table)


def show_usage(usage_data: dict):
    """Display pollen balance and recent usage history."""
    if not usage_data:
        console.print("[yellow]No usage data available[/]")
        return

    entries = usage_data.get("usage", [])
    if not entries:
        console.print("[dim]No recent usage to show. Make some requests first![/]")
        return

    table = Table(title="📊 Recent Usage", border_style="cyan")
    table.add_column("Date", style="dim")
    table.add_column("Model", style="green")
    table.add_column("Type", style="blue")
    table.add_column("Tokens", style="yellow")
    table.add_column("Cost", style="magenta")

    total_cost = 0
    for entry in entries[:25]:  # Show last 25
        ts = entry.get("timestamp", "?")[:16]
        model = entry.get("model", "?") or "?"
        etype = entry.get("type", "?").replace("generate.", "")
        
        inp_tok = entry.get("input_text_tokens") or entry.get("input_tokens") or 0
        out_tok = entry.get("output_text_tokens") or entry.get("output_tokens") or 0
        tokens = f"{inp_tok}→{out_tok}"
        
        cost = entry.get("cost", 0)
        total_cost += cost
        cost_str = f"{cost:.4f}🌸" if cost else "-"
        
        table.add_row(ts, model, etype, tokens, cost_str)

    console.print(table)
    console.print(f"[dim]Total cost shown: [yellow]{total_cost:.4f}🌸[/][/]")


def show_balance_detail(balance_data: dict):
    """Display pollen balance with more detail."""
    balance = balance_data.get("balance", "?")
    console.print(f"[green]🌸 Pollen balance: [bold]{balance}[/][/]")


def save_confirmation(path: str, messages: int):
    """Confirm conversation saved."""
    console.print(f"[green]💾 Saved {messages} messages to {path}[/]")
