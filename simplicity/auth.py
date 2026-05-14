"""Bring Your Own Pollen (BYOP) device flow authentication.

Lets users sign in with their Pollinations account through a browser,
so they bring their own pollen and the app developer earns royalties.

Flow:
  1. Request a device code from Pollinations
  2. User opens browser, enters code at enter.pollinations.ai/device
  3. CLI polls for the access token
  4. Token is saved and used for all API calls
"""

import json
import time
import urllib.request
import urllib.error
from typing import Optional


# Doxi's publishable app key — safe for client-side code
# Developer earnings enabled: 25% markup → credits to Doxi's balance
APP_KEY = "pk_GVZMVD9V84NNXCWd"

DEVICE_CODE_URL = "https://enter.pollinations.ai/api/device/code"
DEVICE_TOKEN_URL = "https://enter.pollinations.ai/api/device/token"
AUTH_PAGE = "https://enter.pollinations.ai/device"
POLL_INTERVAL = 5  # seconds


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


def request_device_code() -> Optional[dict]:
    """Request a device code from Pollinations.

    Returns dict with device_code, user_code, verification_uri
    or None on failure.
    """
    try:
        result = _post_json(DEVICE_CODE_URL, {
            "client_id": APP_KEY,
            "scope": "generate",
        })
        return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
            msg = data.get("error_description") or data.get("error") or body
        except json.JSONDecodeError:
            msg = body[:500]
        raise DeviceFlowError(f"Failed to request device code: {msg}")
    except Exception as e:
        raise DeviceFlowError(f"Network error: {e}")


def poll_for_token(device_code: str, timeout_seconds: int = 120) -> Optional[str]:
    """Poll for the access token until the user approves or timeout.

    Returns the access_token (sk_...) or None on timeout.
    """
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        try:
            result = _post_json(DEVICE_TOKEN_URL, {
                "device_code": device_code,
            })

            if "access_token" in result:
                return result["access_token"]

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
                err = data.get("error", "")
            except json.JSONDecodeError:
                err = ""

            if err == "authorization_pending":
                # User hasn't approved yet — keep polling
                time.sleep(POLL_INTERVAL)
                continue
            elif err == "slow_down":
                # Polling too fast
                time.sleep(POLL_INTERVAL + 2)
                continue
            elif err == "expired_token":
                raise DeviceFlowError("Device code expired. Please try again.")
            else:
                raise DeviceFlowError(f"Token request failed: {err or body[:200]}")

        time.sleep(POLL_INTERVAL)

    return None  # Timeout


def byop_login(rich_console=None, rich_progress=None) -> str:
    """Run the full BYOP device flow login.

    Shows instructions to the user, polls for approval,
    and returns the API key.

    Args:
        rich_console: Optional Rich Console for pretty output
        rich_progress: Optional Rich Progress for spinner

    Returns:
        The user's API key (sk_...)
    """
    if rich_console is None:
        import sys
        class FallbackConsole:
            def print(self, *a, **kw): print(*a)
        rich_console = FallbackConsole()

    # Step 1: Request device code
    rich_console.print("\n[bold cyan]🔐 Simplicity × Pollinations[/]")
    rich_console.print("[dim]Bring Your Own Pollen — you pay, we both win[/]\n")

    try:
        device = request_device_code()
    except DeviceFlowError as e:
        rich_console.print(f"[red]❌ {e}[/]")
        raise

    user_code = device.get("user_code", "????")
    device_code = device.get("device_code", "")
    
    # Use the pre-filled URL if available, otherwise build it
    auth_url = device.get(
        "verification_uri_complete",
        f"https://enter.pollinations.ai/device?user_code={user_code}"
    )

    if not device_code:
        rich_console.print("[red]❌ No device code received[/]")
        raise DeviceFlowError("No device code in response")

    # Step 2: Show instructions
    rich_console.print()
    rich_console.print(
        f"  [bold]1.[/] Open: [link={auth_url}]{auth_url}[/link]"
    )
    rich_console.print(
        f"  [bold]2.[/] Code: [bold green]{user_code}[/] (pre-filled if you use the link above)"
    )
    rich_console.print(
        "  [bold]3.[/] Sign in with GitHub and approve"
    )
    rich_console.print()

    # Step 3: Poll for token
    rich_console.print("[dim]Waiting for approval...[/]", end="\r")

    try:
        token = poll_for_token(device_code, timeout_seconds=180)
    except DeviceFlowError as e:
        rich_console.print(f"\n[red]❌ {e}[/]")
        raise

    if not token:
        rich_console.print("\n[red]❌ Login timed out. Please try again.[/]")
        raise DeviceFlowError("Login timed out")

    rich_console.print("[green]✅ Connected! Pollinations account linked.[/]")
    rich_console.print(
        "[dim]🌸 You bring the pollen — [green]25% supports the developer[/] ✨[/]\n"
    )

    return token


class DeviceFlowError(Exception):
    """Raised when the device flow fails."""
    pass
