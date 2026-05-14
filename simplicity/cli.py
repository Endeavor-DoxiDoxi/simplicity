"""Command-line interface for Simplicity.

Commands:
  simplicity chat       Start interactive chat (default)
  simplicity ask <msg>  One-shot question
  simplicity setup      Configure API key and settings
  simplicity models     List available models
  simplicity balance    Check pollen balance
  simplicity tools      List available tools
"""

import argparse
import os
import sys
from pathlib import Path

from simplicity.config import Config
from simplicity.display import (
    console,
    error_message,
    success_message,
    show_models,
    show_models_detail,
    show_balance,
    show_balance_detail,
    show_usage,
    welcome,
)
from simplicity.chat import ChatSession, one_shot
from simplicity.tools import ToolRegistry
from simplicity.client import SimplicityClient, SimplicityAPIError


def cmd_chat(args):
    """Start interactive chat session."""
    config = Config().load()

    if not config.is_configured():
        error_message("No API key configured.")
        console.print("Run [bold]simplicity setup[/] first, or set [bold]SIMPLICITY_API_KEY[/] env var.")
        sys.exit(1)

    if args.model:
        config.set("model", args.model)

    session = ChatSession(config)
    session.run()


def cmd_ask(args):
    """One-shot question mode."""
    config = Config().load()

    if not config.is_configured():
        error_message("No API key configured. Run 'simplicity setup' first.")
        sys.exit(1)

    if args.model:
        config.data["model"] = args.model

    one_shot(config, args.prompt, no_stream=args.no_stream)


def cmd_setup(args):
    """Interactive setup wizard."""
    config = Config().load()
    config.setup_wizard()


def cmd_models(args):
    """List available Pollinations models."""
    config = Config().load()
    
    if config.is_configured():
        console.print("[dim]Fetching your available models (authenticated)...[/]")
        models = SimplicityClient.fetch_models(api_key=config.api_key)
        show_models_detail(models)
    else:
        console.print("[dim]Fetching models from Pollinations...[/]")
        console.print("[dim](Sign in for your personalized model list)[/]")
        models = SimplicityClient.fetch_models()
        show_models(models)


def cmd_balance(args):
    """Check pollen balance."""
    config = Config().load()

    if not config.is_configured():
        error_message("No API key configured. Run 'simp auth' first.")
        sys.exit(1)

    try:
        balance = SimplicityClient.fetch_balance(config.api_key)
        show_balance_detail(balance)
    except SimplicityAPIError as e:
        error_message(f"Could not fetch balance: {e}")
    except Exception as e:
        error_message(f"Could not fetch balance: {e}")


def cmd_discord(args):
    """Start the Simplicity Discord bot."""
    token = args.token or os.environ.get("DISCORD_TOKEN")
    if not token:
        error_message("No Discord token provided.")
        console.print("Set DISCORD_TOKEN env var or pass --token")
        console.print("Get a token at: https://discord.com/developers/applications")
        sys.exit(1)
    from simplicity.discord_connector import run_discord
    run_discord(token)


def cmd_web(args):
    """Start the Simplicity web UI."""
    from simplicity.webui import run_webui
    run_webui(port=args.port)


def cmd_usage(args):
    """Show pollen balance and recent usage history."""
    config = Config().load()

    if not config.is_configured():
        error_message("No API key configured. Run 'simp auth' first.")
        sys.exit(1)

    # Balance
    try:
        balance = SimplicityClient.fetch_balance(config.api_key)
        show_balance_detail(balance)
    except SimplicityAPIError as e:
        error_message(f"Balance check failed: {e}")
    except Exception:
        console.print("[dim]Balance: (unavailable)[/]")

    console.print()

    # Usage history
    try:
        usage = SimplicityClient.fetch_usage(config.api_key, days=args.days)
        show_usage(usage)
    except SimplicityAPIError as e:
        if e.status == 403:
            console.print("[dim]Usage history requires account:usage permission.[/]")
            console.print("[dim]Add this scope to your API key or re-run simp auth.[/]")
        else:
            error_message(f"Usage fetch failed: {e}")
    except Exception as e:
        error_message(f"Could not fetch usage: {e}")


def cmd_update(args):
    """Update Simplicity to the latest version."""
    import subprocess
    
    # Find the update script
    update_script = None
    for name in ["update.sh", "update.bat"]:
        path = Path(__file__).parent.parent / name
        if path.exists():
            update_script = path
            break
    
    if not update_script:
        error_message("Update script not found. Try 'git pull' manually.")
        sys.exit(1)
    
    console.print("[dim]Running updater...[/]")
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", str(update_script)], cwd=update_script.parent)
    else:
        subprocess.run(["bash", str(update_script)], cwd=update_script.parent)


