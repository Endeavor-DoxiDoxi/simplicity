"""Discord connector for Simplicity — run your agent as a Discord bot.

Start with: simplicity discord
Requires:  discord.py (pip install simplicity[discord])
           A Discord bot token (from https://discord.com/developers)

The bot listens for @mentions and replies using the Simplicity chat engine.
Tool calls that require approval are presented as reactions — the user
reacts with ✅ to approve or ❌ to deny.
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional


# ── Discord.py availability check ────────────────────────────────

DISCORD_AVAILABLE = False
try:
    import discord
    from discord.ext import commands
    DISCORD_AVAILABLE = True
except ImportError:
    pass


# ── Bot class ─────────────────────────────────────────────────────

if DISCORD_AVAILABLE:

    class SimplicityBot(commands.Bot):
        """Discord bot powered by the Simplicity chat engine."""

        def __init__(self, config, provider, tools, command_prefix="!"):
            intents = discord.Intents.default()
            intents.message_content = True
            intents.reactions = True
            super().__init__(command_prefix=command_prefix, intents=intents)
            self._config = config
            self._provider = provider
            self._tools = tools
            # Per-channel conversation state
            self._conversations: dict[int, list[dict]] = {}
            # Pending approval requests: message_id -> (tool_name, args, channel_id)
            self._pending_approvals: dict[int, tuple] = {}

        async def setup_hook(self):
            """Bot startup."""
            print(f"  Logged in as: {self.user}")
            print(f"  Model: {self._provider.model}")
            print(f"  Tools: {len(self._tools.get_definitions())}")
            print()

        def _get_conversation(self, channel_id: int) -> list[dict]:
            """Get or create conversation history for a channel."""
            if channel_id not in self._conversations:
                self._conversations[channel_id] = [
                    {"role": "system", "content": self._config.system_prompt},
                ]
            return self._conversations[channel_id]

        def _clean_discord_content(self, text: str) -> str:
            """Strip Discord-specific formatting and mentions."""
            # Remove <@...> mentions
            text = re.sub(r'<@!?\d+>', '', text)
            # Remove custom emoji
            text = re.sub(r'<a?:\w+:\d+>', '', text)
            return text.strip()

        async def on_message(self, message: discord.Message):
            """Handle incoming messages."""
            # Ignore own messages
            if message.author == self.user:
                return
            # Ignore bots
            if message.author.bot:
                return

            # Check if bot is @mentioned or it's a DM
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mentioned = self.user in message.mentions

            if not (is_dm or is_mentioned):
                return

            # Clean the message content
            content = self._clean_discord_content(message.content)
            if not content:
                content = "hello"  # Just a mention with no text

            # Get conversation
            conv = self._get_conversation(message.channel.id)

            # Show typing indicator
            async with message.channel.typing():
                try:
                    await self._process_chat(message.channel, conv, content)
                except Exception as e:
                    await message.channel.send(f"❌ Error: {e}")

        async def _process_chat(self, channel, conv: list[dict], user_msg: str):
            """Process a chat message through the Simplicity engine."""
            conv.append({"role": "user", "content": user_msg})

            available_tools = self._tools.get_definitions() or None
            max_rounds = 5

            for round_num in range(max_rounds):
                # Collect streaming response
                full_content = ""
                tool_calls = []
                last_usage = None

                try:
                    for chunk in self._provider.chat_stream(
                        messages=conv,
                        tools=available_tools,
                        temperature=self._config.temperature,
                        max_tokens=self._config.max_tokens,
                    ):
                        if chunk["type"] == "content":
                            full_content += chunk["content"]
                        elif chunk["type"] == "tool_call":
                            tool_calls.append({
                                "id": chunk.get("id", f"call_{len(tool_calls)}"),
                                "type": "function",
                                "function": {
                                    "name": chunk["name"],
                                    "arguments": chunk.get("arguments", "{}"),
                                },
                            })
                        elif chunk["type"] == "finish":
                            last_usage = chunk.get("usage")
                except Exception as e:
                    await self._send_long(channel, f"❌ Provider error: {e}")
                    return

                # Handle tool calls
                if tool_calls:
                    # Add assistant tool call message
                    conv.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": tool_calls,
                    })

                    for tc in tool_calls:
                        fn = tc["function"]
                        name = fn["name"]
                        try:
                            args = json.loads(fn["arguments"])
                        except json.JSONDecodeError:
                            args = {}

                        # Approval check
                        if self._tools.requires_approval(name):
                            approved = await self._request_approval(
                                channel, name, args
                            )
                            if not approved:
                                result = "User denied this tool call."
                                conv.append({
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "content": result,
                                })
                                continue

                        # Execute tool
                        result = self._tools.execute(name, args)
                        conv.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })

                        # Reload tools if a new one was created
                        if name == "create_tool":
                            self._tools._loaded = False
                            self._tools.load_custom_tools()
                            available_tools = self._tools.get_definitions() or None

                    # Continue loop to send tool results back
                    continue

                # No tool calls — send the text response
                if full_content.strip():
                    await self._send_long(channel, full_content)
                else:
                    await channel.send("🤔 (no response)")

                conv.append({"role": "assistant", "content": full_content})
                return

            await channel.send("⚠️  Max tool calling rounds reached.")

        async def _request_approval(
            self, channel, tool_name: str, args: dict
        ) -> bool:
            """Ask the user to approve a tool call via reactions."""
            args_preview = "\n".join(
                f"  **{k}:** {str(v)[:200]}" for k, v in args.items()
            )
            msg = await channel.send(
                f"⚠️  **Approve tool call?**\n"
                f"**Tool:** `{tool_name}`\n{args_preview}\n\n"
                f"React ✅ to approve / ❌ to deny (15s timeout)"
            )
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")

            self._pending_approvals[msg.id] = (tool_name, args, channel.id)

            # Wait for reaction
            def check(reaction, user):
                return (
                    reaction.message.id == msg.id
                    and not user.bot
                    and str(reaction.emoji) in ("✅", "❌")
                )

            try:
                reaction, user = await self.wait_for(
                    "reaction_add", timeout=15.0, check=check
                )
                approved = str(reaction.emoji) == "✅"
                await msg.edit(content=f"{'✅ Approved' if approved else '❌ Denied'}: `{tool_name}`")
                await msg.clear_reactions()
                return approved
            except asyncio.TimeoutError:
                await msg.edit(content=f"⏰ Timed out — denied: `{tool_name}`")
                await msg.clear_reactions()
                return False
            finally:
                self._pending_approvals.pop(msg.id, None)

        async def _send_long(self, channel, content: str):
            """Send a message, splitting if too long for Discord."""
            # Discord's 2000 char limit
            if len(content) <= 1990:
                # Strip markdown that Discord can't render nicely
                await channel.send(self._format_for_discord(content))
            else:
                # Split into chunks
                chunks = []
                while len(content) > 1990:
                    # Find a good split point
                    split_at = content.rfind("\n", 0, 1990)
                    if split_at < 1000:
                        split_at = content.rfind(" ", 0, 1990)
                    if split_at < 1000:
                        split_at = 1990
                    chunks.append(content[:split_at])
                    content = content[split_at:].lstrip()
                chunks.append(content)

                for chunk in chunks:
                    await channel.send(self._format_for_discord(chunk))

        def _format_for_discord(self, text: str) -> str:
            """Format text for Discord display."""
            # Convert ```language\n blocks to Discord code blocks
            text = re.sub(r'```(\w*)\n', r'```\1\n', text)
            return text


# ── Entry point ───────────────────────────────────────────────────

def run_discord(token: str):
    """Start the Simplicity Discord bot."""
    if not DISCORD_AVAILABLE:
        print("❌ discord.py is not installed.")
        print()
        print("Install it with:")
        print("  pip install discord.py")
        print()
        print("Or re-run the Simplicity installer and choose Discord support.")
        sys.exit(1)

    from simplicity.config import Config
    from simplicity.providers import PollinationsProvider
    from simplicity.tools import ToolRegistry

    config = Config().load()

    if not config.is_configured():
        print("⚠️  No API key configured. Run 'simp auth' first.")
        print("   The bot will start but won't be able to chat.")
        print()

    provider = PollinationsProvider(config.api_key, config.model)
    tools = ToolRegistry(Path.home() / ".simplicity" / "tools")

    print()
    print("  🌸  Simplicity Discord Bot")
    print(f"  →  Model: {config.model}")
    print(f"  →  Tools: {len(tools.get_definitions())}")
    print()

    bot = SimplicityBot(config, provider, tools)

    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ Invalid Discord bot token.")
        print("   Get one at: https://discord.com/developers/applications")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n  Shutting down...")
