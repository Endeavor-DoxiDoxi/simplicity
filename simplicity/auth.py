"""Bring Your Own Pollen (BYOP) authentication for Simplicity.

Uses the GitHub Pages auth.html relay page as the OAuth redirect endpoint.
A local server receives the API key callback.
"""

import json
import random
import string
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional


APP_KEY = "pk_GVZMVD9V84NNXCWd"
AUTH_RELAY = "https://endeavor-doxidoxi.github.io/auth.html"
AUTHORIZE_URL = "https://enter.pollinations.ai/authorize"
DEVICE_CODE_URL = "https://enter.pollinations.ai/api/device/code"
DEVICE_TOKEN_URL = "https://enter.pollinations.ai/api/device/token"
AUTH_LOG = Path.home() / ".simplicity" / "auth.log"
DEFAULT_PORT = 19876


# ── Auth logging ─────────────────────────────────────────────────

def _auth_log(msg: str):
    try:
        AUTH_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(AUTH_LOG, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def show_auth_log(console):
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


def _find_free_port(preferred: int = DEFAULT_PORT) -> int:
    import socket
    for offset in range(11):
        p = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    raise OSError(f"No free port in range {preferred}-{preferred+10}")


def _open_browser(url: str, console) -> bool:
    try:
        webbrowser.open(url)
        return True
    except Exception:
        console.print(f"[dim]Open manually: {url}[/]")
        return False


# ── Callback server ──────────────────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            data = json.loads(body)
            key = data.get("api_key", "")
            if key:
                self.server.api_key = key
                self.wfile.write(b'{"status":"ok"}')
                self.server.running = False
            else:
                self.wfile.write(b'{"status":"error","message":"no key"}')
        except Exception as e:
            self.wfile.write(json.dumps({"status":"error","message":str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass


def _run_callback_server(port: int, timeout: int) -> Optional[str]:
    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.api_key = None
    server.running = True
    server.timeout = 1
    deadline = time.monotonic() + timeout
    while server.running and time.monotonic() < deadline:
        server.handle_request()
    server.server_close()
    return server.api_key


# ── Auth check — nova-fast ONLY ──────────────────────────────────

def check_api_key(api_key: str, model: str = "nova-fast") -> dict:
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
            "User-Agent": "Simplicity/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": True, "status": resp.status, "message": "key works", "model": model}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("error", {}).get("message", body[:200])
        except json.JSONDecodeError:
            detail = body[:200]
        return {"ok": False, "status": e.code, "message": detail, "model": model}
    except Exception as e:
        return {"ok": False, "status": 0, "message": str(e)[:200], "model": model}


def run_auth_check(console, api_key: str, model: str = "nova-fast"):
    console.print(f"\n[dim]Verifying key...[/]", end=" ")
    result = check_api_key(api_key, model)
    _auth_log(f"auth_check: ok={result['ok']} status={result['status']} msg={result['message'][:80]}")
    if result["ok"]:
        console.print("[green]✅ Key works![/]")
    else:
        console.print(f"[red]❌ Failed (HTTP {result['status']})[/]")
        console.print(f"  [dim]{result['message'][:200]}[/]")
    return result["ok"]


# ── Web redirect flow ────────────────────────────────────────────

def web_redirect_login(console, port: int = DEFAULT_PORT) -> str:
    port = _find_free_port(port)
    state = _generate_state()

    _auth_log(f"web_redirect: port={port}")

    # Build relay URL with local server info
    relay_url = f"{AUTH_RELAY}?port={port}&state={state}&app_key={APP_KEY}"

    console.print()
    console.print("[bold cyan]🔐 Simplicity × Pollinations[/]")
    console.print("[dim]Bring Your Own Pollen — 25% supports the developer[/]")
    console.print()

    # Only warn if using a non-default port (custom setup)
    if port != DEFAULT_PORT:
        console.print(
            f"[yellow]⚠️  Using non-default port {port}.[/]\n"
            f"[yellow]   If you're using your own app key, register this redirect URI:\n"
            f"[yellow]   http://localhost:{port}[/]\n"
        )

    console.print(f"  [dim]Opening browser to sign in...[/]")

    _open_browser(relay_url, console)

    console.print(f"\n[dim]Waiting for authentication...[/]", end="\r")

    try:
        api_key = _run_callback_server(port, 120)
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/]")
        _auth_log("web_redirect: cancelled")
        raise WebRedirectCancelled()

    if not api_key:
        console.print("\n[yellow]⚠️  No response received.[/]")
        _auth_log("web_redirect: timeout")
        console.print("[dim]Try again or use: simp auth --device[/]")
        raise DeviceFlowError("No response. Try again or use --device fallback.")

    masked = api_key[:5] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    _auth_log(f"web_redirect: received key {masked}")

    console.print("[green]✅ Connected! Pollinations account linked.[/]")
    console.print("[dim]🌸 You bring the pollen — [green]25% supports the developer[/] ✨[/]\n")
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
        raise DeviceFlowError(f"Failed: {e}")

    user_code = device.get("user_code", "????")
    device_code = device.get("device_code", "")
    auth_url = device.get("verification_uri_complete",
                         f"https://enter.pollinations.ai/device?user_code={user_code}")
    _auth_log(f"device_flow: code={user_code}")
    console.print(f"  [bold]1.[/] Open: [link={auth_url}]{auth_url}[/link]")
    console.print(f"  [bold]2.[/] Code: [bold green]{user_code}[/]")
    console.print("  [bold]3.[/] Sign in with GitHub and approve\n")
    console.print("[dim]Waiting...[/]", end="\r")

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
                time.sleep(5); continue
            elif err == "expired_token":
                raise DeviceFlowError("Code expired.")
            else:
                raise DeviceFlowError(f"Failed: {err or body[:200]}")
        time.sleep(5)
    raise DeviceFlowError("Timed out")


# ── Unified entry ─────────────────────────────────────────────────

def byop_login(console=None, force_device: bool = False, skip_check: bool = False, port: int = DEFAULT_PORT) -> str:
    if console is None:
        class FB:
            def print(self, *a, **kw): print(*a)
        console = FB()

    _auth_log(f"byop_login: start (device={force_device})")

    if not force_device:
        try:
            api_key = web_redirect_login(console, port=port)
        except WebRedirectCancelled:
            raise
        except Exception as e:
            _auth_log(f"web_redirect failed: {e}")
            console.print(f"\n[yellow]⚠️  {e}[/]")
            console.print("[dim]Falling back to device flow...[/]")
            try:
                api_key = device_login(console)
            except Exception as e2:
                _auth_log(f"device also failed: {e2}")
                raise
    else:
        api_key = device_login(console)

    if not skip_check:
        run_auth_check(console, api_key)

    return api_key


class DeviceFlowError(Exception):
    pass


class WebRedirectCancelled(Exception):
    pass
