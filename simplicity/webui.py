"""Web UI for Simplicity — browser-based chat interface.

Start with: simplicity web
or:        simplicity web --port 8080
"""

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

from simplicity.config import Config
from simplicity.providers import BaseProvider, PollinationsProvider, ProviderError
from simplicity.tools import ToolRegistry


# ── The HTML frontend ────────────────────────────────────────────

WEBUI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Simplicity Web UI</title>
<style>
:root {
  --bg: #0d1117; --surface: #161b22; --border: #30363d;
  --text: #c9d1d9; --muted: #8b949e; --accent: #f781c0;
  --green: #3fb950; --red: #f85149; --yellow: #d2991d;
  --code-bg: #1c2128;
}
* { box-sizing:border-box; margin:0; padding:0; }
body {
  background:var(--bg); color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  height:100vh; display:flex; flex-direction:column;
}
.header {
  background:var(--surface); border-bottom:1px solid var(--border);
  padding:0.75rem 1.25rem; display:flex; align-items:center; gap:0.75rem;
}
.header .logo { font-size:1.5rem; }
.header h1 { font-size:1.1rem; font-weight:600; color:var(--accent); }
.header .sub { color:var(--muted); font-size:0.8rem; margin-left:auto; }
.chat {
  flex:1; overflow-y:auto; padding:1rem;
  display:flex; flex-direction:column; gap:0.75rem;
}
.msg { max-width:85%; padding:0.75rem 1rem; border-radius:10px; line-height:1.5; }
.msg.user { align-self:flex-end; background:rgba(247,129,192,0.15); border:1px solid rgba(247,129,192,0.3); }
.msg.assistant { align-self:flex-start; background:var(--surface); border:1px solid var(--border); }
.msg.system { align-self:center; color:var(--muted); font-size:0.8rem; font-style:italic; }
.msg pre { background:var(--code-bg); border-radius:6px; padding:0.75rem; overflow-x:auto; margin:0.5rem 0; }
.msg code { font-family:'JetBrains Mono','Fira Code',monospace; font-size:0.85rem; }
.msg p { margin:0.25rem 0; }
.tool-call {
  align-self:flex-start; background:rgba(210,153,29,0.1); border:1px solid rgba(210,153,29,0.3);
  border-radius:8px; padding:0.5rem 0.75rem; font-size:0.85rem;
}
.tool-call .name { color:var(--yellow); font-weight:600; }
.tool-call .args { color:var(--muted); }
.tool-result { color:var(--muted); font-size:0.8rem; margin-left:1rem; }
.input-area {
  background:var(--surface); border-top:1px solid var(--border);
  padding:0.75rem 1rem; display:flex; gap:0.5rem;
}
.input-area input {
  flex:1; background:var(--bg); border:1px solid var(--border);
  border-radius:8px; padding:0.6rem 0.75rem; color:var(--text);
  font-size:0.95rem; outline:none;
}
.input-area input:focus { border-color:var(--accent); }
.input-area button {
  background:var(--accent); color:var(--bg); border:none;
  border-radius:8px; padding:0.6rem 1rem; font-weight:600; cursor:pointer;
}
.input-area button:disabled { opacity:0.5; cursor:default; }
.spinner { display:inline-block; width:16px; height:16px; border:2px solid var(--border); border-top-color:var(--accent); border-radius:50%; animation:spin 0.6s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
.typing { display:flex; align-items:center; gap:0.5rem; color:var(--muted); font-size:0.85rem; padding:0.5rem; }
</style>
</head>
<body>
<div class="header">
  <span class="logo">🌸</span>
  <h1>Simplicity</h1>
  <span class="sub" id="model-badge">loading...</span>
</div>
<div class="chat" id="chat"></div>
<div class="input-area">
  <input id="input" placeholder="Type a message..." autofocus />
  <button id="send" onclick="send()">Send</button>
</div>

<script>
const chat = document.getElementById('chat');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const modelBadge = document.getElementById('model-badge');
let streaming = false;
let currentAssistantMsg = null;

input.addEventListener('keydown', e => { if (e.key==='Enter') send(); });

async function loadStatus() {
  try {
    let r = await fetch('/status');
    let s = await r.json();
    modelBadge.textContent = s.model + (s.authenticated ? ' · 🔑' : '');
  } catch(e) { modelBadge.textContent = 'offline'; }
}

function addMsg(role, html) {
  let d = document.createElement('div');
  d.className = 'msg ' + role;
  d.innerHTML = html;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
  return d;
}

function addSystem(text) {
  let d = document.createElement('div');
  d.className = 'msg system';
  d.textContent = text;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
}

function addToolCall(name, args) {
  let d = document.createElement('div');
  d.className = 'tool-call';
  d.innerHTML = '🔧 <span class="name">'+escapeHtml(name)+'</span> <span class="args">'+escapeHtml(JSON.stringify(args))+'</span>';
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
  return d;
}

function escapeHtml(text) {
  let d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

function simpleMarkdown(text) {
  // Code blocks
  text = text.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  // Inline code
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Newlines to <br>
  text = text.replace(/\n/g, '<br>');
  return text;
}

async function send() {
  let msg = input.value.trim();
  if (!msg || streaming) return;
  input.value = '';
  streaming = true;
  sendBtn.disabled = true;

  addMsg('user', escapeHtml(msg));

  // Typing indicator
  let typing = document.createElement('div');
  typing.className = 'typing';
  typing.innerHTML = '<div class="spinner"></div> Thinking...';
  chat.appendChild(typing);
  chat.scrollTop = chat.scrollHeight;

  try {
    let r = await fetch('/chat', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:msg})
    });

    if (!r.ok) {
      typing.remove();
      addSystem('Error: ' + r.status + ' — ' + (await r.text()));
      return;
    }

    let reader = r.body.getReader();
    let decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      let {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream:true});

      while (buffer.includes('\n')) {
        let idx = buffer.indexOf('\n');
        let line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx+1);

        if (line.startsWith('data: ')) {
          let data = line.slice(6);
          if (data === '[DONE]') break;
          try {
            let evt = JSON.parse(data);
            if (evt.type === 'content') {
              if (typing) { typing.remove(); typing = null; }
              if (!currentAssistantMsg) {
                currentAssistantMsg = addMsg('assistant', '');
              }
              let html = simpleMarkdown(evt.content);
              currentAssistantMsg.innerHTML += html;
              chat.scrollTop = chat.scrollHeight;
            } else if (evt.type === 'tool_call') {
              if (typing) { typing.remove(); typing = null; }
              currentAssistantMsg = null;
              addToolCall(evt.name, JSON.parse(evt.arguments||'{}'));
            } else if (evt.type === 'tool_result') {
              let d = document.createElement('div');
              d.className = 'tool-result';
              d.textContent = '→ ' + (evt.content||'').slice(0,300);
              chat.appendChild(d);
              chat.scrollTop = chat.scrollHeight;
            } else if (evt.type === 'finish') {
              currentAssistantMsg = null;
            }
          } catch(e) {}
        }
      }
    }
  } catch(e) {
    if (typing) typing.remove();
    addSystem('Error: ' + e.message);
  } finally {
    streaming = false;
    sendBtn.disabled = false;
    input.focus();
    currentAssistantMsg = null;
    if (typing) typing.remove();
  }
}

