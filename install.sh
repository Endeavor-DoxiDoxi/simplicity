#!/usr/bin/env bash
# ───────────────────────────────────────────────
#  Simplicity Installer — Linux / macOS
# ───────────────────────────────────────────────
set -euo pipefail

SIMPLICITY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.simplicity"
TOOLS_DIR="$CONFIG_DIR/tools"
WORKSPACE_DIR="$SIMPLICITY_DIR/workspace"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "  ${CYAN}🌸  S I M P L I C I T Y   I N S T A L L E R${NC}"
echo -e "  ─────────────────────────────────────────"
echo ""

# ── Pick environment type ────────────────────
echo -e "${BOLD}Choose environment type:${NC}"
echo "  [1] Virtual env (venv)     — lightweight, self-contained"
echo "  [2] Conda                   — if you use Anaconda/Miniconda"

if command -v conda &>/dev/null; then
    echo -e "  ${GREEN}Conda detected!${NC}"
    DEFAULT_ENV=2
else
    echo -e "  ${YELLOW}Conda not found — defaulting to venv${NC}"
    DEFAULT_ENV=1
fi

read -p "$(echo -e "${BOLD}Choice [${DEFAULT_ENV}]${NC}: ")" env_choice
env_choice=${env_choice:-$DEFAULT_ENV}

# ── Pick wrapper name ─────────────────────────
echo ""
echo -e "${BOLD}Pick a command name:${NC}"
echo "  [1] simp          — short & quick"
echo "  [2] simplicity    — full name (recommended)"
read -p "$(echo -e "${BOLD}Choice [2]${NC}: ")" name_choice
name_choice=${name_choice:-2}

if [ "$name_choice" = "1" ]; then
    WRAPPER_NAME="simp"
else
    WRAPPER_NAME="simplicity"
fi

# Handle conflict: if simplicity/ dir exists, append .sh
if [ "$WRAPPER_NAME" = "simplicity" ] && [ -d "$SIMPLICITY_DIR/simplicity" ]; then
    WRAPPER_NAME="simplicity.sh"
    echo -e "  ${YELLOW}Note: 'simplicity' is the package dir, using 'simplicity.sh' instead${NC}"
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
        echo -e "${RED}❌ Python 3.11+ required. Install it first:${NC}"
        echo "   Ubuntu/Debian: sudo apt install python3 python3-venv python3-full"
        echo "   macOS:         brew install python@3.13"
        exit 1
    fi
    echo -e "${GREEN}✅ Found $PYTHON ($($PYTHON --version))${NC}"

    if [ ! -d "$VENV_DIR" ]; then
        echo "📦 Creating venv..."
        "$PYTHON" -m venv "$VENV_DIR"
    fi
    echo -e "${GREEN}✅ Virtual environment ready${NC}"

    echo "📦 Installing Simplicity..."
    "$VENV_DIR/bin/pip" install -e "$SIMPLICITY_DIR" --quiet
    echo -e "${GREEN}✅ Simplicity installed${NC}"

    # Wrapper uses venv's installed simplicity entry point
    SIMPLICITY_CMD="$SIMPLICITY_DIR/.venv/bin/simplicity"
}

# ── Setup: conda ──────────────────────────────
setup_conda() {
    if ! command -v conda &>/dev/null; then
        echo -e "${RED}❌ Conda not found. Please install it first.${NC}"
        exit 1
    fi

    local ENV_NAME="simplicity"
    if conda env list | grep -q "^${ENV_NAME} "; then
        echo -e "${GREEN}✅ Conda env '${ENV_NAME}' already exists${NC}"
    else
        echo "📦 Creating conda env '${ENV_NAME}' with Python 3.13..."
        conda create -y -n "$ENV_NAME" python=3.13 pip
    fi

    echo "📦 Installing Simplicity..."
    # Run pip in the conda env
    conda run -n "$ENV_NAME" pip install -e "$SIMPLICITY_DIR" --quiet
    echo -e "${GREEN}✅ Simplicity installed${NC}"

    # Wrapper uses conda run
    SIMPLICITY_CMD="conda run -n simplicity simplicity"
}

# ── Run setup ─────────────────────────────────
if [ "$env_choice" = "2" ]; then
    setup_conda
else
    setup_venv
fi

# ── Create wrapper script ─────────────────────
if [ "$env_choice" = "2" ]; then
    # Conda wrapper
    cat > "$WRAPPER_BIN" << 'WRAPPER_EOF'
#!/usr/bin/env bash
# Simplicity wrapper (conda)
exec conda run -n simplicity simplicity "$@"
WRAPPER_EOF
else
    # Venv wrapper — resolves real path for portability
    cat > "$WRAPPER_BIN" << 'WRAPPER_EOF'
#!/usr/bin/env bash
# Simplicity wrapper (venv)
SIMPLICITY_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")")" && pwd)"
exec "$SIMPLICITY_DIR/.venv/bin/simplicity" "$@"
WRAPPER_EOF
fi
chmod +x "$WRAPPER_BIN"
echo -e "${GREEN}✅ Wrapper:  ${SIMPLICITY_DIR}/${WRAPPER_NAME}${NC}"

# ── Create config directories ─────────────────
mkdir -p "$CONFIG_DIR" "$TOOLS_DIR" "$WORKSPACE_DIR"
echo -e "${GREEN}✅ Config:   ${CONFIG_DIR}${NC}"
echo -e "${GREEN}✅ Workspace: ${WORKSPACE_DIR}${NC}"

# ── Copy example tools ────────────────────────
if [ -f "$SIMPLICITY_DIR/examples/get_datetime.py" ]; then
    cp "$SIMPLICITY_DIR/examples/get_datetime.py" "$TOOLS_DIR/" 2>/dev/null || true
    echo -e "${GREEN}✅ Example tool installed${NC}"
fi

# ── PATH setup ────────────────────────────────
echo ""
echo -e "  ┌─────────────────────────────────────────────┐"
echo -e "  │  ${GREEN}🌸 Simplicity installed successfully!${NC}     │"
echo -e "  └─────────────────────────────────────────────┘"
echo ""

SHELL_RC=""
case "$SHELL" in
    */zsh)   SHELL_RC="$HOME/.zshrc" ;;
    */bash)  SHELL_RC="$HOME/.bashrc" ;;
    */fish)  SHELL_RC="$HOME/.config/fish/config.fish" ;;
esac

echo -e "  ${BOLD}You can run it right now:${NC}"
echo -e "    ${CYAN}${WRAPPER_BIN} chat${NC}"
echo ""

if [ -n "$SHELL_RC" ]; then
    echo -e "  ${BOLD}For global access (just '${WRAPPER_NAME}'):${NC}"
    echo -e "    ${CYAN}echo 'export PATH=\"\$PATH:${SIMPLICITY_DIR}\"' >> ${SHELL_RC}${NC}"
    echo -e "    ${CYAN}source ${SHELL_RC}${NC}"
    echo ""
    echo -e "  After that, just run: ${CYAN}${WRAPPER_NAME} chat${NC}"
else
    echo -e "  ${BOLD}For global access, add this directory to your PATH${NC}"
fi
echo ""
echo -e "  ${BOLD}First-time setup:${NC}"
echo -e "    ${CYAN}${WRAPPER_BIN} auth${NC}"
echo ""
