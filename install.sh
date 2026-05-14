#!/usr/bin/env bash
# ───────────────────────────────────────────────
#  Simplicity Installer — Linux / macOS
# ───────────────────────────────────────────────
set -euo pipefail

SIMPLICITY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SIMPLICITY_DIR/.venv"
WRAPPER_BIN="$SIMPLICITY_DIR/simplicity"
CONFIG_DIR="$HOME/.simplicity"
TOOLS_DIR="$CONFIG_DIR/tools"
WORKSPACE_DIR="$SIMPLICITY_DIR/workspace"

echo ""
echo "  🌸  S I M P L I C I T Y   I N S T A L L E R"
echo "  ─────────────────────────────────────────"
echo ""

# ── Python check ──────────────────────────────
PYTHON=""
for py in python3 python; do
    if command -v "$py" &>/dev/null; then
        ver=$("$py" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$py"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ Python 3.11+ is required. Install it first:"
    echo "   Ubuntu/Debian: sudo apt install python3 python3-venv python3-full"
    echo "   macOS:         brew install python@3.13"
    exit 1
fi
echo "✅ Found $PYTHON ($($PYTHON --version))"

# ── Virtual environment ───────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
fi
echo "✅ Virtual environment ready"

# ── Install package ───────────────────────────
echo "📦 Installing Simplicity..."
"$VENV_DIR/bin/pip" install -e "$SIMPLICITY_DIR" --quiet
echo "✅ Simplicity installed"

# ── Create wrapper script ─────────────────────
cat > "$WRAPPER_BIN" << 'WRAPPER_EOF'
#!/usr/bin/env bash
# Simplicity wrapper — auto-activates venv
SIMPLICITY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SIMPLICITY_DIR/.venv/bin/python" -m simplicity "$@"
WRAPPER_EOF
chmod +x "$WRAPPER_BIN"
echo "✅ Wrapper script: $WRAPPER_BIN"

# ── Create config directories ─────────────────
mkdir -p "$CONFIG_DIR" "$TOOLS_DIR" "$WORKSPACE_DIR"
echo "✅ Config:    $CONFIG_DIR"
echo "✅ Workspace: $WORKSPACE_DIR"

# ── Copy example tools ────────────────────────
if [ -f "$SIMPLICITY_DIR/examples/get_datetime.py" ]; then
    cp "$SIMPLICITY_DIR/examples/get_datetime.py" "$TOOLS_DIR/" 2>/dev/null || true
    echo "✅ Example tool installed"
fi

# ── Add to PATH suggestion ────────────────────
SHELL_RC=""
case "$SHELL" in
    */zsh)   SHELL_RC="$HOME/.zshrc" ;;
    */bash)  SHELL_RC="$HOME/.bashrc" ;;
    */fish)  SHELL_RC="$HOME/.config/fish/config.fish" ;;
esac

echo ""
echo "  ┌─────────────────────────────────────────┐"
echo "  │  🌸 Simplicity installed successfully!  │"
echo "  └─────────────────────────────────────────┘"
echo ""
echo "  To use it from anywhere, add to your PATH:"
echo ""
if [ -n "$SHELL_RC" ]; then
    echo "    echo 'export PATH=\"$SIMPLICITY_DIR:\$PATH\"' >> $SHELL_RC"
    echo "    source $SHELL_RC"
else
    echo "    export PATH=\"$SIMPLICITY_DIR:\$PATH\""
fi
echo ""
echo "  Or just run directly:"
echo "    $WRAPPER_BIN chat"
echo ""
echo "  First-time setup:"
echo "    $WRAPPER_BIN auth"
echo "    $WRAPPER_BIN setup"
echo ""
