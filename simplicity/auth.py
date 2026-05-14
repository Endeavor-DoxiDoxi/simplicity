"""Bring Your Own Pollen (BYOP) authentication for Simplicity.

Two flows:
  1. Web redirect (primary): Opens browser → GitHub Pages relay →
     Pollinations OAuth → API key sent back to local server.
  2. Device flow (fallback): Manual code entry for headless systems.

Includes optional auth-check (ping) and auth logging.
"""

import json
import os
import random
import string
import sys
import time
import urllib.request
import urllib.error
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional


# ── Constants ────────────────────────────────────────────────────

APP_KEY = "pk_GVZMVD9V84NNXCWd"
AUTH_RELAY = "https://endeavor-doxidoxi.github.io/auth.html"
AUTHORIZE_URL = "https://enter.pollinations.ai/authorize"

DEVICE_CODE_URL = "https://enter.pollinations.ai/api/device/code"
DEVICE_TOKEN_URL = "https://enter.pollinations.ai/api/device/token"

SERVER_TIMEOUT = 120
AUTH_LOG = Path.home() / ".simplicity" / "auth.log"


# ── Auth logging ─────────────────────────────────────────────────

def _auth_log(msg: str):
    """Write a timestamped line to the auth log (no secrets)."""
    try:
        AUTH_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(AUTH_LOG, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def show_auth_log(console):
    """Display the last 30 lines of the auth log."""
    if not AUTH_LOG.exists():
        console.print("[dim]No auth log yet.[/]")
        return
    lines = AUTH_LOG.read_text().splitlines()[-30:]
    console.print(f"\n[bold]Auth log ({AUTH_LOG}):[/]\n")
    for line in lines:
        console.print(f"  [dim]{line}[/]")
    console.print()


# ── Helpers ──────────────────────────────────────────────────────

def _generate_state(length: int = 32) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def _find_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _open_browser(url: str, console) -> bool:
    try:
        webbrowser.open(url)
        return True
    except Exception:
        console.print(f"[dim]Open manually: {url}[/]")
        return False


# ── Local callback server ────────────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try:
            data = json.loads(body)
            api_key = data.get('api_key', '')
            if api_key:
                self.server.api_key = api_key
                self.wfile.write(json.dumps({'status': 'ok'}).encode())
            else:
                self.wfile.write(json.dumps({'status': 'error', 'message': 'no api_key'}).encode())
        except Exception as e:
            self.wfile.write(json.dumps({'status': 'error', 'message': str(e)}).encode())
        finally:
            self.server.running = False

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        pass


def _run_callback_server(port: int, timeout: int) -> Optional[str]:
    server = HTTPServer(('127.0.0.1', port), _CallbackHandler)
    server.api_key = None
    server.running = True
    server.timeout = 1
    deadline = time.monotonic() + timeout
    while server.running and time.monotonic() < deadline:
        server.handle_request()
    server.server_close()
    return server.api_key


# ── Auth check (ping) ────────────────────────────────────────────

def check_api_key(api_key: str, model: str = "nova-fast") -> dict:
    """Test if the API key works by sending a minimal chat ping.
    
    Returns dict with: ok (bool), status (int), message (str), model (str)
    """
    data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://gen.pollinations.ai/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": True, "status": resp.status, "message": "key works", "model": model}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body)
            detail = err.get("error", {}).get("message", body[:200])
        except json.JSONDecodeError:
            detail = body[:200]
        return {"ok": False, "status": e.code, "message": detail, "model": model}
    except Exception as e:
        return {"ok": False, "status": 0, "message": str(e)[:200], "model": model}


def run_auth_check(console, api_key: str, model: str = "nova-fast"):
    """Run an optional auth check and display results. Tests nova-fast ONLY."""
    console.print(f"\n[dim]Verifying key with '{model}'...[/]", end=" ")
    result = check_api_key(api_key, model)

    _auth_log(
        f"auth_check: model={model} ok={result['ok']} "
        f"status={result['status']} msg={result['message'][:80]}"
    )

    if result["ok"]:
        console.print("[green]✅ Key works![/]")
        _auth_log("auth_check: PASS")
    else:
        console.print(f"[red]❌ Key check failed (HTTP {result['status']})[/]")
        console.print(f"  [dim]Error: {result['message'][:200]}[/]")
        _auth_log(f"auth_check: FAIL (HTTP {result['status']})")
        
        if result["status"] == 403:
            console.print("\n[yellow]The key was created but doesn't have generation permission.[/]")
            console.print("[dim]This usually means the Pollinations app key needs its redirect URI\n"
                          "configured at enter.pollinations.ai:\n"
                          "  1. Go to https://enter.pollinations.ai\n"
                          "  2. Find app key pk_GVZMVD9V84NNXCWd\n"
                          "  3. Add redirect URI:\n"
                          "     https://endeavor-doxidoxi.github.io/auth.html[/]")
            console.print(f"\n[dim]Full auth log: [bold]simp auth-log[/] (or {AUTH_LOG})[/]")

    return result["ok"]


# ── Web redirect flow (primary) ──────────────────────────────────

def web_redirect_login(console) -> str:
    port = _find_free_port()
    state = _generate_state()

    _auth_log(f"web_redirect: starting on port {port}")

    relay_params = f"port={port}&state={state}&app_key={APP_KEY}"
    relay_url = f"{AUTH_RELAY}?{relay_params}"

    console.print()
    console.print("[bold cyan]🔐 Simplicity × Pollinations[/]")
    console.print("[dim]Bring Your Own Pollen — 25% supports the developer[/]")
    console.print()
    console.print(f"  [dim]Local server:[/] [green]localhost:{port}[/]")
    console.print(f"  [dim]Opening browser...[/]")

    _open_browser(relay_url, console)

    console.print()
    console.print("[dim]Waiting for authentication...[/]", end="\r")

    try:
        api_key = _run_callback_server(port, SERVER_TIMEOUT)
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/]")
        _auth_log("web_redirect: cancelled by user")
        raise WebRedirectCancelled()

    if not api_key:
        console.print("\n[yellow]⚠️  No response received.[/]")
        _auth_log("web_redirect: timeout — no key received")
        console.print(
            "[dim]If the browser showed an error, configure the redirect URI:\\n"
            "  Go to https://enter.pollinations.ai\\n"
            "  Edit app key → Add redirect: https://endeavor-doxidoxi.github.io/auth.html\\n"
            "Or fall back to device flow: simp auth --device[/]"
        )
        raise DeviceFlowError("No response. Try --device fallback or configure redirect URI.")

    # Mask key for logging
    masked = api_key[:5] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    _auth_log(f"web_redirect: received key {masked}")

    console.print("[green]✅ Connected! Pollinations account linked.[/]")
    console.print(
        "[dim]🌸 You bring the pollen — [green]25% supports the developer[/] ✨[/]\n"
    )

    return api_key