def cmd_disconnect(args):
    """Remove the saved API key."""
    config = Config().load()
    if config.api_key:
        config.set("api_key", "")
        success_message("API key removed. Run 'simp auth' to reconnect.")
    else:
        console.print("[dim]No API key is currently saved.[/]")


def cmd_auth(args):
    """BYOP login — sign in with Pollinations (web redirect + device fallback)."""
    from simplicity.auth import byop_login, DeviceFlowError, WebRedirectCancelled
    from simplicity.config import Config

    config = Config().load()

    try:
        api_key = byop_login(console=console, force_device=args.device)
        config.set("api_key", api_key)
        success_message("API key saved! You're ready to go.")
        console.print("[dim]Run [bold]simp chat[/] to start chatting.[/]")
    except WebRedirectCancelled:
        console.print("\n[dim]Login cancelled.[/]")
        sys.exit(0)
    except DeviceFlowError as e:
        error_message(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Login cancelled.[/]")
        sys.exit(0)


def cmd_tools(args):
    """List available tools."""
    registry = ToolRegistry(Path.home() / ".simplicity" / "tools")
    tools = registry.list_tools()

    if not tools:
        console.print("[dim]No tools available.[/]")
        console.print(
            f"[dim]Add custom tools to ~/.simplicity/tools/ (Python files with TOOL_DEFINITION + execute)[/]"
        )
        return

    console.print("\n[bold]Available Tools:[/]\n")
    for t in tools:
        badge = " [yellow]⚠️[/]" if t["dangerous"] else ""
        tag = "[dim](built-in)[/]" if t["builtin"] else "[cyan](custom)[/]"
        console.print(f"  [bold]{t['name']}[/]{badge} {tag}")
        console.print(f"    [dim]{t['description']}[/]")

    console.print(
        f"\n[dim]Custom tools: drop Python files in ~/.simplicity/tools/[/]"
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="simplicity",
        description="🌸 Simplicity — AI Chat CLI powered by Pollinations.ai",
        epilog="Get your API key at https://enter.pollinations.ai",
    )
    parser.add_argument(
        "--version", action="version", version="simplicity 1.0.0"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # chat
    chat_parser = subparsers.add_parser("chat", help="Start interactive chat")
    chat_parser.add_argument(
        "-m", "--model", help="Override the default model"
    )
    chat_parser.set_defaults(func=cmd_chat)

    # ask
    ask_parser = subparsers.add_parser("ask", help="One-shot question")
    ask_parser.add_argument("prompt", help="The question or prompt")
    ask_parser.add_argument(
        "-m", "--model", help="Override the default model"
    )
    ask_parser.add_argument(
        "--no-stream", action="store_true", help="Disable streaming output"
    )
    ask_parser.set_defaults(func=cmd_ask)

    # setup
    setup_parser = subparsers.add_parser("setup", help="Configure API key and settings")
    setup_parser.set_defaults(func=cmd_setup)

    # models
    models_parser = subparsers.add_parser("models", help="List available models")
    models_parser.set_defaults(func=cmd_models)

    # balance
    balance_parser = subparsers.add_parser("balance", help="Check pollen balance")
    balance_parser.set_defaults(func=cmd_balance)

    # discord
    discord_parser = subparsers.add_parser("discord", help="Start Discord bot connector")
    discord_parser.add_argument(
        "-t", "--token", help="Discord bot token (or set DISCORD_TOKEN env var)"
    )
    discord_parser.set_defaults(func=cmd_discord)

    # web
    web_parser = subparsers.add_parser("web", help="Start web UI chat interface")
    web_parser.add_argument(
        "-p", "--port", type=int, default=8080, help="Port to listen on (default: 8080)"
    )
    web_parser.set_defaults(func=cmd_web)

    # usage
    usage_parser = subparsers.add_parser("usage", help="View pollen balance and usage history")
    usage_parser.add_argument(
        "-d", "--days", type=int, default=30, help="Number of days of history (default: 30)"
    )
    usage_parser.set_defaults(func=cmd_usage)

    # update
    update_parser = subparsers.add_parser("update", help="Update to the latest version")
    update_parser.set_defaults(func=cmd_update)

    # disconnect
    disconnect_parser = subparsers.add_parser("disconnect", help="Remove saved API key")
    disconnect_parser.set_defaults(func=cmd_disconnect)

    # auth
    auth_parser = subparsers.add_parser("auth", help="Sign in with Pollinations (web redirect BYOP)")
    auth_parser.add_argument(
        "--device", action="store_true", help="Use device code flow instead of web redirect"
    )
    auth_parser.set_defaults(func=cmd_auth)

    # tools
    tools_parser = subparsers.add_parser("tools", help="List available tools")
    tools_parser.set_defaults(func=cmd_tools)

    return parser


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        # Default to chat if no command given
        args.func = cmd_chat
        # Inject model arg if not present
        if not hasattr(args, "model"):
            args.model = None

    args.func(args)


if __name__ == "__main__":
    main()
