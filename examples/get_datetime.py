"""Example custom tool: Get current date/time information.

Drop this file in ~/.simplicity/tools/ to add it to Simplicity.
"""

from datetime import datetime

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_datetime",
        "description": "Get the current date, time, and day of week",
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "Timezone name (optional, e.g. 'America/Denver')",
                }
            },
            "required": [],
        },
    },
}


def execute(timezone: str = "UTC") -> str:
    now = datetime.now()
    return (
        f"Current date: {now.strftime('%Y-%m-%d')}\n"
        f"Current time: {now.strftime('%H:%M:%S')}\n"
        f"Day of week: {now.strftime('%A')}\n"
        f"Timezone: {timezone}"
    )
