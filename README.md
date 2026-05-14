# 🌸 Simplicity

**AI Chat CLI powered by [Pollinations.ai](https://pollinations.ai)**

A beautiful, easy-to-use terminal AI assistant with tool calling, streaming, and a plugin system.

## Features

- 🗣️ **Interactive chat** with streaming responses
- 🔧 **Tool calling** — AI can read/write files, run commands, search the web
- 🧩 **Custom tools** — drop Python files in `~/.simplicity/tools/`
- 🎨 **Beautiful TUI** — syntax-highlighted code, rich markdown
- 🚀 **One-shot mode** — `simplicity ask "explain this code"`
- 💰 **Balance checking** — `simplicity balance`
- 📋 **Model listing** — `simplicity models`
- 💾 **Conversation saving** — `/save` in chat mode
- 🔌 **OpenAI-compatible** — works with any compatible API

## Quick Start

### 🚀 One-Command Install

```bash
# 1. Clone
git clone https://github.com/Endeavor-DoxiDoxi/simplicity.git
cd simplicity

# 2. Install (auto-creates venv, wrapper, workspace)
./install.sh        # Linux / macOS
# or
install.bat         # Windows (double-click or run in cmd)

# 3. Sign in (BYOP — you bring pollen, dev earns 25%)
./simplicity auth

# 4. Chat!
./simplicity chat
```

That's it. The installer creates everything — venv, wrapper script, config, and workspace. No global pip install needed.

### Manual Install

```bash
pip install -e . --break-system-packages  # or use a venv
simplicity setup
simplicity chat
```

## Get an API Key

### 🌸 Bring Your Own Pollen (Recommended!)

```bash
simplicity auth
```

This opens a browser-based login flow:
1. CLI shows you a code and URL
2. Open the URL, enter the code
3. Sign in with GitHub
4. Your API key is automatically saved

**Why BYOP?**
- 🔒 You control your own pollen balance
- 💰 25% of your usage supports the Simplicity developer
- ⚡ No copy-pasting keys needed
- 🎯 Usage counts toward Pollinations tier upgrades

### Manual Key Entry

```bash
simplicity setup
```

1. Go to [enter.pollinations.ai](https://enter.pollinations.ai)
2. Sign in with GitHub, copy your API key (starts with `sk_`)
3. Choose option 2 in setup and paste it

## Commands

### Chat Mode (`simplicity chat`)

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/quit` | Exit chat |
| `/clear` | Clear conversation |
| `/model <name>` | Change model |
| `/balance` | Check pollen balance |
| `/tools` | List available tools |
| `/save [file]` | Save conversation |
| `/system <prompt>` | Set custom system prompt |

### CLI Commands

```bash
simplicity chat              # Interactive chat (default)
simplicity ask "prompt"      # One-shot question
simplicity auth              # Sign in with Pollinations (BYOP)
simplicity setup             # Configure API key + model
simplicity models            # List available models
simplicity balance           # Check pollen balance
simplicity tools             # List available tools
```

## Tools

Simplicity includes built-in tools the AI can use:

- **read_file** — Read file contents
- **write_file** — Create or overwrite files
- **list_directory** — List files in a directory
- **run_command** — Execute shell commands (requires approval)
- **web_search** — Search the web via DuckDuckGo

### Custom Tools

Create a Python file in `~/.simplicity/tools/`:

```python
# ~/.simplicity/tools/get_weather.py

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name"
                }
            },
            "required": ["city"]
        }
    }
}

def execute(city: str) -> str:
    # Your implementation here
    return f"The weather in {city} is sunny, 72°F"
```

## Configuration

Config is stored at `~/.simplicity/config.json`:

```json
{
  "api_key": "sk_...",
  "model": "openai",
  "system_prompt": "You are a helpful AI assistant...",
  "max_tokens": 4096,
  "temperature": 0.7,
  "stream": true
}
```

Environment variable override: `SIMPLICITY_API_KEY=sk_...`

## Available Models

Pollinations provides access to many models:

- `openai` — Fast, general purpose
- `openai-large` — More capable
- `qwen-coder` — Optimized for coding
- `claude-fast` — Claude speed
- `claude-opus-4.7` — Claude Opus (powerful)
- `deepseek` — DeepSeek
- `gemini` — Google Gemini
- `gpt-5.5` — Latest GPT
- `mistral-large` — Mistral (large)
- And many more!

## Requirements

- Python 3.11+
- `rich` (auto-installed)

## Platform Support

- 🐧 **Linux** — full support
- 🍎 **macOS** — full support
- 🪟 **Windows** — full support (Windows Terminal recommended)

## License

MIT
