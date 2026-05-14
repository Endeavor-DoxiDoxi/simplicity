#!/usr/bin/env bash
# ───────────────────────────────────────────────
#  Simplicity Installer — Linux / macOS
# ───────────────────────────────────────────────
set -euo pipefail

SIMPLICITY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.simplicity"
TOOLS_DIR="$CONFIG_DIR/tools"
WORKSPACE_DIR="$SIMPLICITY_DIR/workspace"

echo ""
echo "  .  .  .   S I M P L I C I T Y   I N S T A L L E R"
echo "  ------------------------------------------------"
echo ""
echo "  Install directory: $SIMPLICITY_DIR"
echo ""

# ── Pick environment type ────────────────────
echo "Choose environment type:"
echo "  [1] Virtual env (venv)    - lightweight, self-contained"
echo "  [2] Conda                  - if you use Anaconda/Miniconda"

if command -v conda &>/dev/null; then
    echo "  Conda detected!"
    DEFAULT_ENV=2
else
    echo "  Conda not found - defaulting to venv"
    DEFAULT_ENV=1
fi

read -p "Choice [$DEFAULT_ENV]: " env_choice
env_choice=${env_choice:-$DEFAULT_ENV}

# ── Discord support ───────────────────────────
echo ""
read -p "Install Discord bot support? (discord.py) [y/N]: " discord_choice
discord_choice=${discord_choice:-n}

# ── Pick wrapper name ─────────────────────────
echo ""
echo "Pick a command name:"
echo "  [1] simp          - short & quick"
echo "  [2] simplicity    - full name (recommended)"
read -p "Choice [2]: " name_choice
name_choice=${name_choice:-2}

# ── Python check ──────────────────────────────
find_python() {
    for py in python3 python; do
        if command -v "$py" &>/dev/null; then
            ver=$("$py" --version 2>&1 | grep -oP '\d+\.\d+')
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
                echo "$py"
                return 0
            fi
        fi
    done
    return 1
}

# ── Setup: venv ───────────────────────────────
setup_venv() {
    local VENV_DIR="$SIMPLICITY_DIR/.venv"
    local PYTHON
    PYTHON=$(find_python)
    if [ -z "$PYTHON" ]; then
        echo "ERROR: Python 3.11+ required. Install it first:"
        echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-full"
        echo "  macOS:         brew install python@3.13"
        exit 1
    fi
    echo "[OK] Found $PYTHON ($($PYTHON --version))"

    if [ ! -d "$VENV_DIR" ]; then
        echo "... Creating venv..."
        "$PYTHON" -m venv "$VENV_DIR"
    fi
    echo "[OK] Virtual environment ready"

    echo "... Installing Simplicity..."
    "$VENV_DIR/bin/pip" install -e "$SIMPLICITY_DIR" --quiet
    echo "[OK] Simplicity installed"
    if [ "$discord_choice" = "y" ] || [ "$discord_choice" = "Y" ]; then
        echo "... Installing discord.py..."
        "$VENV_DIR/bin/pip" install discord.py --quiet
        echo "[OK] Discord support installed"
    fi
}

# ── Setup: conda ──────────────────────────────
setup_conda() {
    if ! command -v conda &>/dev/null; then
        echo "ERROR: Conda not found. Please install it first."
        exit 1
    fi

    local ENV_NAME="simplicity"
    if conda env list | grep -q "^${ENV_NAME} "; then
        echo "[OK] Conda env '${ENV_NAME}' already exists"
    else
        echo "... Creating conda env '${ENV_NAME}' with Python 3.13..."
        conda create -y -n "$ENV_NAME" python=3.13 pip
    fi

    echo "... Installing Simplicity..."
    conda run -n "$ENV_NAME" pip install -e "$SIMPLICITY_DIR" --quiet
    echo "[OK] Simplicity installed"
    if [ "$discord_choice" = "y" ] || [ "$discord_choice" = "Y" ]; then
        echo "... Installing discord.py..."
        conda run -n "$ENV_NAME" pip install discord.py --quiet
        echo "[OK] Discord support installed"
    fi
}

# ── Run setup ─────────────────────────────────
if [ "$env_choice" = "2" ]; then
    setup_conda
else
    setup_venv
fi

# ── Create wrapper: always simp (guaranteed no conflict) ──
if [ "$env_choice" = "2" ]; then
    cat > "$SIMPLICITY_DIR/simp" << 'WRAPPER_EOF'
#!/usr/bin/env bash
exec conda run -n simplicity simplicity "$@"
WRAPPER_EOF
else
    cat > "$SIMPLICITY_DIR/simp" << 'WRAPPER_EOF'
#!/usr/bin/env bash
SIMPLICITY_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")")" && pwd)"
exec "$SIMPLICITY_DIR/.venv/bin/simplicity" "$@"
WRAPPER_EOF
fi
chmod +x "$SIMPLICITY_DIR/simp"
echo "[OK] Wrapper: ./simp"

# Also create simplicity.sh if user wants the full name
if [ "$name_choice" = "2" ]; then
    cp "$SIMPLICITY_DIR/simp" "$SIMPLICITY_DIR/simplicity.sh"
    chmod +x "$SIMPLICITY_DIR/simplicity.sh"
    echo "[OK] Wrapper: ./simplicity.sh"
fi

# ── Create config directories ─────────────────
mkdir -p "$CONFIG_DIR" "$TOOLS_DIR" "$WORKSPACE_DIR"
echo "[OK] Config:   $CONFIG_DIR"
echo "[OK] Workspace: $WORKSPACE_DIR"

# ── Copy example tools ────────────────────────
if [ -f "$SIMPLICITY_DIR/examples/get_datetime.py" ]; then
    cp "$SIMPLICITY_DIR/examples/get_datetime.py" "$TOOLS_DIR/" 2>/dev/null || true
    echo "[OK] Example tool installed"
fi

# ── Done ──────────────────────────────────────
SHELL_RC=""
case "$SHELL" in
    */zsh)   SHELL_RC="$HOME/.zshrc" ;;
    */bash)  SHELL_RC="$HOME/.bashrc" ;;
    */fish)  SHELL_RC="$HOME/.config/fish/config.fish" ;;
esac

echo ""
echo "  . . . . . . . . . . . . . . . . . . . . . . . ."
echo "  .  Simplicity installed successfully!"
echo "  . . . . . . . . . . . . . . . . . . . . . . . ."
echo ""
echo "  >> YOU ARE IN: $SIMPLICITY_DIR"
echo ""
echo "  Run Simplicity from THIS folder:"
echo "    ./simp chat"
echo ""
echo "  (simp was created right here — 'ls' shows it)"
echo "  (fallback: .venv/bin/simplicity chat)"
echo ""

if [ -n "$SHELL_RC" ]; then
    echo "  For global access (just 'simp'):"
    echo "    echo 'export PATH=\"\$PATH:$SIMPLICITY_DIR\"' >> $SHELL_RC"
    echo "    source $SHELL_RC"
else
    echo "  For global access, add this directory to your PATH"
fi
echo ""
echo "  First-time setup:"
echo "    ./simp auth"
echo ""
