"""Provider abstraction layer for Simplicity.

Supports multiple AI backends while keeping Pollinations as the default.
OpenAI-compatible APIs work with zero config — just change the base URL.
"""

import json
import urllib.request
import urllib.error
from typing import Optional, Generator


class BaseProvider:
    """Abstract base for AI providers."""

    name: str = "base"
    base_url: str = ""

    def __init__(self, api_key: str, model: str = ""):
        self.api_key = api_key
        self.model = model

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Generator[dict, None, None]:
        """Stream a chat completion. Yields delta chunks.

        Each yielded dict has:
          - type: "content" | "tool_call" | "finish"
          - For "content": {content: str}
          - For "tool_call": {id, name, arguments: str}
          - For "finish": {reason, usage}
        """
        raise NotImplementedError

    def fetch_models(self) -> list[dict]:
        """Fetch available models from this provider."""
        return []

    @staticmethod
    def from_config(provider_name: str, api_key: str, model: str) -> "BaseProvider":
        """Create a provider from a name string."""
        providers = {
            "pollinations": PollinationsProvider,
            "openai": OpenAIProvider,
            "ollama": OllamaProvider,
        }
        if provider_name in providers:
            return providers[provider_name](api_key, model)
        # Default to Pollinations
        return PollinationsProvider(api_key, model)


# ── Pollinations Provider (default) ──────────────────────────────

POLLINATIONS_BASE = "https://gen.pollinations.ai/v1"
POLLINATIONS_API = "https://gen.pollinations.ai"
POLLINATIONS_MODELS = "https://gen.pollinations.ai/models"
POLLINATIONS_TEXT_MODELS = "https://gen.pollinations.ai/text/models"


class PollinationsProvider(BaseProvider):
    """Pollinations.ai provider — default, no extra config needed."""

    name = "pollinations"
    base_url = POLLINATIONS_BASE

    def chat_stream(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        data = {
            "model": self.model or "nova-fast",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"

        yield from _openai_stream(self.base_url, self._headers(), data)

    def fetch_models(self) -> list[dict]:
        """Fetch models, authenticated if API key is set."""
        headers = {"User-Agent": "Simplicity/1.0", "Accept": "application/json"}
        if self.api_key:
            try:
                req = urllib.request.Request(
                    POLLINATIONS_TEXT_MODELS,
                    headers={**headers, "Authorization": f"Bearer {self.api_key}"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception:
                pass
        try:
            req = urllib.request.Request(POLLINATIONS_MODELS, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return []

    def fetch_balance(self) -> dict:
        req = urllib.request.Request(
            f"{POLLINATIONS_API}/account/balance",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch_usage(self, days: int = 30) -> dict:
        req = urllib.request.Request(
            f"{POLLINATIONS_API}/account/usage?days={days}",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))


# ── OpenAI Provider ───────────────────────────────────────────────

class OpenAIProvider(BaseProvider):
    """OpenAI API provider."""

    name = "openai"
    base_url = "https://api.openai.com/v1"

    def chat_stream(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        data = {
            "model": self.model or "gpt-4o-mini",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"
        yield from _openai_stream(self.base_url, self._headers(), data)


# ── Ollama Provider (local) ───────────────────────────────────────

class OllamaProvider(BaseProvider):
    """Ollama local models provider."""

    name = "ollama"
    base_url = "http://localhost:11434/v1"

    def __init__(self, api_key: str = "", model: str = ""):
        super().__init__(api_key or "ollama", model or "llama3.2")
        # Ollama doesn't need auth, but the header is harmless

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def chat_stream(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        data = {
            "model": self.model or "llama3.2",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        yield from _openai_stream(self.base_url, self._headers(), data)


# ── Shared SSE streaming parser ──────────────────────────────────

def _openai_stream(base_url: str, headers: dict, data: dict) -> Generator[dict, None, None]:
    """Parse OpenAI-compatible SSE stream. Used by all providers."""
    url = f"{base_url}/chat/completions"
    body = json.dumps(data).encode("utf-8")
    # Add User-Agent to avoid Cloudflare 1010 blocks
    if "User-Agent" not in headers:
        headers["User-Agent"] = "Simplicity/1.0"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            buffer = ""
            tool_calls_in_progress: dict[int, dict] = {}
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                buffer += text
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            return
                        try:
                            chunk_data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk_data.get("choices", [])
                        usage = chunk_data.get("usage")
                        for choice in choices:
                            delta = choice.get("delta", {})
                            finish_reason = choice.get("finish_reason")
                            if "content" in delta and delta["content"]:
                                yield {"type": "content", "content": delta["content"]}
                            if "tool_calls" in delta:
                                for tc in delta["tool_calls"]:
                                    idx = tc.get("index", 0)
                                    if idx not in tool_calls_in_progress:
                                        tool_calls_in_progress[idx] = {
                                            "id": tc.get("id", ""),
                                            "name": "",
                                            "arguments": "",
                                        }
                                    e = tool_calls_in_progress[idx]
                                    if "id" in tc and tc["id"]:
                                        e["id"] = tc["id"]
                                    if "function" in tc:
                                        fn = tc["function"]
                                        if "name" in fn and fn["name"]:
                                            e["name"] = fn["name"]
                                        if "arguments" in fn:
                                            e["arguments"] += fn["arguments"]
                            if finish_reason:
                                for tc in tool_calls_in_progress.values():
                                    if tc["name"]:
                                        yield {"type": "tool_call", **tc}
                                tool_calls_in_progress.clear()
                                yield {
                                    "type": "finish",
                                    "reason": finish_reason,
                                    "usage": usage,
                                }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            msg = error_data.get("error", {}).get("message", error_body)
        except json.JSONDecodeError:
            msg = error_body[:500]
        raise ProviderError(e.code, msg)


class ProviderError(Exception):
    """Raised when an AI provider returns an error."""
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"Provider Error {status}: {message[:200]}")
