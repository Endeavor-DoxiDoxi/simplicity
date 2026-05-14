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

# ── Pick wrapper name ─────────────────────────
echo ""
echo "Pick a command name:"
echo "  [1] simp          - short & quick"
echo "  [2] simplicity    - full name (recommended)"
read -p "Choice [2]: " name_choice
name_choice=${name_choice:-2}

if [ "$name_choice" = "1" ]; then
    WRAPPER_NAME="simp"
else
    WRAPPER_NAME="simplicity"
fi

# Handle conflict: if simplicity/ dir exists, append .sh
if [ "$WRAPPER_NAME" = "simplicity" ] && [ -d "$SIMPLICITY_DIR/simplicity" ]; then
    WRAPPER_NAME="simplicity.sh"
    echo "  Note: 'simplicity' is the package dir, using 'simplicity.sh' instead"
fi
WRAPPER_BIN="$SIMPLICITY_DIR/$WRAPPER_NAME"

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
}

# ── Run setup ─────────────────────────────────
if [ "$env_choice" = "2" ]; then
    setup_conda
else
    setup_venv
fi

# ── Create wrapper script ─────────────────────
if [ "$env_choice" = "2" ]; then
    cat > "$WRAPPER_BIN" << 'WRAPPER_EOF'
#!/usr/bin/env bash
# Simplicity wrapper (conda)
exec conda run -n simplicity simplicity "$@"
WRAPPER_EOF
else
    cat > "$WRAPPER_BIN" << 'WRAPPER_EOF'
#!/usr/bin/env bash
# Simplicity wrapper (venv)
SIMPLICITY_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")")" && pwd)"
exec "$SIMPLICITY_DIR/.venv/bin/simplicity" "$@"
WRAPPER_EOF
fi
chmod +x "$WRAPPER_BIN"
echo "[OK] Wrapper: ./$WRAPPER_NAME"

# ── Create config directories ─────────────────
mkdir -p "$CONFIG_DIR" "$TOOLS_DIR" "$WORKSPACE_DIR"
echo "[OK] Config:   $CONFIG_DIR"
echo "[OK] Workspace: $WORKSPACE_DIR"

# ── Copy example tools ────────────────────────
if [ -f "$SIMPLICITY_DIR/examples/get_datetime.py" ]; then
    cp "$SIMPLICITY_DIR/examples/get_datetime.py" "$TOOLS_DIR/" 2>/dev/null || true
    echo "[OK] Example tool installed"
fi

# ── PATH setup ────────────────────────────────
echo ""
echo "  . . . . . . . . . . . . . . . . . . . . . . . ."
echo "  .  Simplicity installed successfully!"
echo "  . . . . . . . . . . . . . . . . . . . . . . . ."
echo ""

SHELL_RC=""
case "$SHELL" in
    */zsh)   SHELL_RC="$HOME/.zshrc" ;;
    */bash)  SHELL_RC="$HOME/.bashrc" ;;
    */fish)  SHELL_RC="$HOME/.config/fish/config.fish" ;;
esac

echo "  Run right now:"
echo "    ./$WRAPPER_NAME chat"
echo ""

if [ -n "$SHELL_RC" ]; then
    echo "  For global access (just '$WRAPPER_NAME'):"
    echo "    echo 'export PATH=\"\$PATH:$SIMPLICITY_DIR\"' >> $SHELL_RC"
    echo "    source $SHELL_RC"
    echo ""
    echo "  After that, just run: $WRAPPER_NAME chat"
else
    echo "  For global access, add this directory to your PATH"
fi
echo ""
echo "  First-time setup:"
echo "    ./$WRAPPER_NAME auth"
echo ""