loadStatus();
</script>
</body>
</html>
"""


# ── HTTP request handler ─────────────────────────────────────────

class _WebUIHandler(BaseHTTPRequestHandler):
    """Serves the web UI and handles chat API requests."""

    # Class-level state (shared across requests)
    provider: BaseProvider = None
    config: Config = None
    tools: ToolRegistry = None
    messages: list[dict] = []

    def __init__(self, *args, **kwargs):
        # Set BEFORE super().__init__ — handle() is called during __init__
        self._provider = _WebUIHandler.provider
        self._config = _WebUIHandler.config
        self._tools = _WebUIHandler.tools
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_html()
        elif self.path == "/status":
            self._serve_status()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/chat":
            self._handle_chat()
        else:
            self.send_error(404)

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(WEBUI_HTML.encode("utf-8"))

    def _serve_status(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        data = json.dumps({
            "model": self._provider.model,
            "authenticated": bool(self._config.is_configured()),
        })
        self.wfile.write(data.encode())

    def _handle_chat(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length))
        user_message = body.get("message", "")

        if not user_message:
            self.send_error(400)
            return

        # Add user message to conversation
        _WebUIHandler.messages.append({"role": "user", "content": user_message})

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def emit(event_type: str, **kwargs):
            data = json.dumps({"type": event_type, **kwargs})
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()

        # Tool calling loop
        max_rounds = 5
        for _ in range(max_rounds):
            try:
                available_tools = self._tools.get_definitions() or None

                for chunk in self._provider.chat_stream(
                    messages=_WebUIHandler.messages,
                    tools=available_tools,
                    temperature=self._config.temperature,
                    max_tokens=self._config.max_tokens,
                ):
                    if chunk["type"] == "content":
                        emit("content", content=chunk["content"])
                    elif chunk["type"] == "tool_call":
                        emit("tool_call", name=chunk["name"], arguments=chunk.get("arguments", "{}"))
                    elif chunk["type"] == "finish":
                        emit("finish", reason=chunk["reason"])

            except ProviderError as e:
                emit("content", content=f"\n\n❌ Error: {e}")
                emit("finish", reason="error")
                return

            # Check for tool calls in the last assistant message
            # We need to collect tool calls from the stream
            # Since we're streaming, we collect them in a separate pass
            # For simplicity, re-request without streaming to check for tool calls
            break  # For now, single-turn — tool loop handled by next message

        emit("content", content="")
        emit("finish", reason="stop")

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def run_webui(port: int = 8080):
    """Start the Simplicity web UI server."""
    config = Config().load()

    if not config.is_configured():
        print("⚠️  No API key configured. Run 'simp auth' first.")
        print("   The web UI will start but won't be able to chat.")
        print()

    # Create provider
    provider = PollinationsProvider(config.api_key, config.model)
    tools = ToolRegistry(Path.home() / ".simplicity" / "tools")

    # Set up handler state
    _WebUIHandler.provider = provider
    _WebUIHandler.config = config
    _WebUIHandler.tools = tools
    _WebUIHandler.messages = [{
        "role": "system",
        "content": config.system_prompt,
    }]

    server = HTTPServer(("0.0.0.0", port), _WebUIHandler)

    print()
    print("  🌸  Simplicity Web UI")
    print(f"  →  http://localhost:{port}")
    print(f"  →  Model: {config.model}")
    print(f"  →  Press Ctrl+C to stop")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        server.server_close()
