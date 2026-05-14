"""Bring Your Own Pollen (BYOP) authentication for Simplicity.

Two flows:
  1. Web redirect (primary): Opens browser → GitHub Pages relay →
     Pollinations OAuth → API key sent back to local server.
  2. Device flow (fallback): Manual code entry for headless systems.

Flow 1 (Web Redirect):
  1. CLI starts temporary local HTTP server
  2. Opens browser to GitHub Pages auth.html with port + state params
  3. auth.html stores params → redirects to Pollinations authorize
  4. User approves → Pollinations redirects to auth.html#api_key=...
  5. auth.html POSTs key to localhost:{port}
  6. CLI receives key, stops server, saves config
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
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional


# ── Constants ────────────────────────────────────────────────────

APP_KEY = "pk_GVZMVD9V84NNXCWd"
AUTH_RELAY = "https://endeavor-doxidoxi.github.io/auth.html"
AUTHORIZE_URL = "https://enter.pollinations.ai/authorize"

# Device flow (fallback)
DEVICE_CODE_URL = "https://enter.pollinations.ai/api/device/code"
DEVICE_TOKEN_URL = "https://enter.pollinations.ai/api/device/token"

# Local server
SERVER_TIMEOUT = 120  # seconds


# ── Helpers ──────────────────────────────────────────────────────

def _generate_state(length: int = 32) -> str:
    """Generate a random CSRF state token."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def _find_free_port() -> int:
    """Find a free TCP port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _open_browser(url: str, console) -> bool:
    """Try to open a URL in the browser. Returns True if successful."""
    try:
        webbrowser.open(url)
        return True
    except Exception:
        console.print(f"[dim]Could not open browser. Open this URL manually:[/]")
        console.print(f"[cyan]{url}[/]")
        return False


# ── Local callback server ────────────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the single POST from auth.html with the API key."""

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        # CORS headers (auth.html is on a different origin)
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
            # Shutdown after handling this request
            self.server.running = False

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def _run_callback_server(port: int, timeout: int) -> Optional[str]:
    """Run a temporary HTTP server to receive the API key callback.

    Returns the API key or None on timeout/failure.
    """
    server = HTTPServer(('127.0.0.1', port), _CallbackHandler)
    server.api_key = None
    server.running = True
    server.timeout = 1  # poll every second

    deadline = time.monotonic() + timeout
    while server.running and time.monotonic() < deadline:
        server.handle_request()

    server.server_close()
    return server.api_key


# ── Web redirect flow (primary) ──────────────────────────────────

def web_redirect_login(console) -> str:
    """Run the web redirect BYOP login flow.

    Starts a local server, opens browser to GitHub Pages auth relay,
    waits for the callback with the API key.

    Returns the user's API key (sk_...).
    """
    port = _find_free_port()
    state = _generate_state()

    # Build the auth relay URL
    relay_params = f"port={port}&state={state}&app_key={APP_KEY}"
    relay_url = f"{AUTH_RELAY}?{relay_params}"

    # Show instructions
    console.print()
    console.print("[bold cyan]🔐 Simplicity × Pollinations[/]")
    console.print("[dim]Bring Your Own Pollen — 25% supports the developer[/]")
    console.print()
    console.print(f"  [dim]Local server:[/] [green]localhost:{port}[/]")
    console.print(
        f"  [dim]Opening browser to sign in with Pollinations...[/]"
    )

    _open_browser(relay_url, console)

    console.print()
    console.print("[dim]Waiting for authentication...[/]", end="\r")

    try:
        api_key = _run_callback_server(port, SERVER_TIMEOUT)
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/]")
        raise WebRedirectCancelled()

    if not api_key:
        console.print("\n[yellow]⚠️  Authentication timed out.[/]")
        raise DeviceFlowError(
            "No response received. Please try again or use a device flow."
        )

    console.print("[green]✅ Connected! Pollinations account linked.[/]")
    console.print(
        "[dim]🌸 You bring the pollen — [green]25% supports the developer[/] ✨[/]\n"
    )

    return api_key


# ── Device flow (fallback) ───────────────────────────────────────

def _post_json(url: str, data: dict) -> dict:
    """Make a JSON POST request."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Simplicity/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def device_login(console) -> str:
    """Run the device code BYOP login flow (fallback for headless systems).

    Returns the user's API key (sk_...).
    """
    console.print("\n[bold cyan]🔐 Simplicity × Pollinations (Device Flow)[/]")
    console.print("[dim]Bring Your Own Pollen — you pay, we both win[/]\n")

    # Step 1: Request device code
    try:
        device = _post_json(DEVICE_CODE_URL, {
            "client_id": APP_KEY,
            "scope": "generate",
        })
    except Exception as e:
        raise DeviceFlowError(f"Failed to request device code: {e}")

    user_code = device.get("user_code", "????")
    device_code = device.get("device_code", "")
    auth_url = device.get(
        "verification_uri_complete",
        f"https://enter.pollinations.ai/device?user_code={user_code}",
    )

    if not device_code:
        raise DeviceFlowError("No device code in response")

    console.print(f"  [bold]1.[/] Open: [link={auth_url}]{auth_url}[/link]")
    console.print(f"  [bold]2.[/] Code: [bold green]{user_code}[/]")
    console.print("  [bold]3.[/] Sign in with GitHub and approve")
    console.print()

    # Step 2: Poll for token
    console.print("[dim]Waiting for approval...[/]", end="\r")
    deadline = time.monotonic() + 180

    while time.monotonic() < deadline:
        try:
            result = _post_json(DEVICE_TOKEN_URL, {"device_code": device_code})
            if "access_token" in result:
                token = result["access_token"]
                console.print("[green]✅ Connected! Pollinations account linked.[/]")
                console.print(
                    "[dim]🌸 You bring the pollen — [green]25% supports the developer[/] ✨[/]\n"
                )
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
                raise DeviceFlowError("Device code expired. Please try again.")
            else:
                raise DeviceFlowError(f"Token request failed: {err or body[:200]}")
        time.sleep(5)

    raise DeviceFlowError("Login timed out")


# ── Unified login entry point ────────────────────────────────────

def byop_login(console=None, force_device: bool = False) -> str:
    """Run the BYOP login flow. Tries web redirect first, falls back to device flow.

    Args:
        console: Rich Console for output
        force_device: Skip web redirect, use device flow directly

    Returns:
        The user's API key (sk_...)
    """
    if console is None:
        class FallbackConsole:
            def print(self, *a, **kw): print(*a)
        console = FallbackConsole()

    # Try web redirect flow first (unless forced device or no browser available)
    if not force_device:
        try:
            return web_redirect_login(console)
        except WebRedirectCancelled:
            raise
        except Exception as e:
            console.print(f"\n[yellow]⚠️  Web redirect failed: {e}[/]")
            console.print("[dim]Falling back to device flow...[/]")

    return device_login(console)


# ── Exceptions ───────────────────────────────────────────────────

class DeviceFlowError(Exception):
    """Raised when the device/auth flow fails."""
    pass


class WebRedirectCancelled(Exception):
    """Raised when the user cancels the web redirect flow."""
    pass
