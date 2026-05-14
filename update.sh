#!/usr/bin/env bash
# ───────────────────────────────────────────────
#  Simplicity Updater — pull latest + reinstall
# ───────────────────────────────────────────────
set -euo pipefail

SIMPLICITY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SIMPLICITY_DIR"

echo ""
echo "  .  .  .   S I M P L I C I T Y   U P D A T E R"
echo "  ------------------------------------------------"
echo ""

# ── Check git ──────────────────────────────────
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "ERROR: Not a git repository. This updater only works with git clones."
    exit 1
fi

# ── Save current HEAD ──────────────────────────
OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
echo "[OK] Current version: ${OLD_HEAD:0:8}"

# ── Stash local changes (keep user tweaks safe) ─
STASHED=0
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "... Stashing local changes..."
    git stash push -m "simplicity-update-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
    STASHED=1
fi

# ── Pull latest ────────────────────────────────
echo "... Pulling latest..."
git pull origin main --ff-only 2>&1 || {
    echo "WARNING: Could not fast-forward. Trying rebase..."
    git pull origin main --rebase 2>&1 || {
        echo "ERROR: Update failed. Your repo may have conflicts."
        echo "Run 'git status' to see what happened."
        if [ $STASHED -eq 1 ]; then
            echo "Your local changes are saved in 'git stash list'."
        fi
        exit 1
    }
}

NEW_HEAD=$(git rev-parse HEAD)
echo "[OK] Updated to: ${NEW_HEAD:0:8}"

# ── Show what's new ────────────────────────────
if [ "$OLD_HEAD" != "unknown" ] && [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
    echo ""
    echo "  Changes:"
    git log --oneline "${OLD_HEAD}..${NEW_HEAD}" 2>/dev/null | head -10 || true
    echo ""
fi

# ── Reinstall (pick up new deps) ───────────────
if [ -d "$SIMPLICITY_DIR/.venv" ]; then
    echo "... Reinstalling (venv)..."
    "$SIMPLICITY_DIR/.venv/bin/pip" install -e "$SIMPLICITY_DIR" --quiet
    echo "[OK] Package reinstalled"
elif command -v conda &>/dev/null && conda env list | grep -q "^simplicity "; then
    echo "... Reinstalling (conda)..."
    conda run -n simplicity pip install -e "$SIMPLICITY_DIR" --quiet
    echo "[OK] Package reinstalled"
else
    echo "... No venv/conda found — install first with ./install.sh"
fi

# ── Restore stashed changes ────────────────────
if [ $STASHED -eq 1 ]; then
    echo "... Restoring your local changes..."
    git stash pop 2>/dev/null || echo "  (could not auto-restore — check 'git stash list')"
fi

# ── User files preserved note ──────────────────
echo ""
echo "  . . . . . . . . . . . . . . . . . . . . . . . ."
echo "  .  Update complete!"
echo "  . . . . . . . . . . . . . . . . . . . . . . . ."
echo ""
echo "  Your files are safe:"
echo "    ~/.simplicity/config.json    (API key, settings)"
echo "    ~/.simplicity/tools/          (custom tools)"
echo "    workspace/                    (your files)"
echo ""
echo "  Run: ./simp chat"
echo ""