# ── Device flow (fallback) ───────────────────────────────────────

def _post_json(url: str, data: dict) -> dict:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Simplicity/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def device_login(console) -> str:
    _auth_log("device_flow: starting")
    console.print("\n[bold cyan]🔐 Simplicity × Pollinations (Device Flow)[/]")

    try:
        device = _post_json(DEVICE_CODE_URL, {"client_id": APP_KEY})
    except Exception as e:
        _auth_log(f"device_flow: code request failed: {e}")
        raise DeviceFlowError(f"Failed to request device code: {e}")

    user_code = device.get("user_code", "????")
    device_code = device.get("device_code", "")
    auth_url = device.get("verification_uri_complete",
                         f"https://enter.pollinations.ai/device?user_code={user_code}")

    _auth_log(f"device_flow: code={user_code}")
    console.print(f"  [bold]1.[/] Open: [link={auth_url}]{auth_url}[/link]")
    console.print(f"  [bold]2.[/] Code: [bold green]{user_code}[/]")
    console.print("  [bold]3.[/] Sign in with GitHub and approve")
    console.print()

    console.print("[dim]Waiting for approval...[/]", end="\r")
    deadline = time.monotonic() + 180

    while time.monotonic() < deadline:
        try:
            result = _post_json(DEVICE_TOKEN_URL, {"device_code": device_code})
            if "access_token" in result:
                token = result["access_token"]
                masked = token[:5] + "..." + token[-4:] if len(token) > 10 else "***"
                _auth_log(f"device_flow: received key {masked}")
                console.print("[green]✅ Connected![/]")
                return token
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                err = json.loads(body).get("error", "")
            except json.JSONDecodeError:
                err = ""
            if err in ("authorization_pending", "slow_down"):
                time.sleep(5)
                continue
            elif err == "expired_token":
                _auth_log("device_flow: code expired")
                raise DeviceFlowError("Device code expired.")
            else:
                raise DeviceFlowError(f"Token request failed: {err or body[:200]}")
        time.sleep(5)

    _auth_log("device_flow: timeout")
    raise DeviceFlowError("Login timed out")


# ── Unified login entry point ────────────────────────────────────

def byop_login(console=None, force_device: bool = False, skip_check: bool = False) -> str:
    if console is None:
        class FB:  # Fallback
            def print(self, *a, **kw): print(*a)
        console = FB()

    _auth_log("byop_login: start (device=" + str(force_device) + ")")

    # Try web redirect first
    if not force_device:
        try:
            api_key = web_redirect_login(console)
        except WebRedirectCancelled:
            raise
        except Exception as e:
            _auth_log(f"web_redirect failed: {e}")
            console.print(f"\n[yellow]⚠️  Web redirect failed: {e}[/]")
            console.print("[dim]Falling back to device flow...[/]")
            try:
                api_key = device_login(console)
            except Exception as e2:
                _auth_log(f"device_flow also failed: {e2}")
                raise
    else:
        api_key = device_login(console)

    # Optional auth check
    if not skip_check:
        run_auth_check(console, api_key)

    return api_key


# ── Exceptions ───────────────────────────────────────────────────

class DeviceFlowError(Exception):
    pass


class WebRedirectCancelled(Exception):
    pass
