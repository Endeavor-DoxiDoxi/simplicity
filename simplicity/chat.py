"""Interactive chat loop and conversation management for Simplicity."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from simplicity.client import SimplicityClient, SimplicityAPIError
from simplicity.providers import ProviderError
from simplicity.config import Config, HISTORY_DIR
from simplicity.tools import ToolRegistry, BUILTIN_EXECUTORS
from simplicity.display import (
    console,
    thinking,
    tool_call_indicator,
    tool_result,
    approval_prompt,
    render_assistant_message,
    stream_token,
    stream_done,
    model_info,
    error_message,
    success_message,
    warn_message,
    help_text,
    save_confirmation,
    debug,
)


class _StreamingThinkFilter:
    """Filters <think> content across streaming chunks.

    Models may split tags across chunks, so a simple regex per-chunk fails.
    This state machine buffers potential partial tags at chunk boundaries.
    """

    _OPEN_RE = __import__('re').compile(r'<\s*think(?:ing)?\s*>', __import__('re').IGNORECASE)
    _CLOSE_RE = __import__('re').compile(r'<\s*/\s*think(?:ing)?\s*>', __import__('re').IGNORECASE)

    def __init__(self):
        self.in_think = False
        self.pending = ""

    def feed(self, text: str) -> str:
        combined = self.pending + text
        self.pending = ""
        result = []
        i = 0

        while i < len(combined):
            if self.in_think:
                match = self._CLOSE_RE.search(combined, i)
                if match:
                    self.in_think = False
                    i = match.end()
                else:
                    # Check for partial closing tag at end
                    remaining = combined[i:]
                    if self._could_be_closing_tag(remaining):
                        self.pending = remaining
                    break
            else:
                match = self._OPEN_RE.search(combined, i)
                if match:
                    result.append(combined[i:match.start()])
                    self.in_think = True
                    i = match.end()
                else:
                    result.append(combined[i:])
                    # Check for partial opening tag at end
                    remaining = combined[i:]
                    if self._could_be_opening_tag(remaining):
                        self.pending = remaining
                        result.pop()
                    break

        return "".join(result)

    _TAG_STARTS = ['<think>', '<thinking>', '< think>', '< thinking>']
    _CLOSE_TAG_STARTS = ['</think>', '</thinking>', '</ think>', '</ thinking>']

    def _could_be_opening_tag(self, text: str) -> bool:
        """Check if text starts with a prefix of any opening think tag."""
        if not text or text[0] != '<':
            return False
        for tag in self._TAG_STARTS:
            if tag.startswith(text):
                return True
        return False

    def _could_be_closing_tag(self, text: str) -> bool:
        """Check if text starts with a prefix of any closing think tag."""
        if not text or not text.startswith('</'):
            return False
        for tag in self._CLOSE_TAG_STARTS:
            if tag.startswith(text):
                return True
        return False

    def finalize(self) -> str:
        if not self.in_think and self.pending:
            return self.pending
        return ""


class ChatSession:
    """Manages an interactive chat conversation."""

    def __init__(self, config: Config):
        self.config = config
        self.client = SimplicityClient(
            api_key=config.api_key,
            model=config.model,
        )
        self.tools = ToolRegistry(Path.home() / ".simplicity" / "tools")

        # Conversation state
        self.messages: list[dict] = []
        self._init_system_prompt()

    def _init_system_prompt(self):
        """Set up the system prompt."""
        system_prompt = self.config.system_prompt
        # Add tool awareness
        tool_names = self.tools.get_tool_names()
        if tool_names:
            system_prompt += (
                f"\n\nYou have access to these tools: {', '.join(tool_names)}. "
                "Use them when helpful to complete tasks."
            )
        self.messages.append({"role": "system", "content": system_prompt})

    def run(self):
        """Start the interactive chat loop."""
        from simplicity.display import welcome

        welcome()
        model_info(self.config.model)

        # Check if API key is set
        if not self.config.is_configured():
            warn_message("No API key configured. Run 'simplicity setup' first.")
            return

        # Main chat loop
        while True:
            try:
                user_input = self._get_input()
                if user_input is None:
                    break  # EOF
                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    if self._handle_command(user_input):
                        continue
                    else:
                        break  # /quit

                # Normal chat
                self._handle_chat(user_input)

            except KeyboardInterrupt:
                console.print("\n[dim](Interrupted)[/]")
                continue
            except EOFError:
                break

        console.print("\n[dim]Goodbye! ✌️[/]")

    def _get_input(self) -> Optional[str]:
        """Get user input with a nice prompt."""
        return console.input("[bold cyan]You ›[/] ")

    def _handle_command(self, cmd: str) -> bool:
        """Handle a slash command. Returns False if should exit."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if command in ("/quit", "/exit", "/q"):
            return False
        elif command == "/disconnect":
            self.config.set("api_key", "")
            success_message("API key removed. Run simp auth to reconnect.")
        elif command in ("/help", "/h", "/?"):
            help_text()
        elif command == "/clear":
            self.messages = []
            self._init_system_prompt()
            success_message("Conversation cleared")
        elif command == "/model":
            if arg:
                self.client.model = arg
                self.config.set("model", arg)
                success_message(f"Model set to: {arg}")
            else:
                console.print(f"[dim]Current model:[/] [green]{self.client.model}[/]")
                console.print("[dim]Use /model <name> to change[/]")
        elif command == "/models":
            self._list_models()
        elif command == "/balance":
            self._check_balance()
        elif command == "/usage":
            self._check_usage(arg)
        elif command == "/tools":
            self._list_tools()
        elif command == "/save":
            self._save_conversation(arg)
        elif command == "/system":
            if arg:
                self.config.set("system_prompt", arg)
                # Replace system message
                self.messages = [m for m in self.messages if m["role"] != "system"]
                self.messages.insert(0, {"role": "system", "content": arg})
                success_message("System prompt updated")
            else:
                sys_msg = next(
                    (m["content"] for m in self.messages if m["role"] == "system"), ""
                )
                console.print(f"[dim]System prompt:[/]\n{sys_msg[:200]}...")
        else:
            warn_message(f"Unknown command: {command}")

        return True

    def _handle_chat(self, user_input: str):
        """Process a normal chat message with tool calling loop."""
        self.messages.append({"role": "user", "content": user_input})

        # Tool calling loop
        max_tool_rounds = 5
        for _ in range(max_tool_rounds):
            try:
                response = self._stream_and_collect()
            except ProviderError as e:
                error_message(str(e))
                return
            except SimplicityAPIError as e:
                if e.is_auth_error:
                    error_message(
                        f"Authentication failed (HTTP {e.status}).\n"
                        f"  Your API key may lack permissions, have expired, or the model\n"
                        f"  may require paid balance. Try:\n"
                        f"  - /model openai (use a free model)\n"
                        f"  - /balance (check your pollen)\n"
                        f"  - simp auth (re-authenticate)"
                    )
                elif e.is_balance_error:
                    error_message(f"Insufficient pollen balance. Top up at enter.pollinations.ai")
                else:
                    error_message(str(e))
                return

            if response is None:
                return  # Interrupted

            # Check for tool calls
            if response.get("tool_calls"):
                self._execute_tool_calls(response["tool_calls"])
                # Continue loop to send tool results back
                continue
            else:
                # Final text response
                content = response.get("content", "")
                if content:
                    self.messages.append({"role": "assistant", "content": content})
                return

        warn_message("Max tool calling rounds reached")

    def _stream_and_collect(self) -> Optional[dict]:
        """Stream the response, collecting content and tool calls."""
        available_tools = self.tools.get_definitions() or None

        full_content = ""
        tool_calls = []
        think_filter = _StreamingThinkFilter()
        first_content = True

        try:
            for chunk in self.client.chat_stream(
                messages=self.messages,
                tools=available_tools,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            ):
                if chunk["type"] == "content":
                    if first_content:
                        console.print("[dim]🤔[/]", end=" ", highlight=False)
                        first_content = False
                    raw = chunk["content"]
                    full_content += raw
                    # Filter think tags for display (handles chunk boundaries)
                    display_text = think_filter.feed(raw)
                    if display_text:
                        stream_token(display_text)
                elif chunk["type"] == "tool_call":
                    if not first_content:
                        console.print()  # end the thinking line
                        first_content = True
                    tool_calls.append(
                        {
                            "id": chunk.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": chunk["name"],
                                "arguments": chunk["arguments"],
                            },
                        }
                    )
                elif chunk["type"] == "finish":
                    usage = chunk.get("usage")
                    if usage:
                        tk = usage.get("total_tokens", "?")
                        debug(f"Tokens: {tk}")

            stream_done()

            # Final think-tag strip on complete content for storage
            from simplicity.providers import _strip_think_tags
            full_content = _strip_think_tags(full_content)

            if not full_content and not tool_calls:
                warn_message("Received empty response — the model may be unavailable.")
                return {"content": "(no response)", "tool_calls": []}
            return {"content": full_content, "tool_calls": tool_calls}

        except KeyboardInterrupt:
            console.print("\n[dim](Stopped)[/]")
            return None

    def _execute_tool_calls(self, tool_calls: list[dict]):
        """Execute tool calls, with user approval for dangerous ones."""
        # Add assistant message with tool calls
        assistant_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        }
        self.messages.append(assistant_msg)

        for tc in tool_calls:
            fn = tc["function"]
            name = fn["name"]
            try:
                args = json.loads(fn["arguments"])
            except json.JSONDecodeError:
                args = {}

            tool_call_indicator(name, args)

            # Check if approval needed
            if self.tools.requires_approval(name):
                if not approval_prompt(name, args):
                    result = "User denied this tool call."
                    tool_result(result)
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        }
                    )
                    continue

            # Execute tool
            result = self.tools.execute(name, args)
            tool_result(result)

            # Reload tools if a new one was created
            if name == "create_tool":
                self.tools._loaded = False  # force reload
                self.tools.load_custom_tools()
                console.print("[dim]🔄 Tools reloaded — new tool is now available[/]")

            # Add tool result to conversation
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                }
            )

    def _list_models(self):
        """List available models from within chat."""
        try:
            from simplicity.client import SimplicityClient
            from simplicity.display import show_models_detail, show_models
            console.print("[dim]Fetching models...[/]")
            models = SimplicityClient.fetch_models(api_key=self.config.api_key)
            if self.config.is_configured():
                show_models_detail(models)
            else:
                show_models(models)
        except Exception as e:
            error_message(f"Could not fetch models: {e}")

    def _check_balance(self):
        """Check pollen balance."""
        try:
            from simplicity.client import SimplicityClient
            data = SimplicityClient.fetch_balance(self.config.api_key)
            from simplicity.display import show_balance_detail
            show_balance_detail(data)
        except Exception as e:
            error_message(f"Could not check balance: {e}")

    def _check_usage(self, days_arg: str):
        """Check pollen balance and usage."""
        try:
            days = int(days_arg) if days_arg else 30
        except ValueError:
            days = 30
        
        from simplicity.client import SimplicityClient, SimplicityAPIError
        from simplicity.display import show_balance_detail, show_usage
        
        try:
            balance = SimplicityClient.fetch_balance(self.config.api_key)
            show_balance_detail(balance)
        except Exception:
            console.print("[dim]Balance unavailable[/]")
        
        try:
            usage = SimplicityClient.fetch_usage(self.config.api_key, days=days)
            show_usage(usage)
        except SimplicityAPIError as e:
            if e.status == 403:
                console.print("[dim]Usage history needs account:usage scope[/]")
            else:
                error_message(f"Usage: {e}")
        except Exception as e:
            error_message(f"Usage: {e}")

    def _list_tools(self):
        """List available tools."""
        tools = self.tools.list_tools()
        if not tools:
            console.print("[dim]No tools available[/]")
            return
        for t in tools:
            badge = "[yellow]⚠️ [/]" if t["dangerous"] else ""
            tag = "[dim](built-in)[/]" if t["builtin"] else "[cyan](custom)[/]"
            console.print(f"  {badge}[bold]{t['name']}[/] {tag}")
            console.print(f"    [dim]{t['description']}[/]")

    def _save_conversation(self, filename: str = ""):
        """Save the conversation to a file."""
        if not filename:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"chat-{ts}.json"

        path = HISTORY_DIR / filename
        data = {
            "timestamp": datetime.now().isoformat(),
            "model": self.client.model,
            "messages": self.messages,
        }
        path.write_text(json.dumps(data, indent=2))
        save_confirmation(str(path), len(self.messages))


def one_shot(config: Config, prompt: str, no_stream: bool = False):
    """One-shot ask mode: send a single prompt, get a response, exit."""
    client = SimplicityClient(api_key=config.api_key, model=config.model)
    messages = [
        {"role": "system", "content": config.system_prompt},
        {"role": "user", "content": prompt},
    ]

    if no_stream:
        # Non-streaming mode
        try:
            with thinking():
                response = client.chat(
                    messages=messages,
                    tools=None,
                    stream=False,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                )
            choice = response.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            render_assistant_message(content)
        except (SimplicityAPIError, ProviderError) as e:
            error_message(str(e))
    else:
        # Streaming mode
        full_content = ""
        try:
            with thinking():
                for chunk in client.chat_stream(
                    messages=messages,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                ):
                    if chunk["type"] == "content":
                        stream_token(chunk["content"])
                        full_content += chunk["content"]
            stream_done()
        except KeyboardInterrupt:
            console.print("\n[dim](Stopped)[/]")
        except (SimplicityAPIError, ProviderError) as e:
            error_message(str(e))
