"""Pollinations.ai API client for Simplicity.

Uses OpenAI-compatible chat completions endpoint.
"""

import json
import urllib.request
import urllib.error
from typing import Optional, Generator


BASE_URL = "https://gen.pollinations.ai/v1"
API_BASE = "https://gen.pollinations.ai"
MODELS_URL = "https://gen.pollinations.ai/models"
TEXT_MODELS_URL = "https://gen.pollinations.ai/text/models"


class SimplicityClient:
    """HTTP client for Pollinations.ai API."""

    def __init__(self, api_key: str, model: str = "nova-fast"):
        self.api_key = api_key
        self.model = model
        self.base_url = BASE_URL
        # Use the provider system internally
        from simplicity.providers import PollinationsProvider
        self._provider = PollinationsProvider(api_key, model)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _request(self, endpoint: str, data: dict) -> dict:
        """Make a non-streaming JSON request."""
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=self._headers(), method="POST")

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                error_data = json.loads(error_body)
                msg = error_data.get("error", {}).get("message", error_body)
            except json.JSONDecodeError:
                msg = error_body[:500]
            raise SimplicityAPIError(e.code, msg)

    def _stream_request(self, endpoint: str, data: dict) -> Generator[dict, None, None]:
        """Make a streaming SSE request. Yields parsed JSON chunks."""
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=self._headers(), method="POST")

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                buffer = ""
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    text = chunk.decode("utf-8", errors="replace")
                    buffer += text

                    # Process complete SSE lines
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                return
                            try:
                                yield json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                        elif line == "":
                            # SSE empty line = event boundary
                            continue
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                error_data = json.loads(error_body)
                msg = error_data.get("error", {}).get("message", error_body)
            except json.JSONDecodeError:
                msg = error_body[:500]
            raise SimplicityAPIError(e.code, msg)

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict:
        """Send a chat completion request. Returns the full response."""
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"

        return self._request("/chat/completions", data)

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
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"

        tool_calls_in_progress: dict[int, dict] = {}

        for chunk in self._stream_request("/chat/completions", data):
            choices = chunk.get("choices", [])
            usage = chunk.get("usage")

            for choice in choices:
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")

                # Content delta
                if "content" in delta and delta["content"]:
                    yield {"type": "content", "content": delta["content"]}

                # Tool call delta
                if "tool_calls" in delta:
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_in_progress:
                            tool_calls_in_progress[idx] = {
                                "id": tc.get("id", ""),
                                "name": "",
                                "arguments": "",
                            }
                        entry = tool_calls_in_progress[idx]
                        if "id" in tc and tc["id"]:
                            entry["id"] = tc["id"]
                        if "function" in tc:
                            fn = tc["function"]
                            if "name" in fn and fn["name"]:
                                entry["name"] = fn["name"]
                            if "arguments" in fn:
                                entry["arguments"] += fn["arguments"]

                # Finish reason
                if finish_reason:
                    # Emit any completed tool calls
                    for tc in tool_calls_in_progress.values():
                        if tc["name"]:
                            yield {"type": "tool_call", **tc}
                    tool_calls_in_progress.clear()

                    yield {
                        "type": "finish",
                        "reason": finish_reason,
                        "usage": usage,
                    }

    @staticmethod
    def fetch_models(api_key: str = "") -> list[dict]:
        """Fetch available models from Pollinations."""
        from simplicity.providers import PollinationsProvider
        return PollinationsProvider(api_key).fetch_models()

    @staticmethod
    def fetch_balance(api_key: str) -> dict:
        """Fetch pollen balance."""
        from simplicity.providers import PollinationsProvider
        try:
            return PollinationsProvider(api_key).fetch_balance()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
                msg = data.get("error", {}).get("message", body)
            except json.JSONDecodeError:
                msg = body[:500]
            raise SimplicityAPIError(e.code, msg)

    @staticmethod
    def fetch_usage(api_key: str, days: int = 30) -> dict:
        """Fetch recent usage history."""
        from simplicity.providers import PollinationsProvider
        try:
            return PollinationsProvider(api_key).fetch_usage(days)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
                msg = data.get("error", {}).get("message", body)
            except json.JSONDecodeError:
                msg = body[:500]
            raise SimplicityAPIError(e.code, msg)


class SimplicityAPIError(Exception):
    """Raised when the Pollinations API returns an error."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        # Keep it brief for terminal display
        short = message[:200]
        super().__init__(f"API Error {status}: {short}")

    @property
    def is_auth_error(self) -> bool:
        return self.status in (401, 403)

    @property
    def is_balance_error(self) -> bool:
        return self.status == 402

    @property
    def is_rate_limit(self) -> bool:
        return self.status == 429
