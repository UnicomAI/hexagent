#!/usr/bin/env bash
# Uninstall HexAgent from macOS.
#
# Removes:
#   - HexAgent.app from /Applications
#   - All app data, caches, logs, preferences (com.hexagent.app)
#   - The "hexagent" Lima VM instance and its disk image
#
# Usage:
#   bash uninstall-mac.sh           # interactive (asks for confirmation)
#   bash uninstall-mac.sh --force   # skip confirmation prompt
set -euo pipefail

APP_NAME="HexAgent"
APP_ID="com.hexagent.app"
LIMA_INSTANCE="hexagent"
FORCE="${1:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "========================================"
echo "  $APP_NAME Uninstaller"
echo "========================================"
echo ""
echo "This will permanently delete:"
echo "  • /Applications/${APP_NAME}.app"
echo "  • ~/Library/Application Support/${APP_NAME}"
echo "  • ~/Library/Caches/${APP_ID}"
echo "  • ~/Library/Logs/${APP_NAME}"
echo "  • ~/Library/Preferences/${APP_ID}.plist"
echo "  • ~/Library/Saved Application State/${APP_ID}.savedState"
echo "  • Lima VM instance: ${LIMA_INSTANCE}  (~/.lima/${LIMA_INSTANCE})"
echo ""

if [ "$FORCE" != "--force" ]; then
    read -r -p "Continue? [y/N] " confirm
    case "$confirm" in
        [yY][eE][sS]|[yY]) ;;
        *)
            echo "Cancelled."
            exit 0
            ;;
    esac
fi

echo ""

# ── 1. Quit the app if running ─────────────────────────────────────────────
if pgrep -x "$APP_NAME" &>/dev/null; then
    echo -n "Quitting ${APP_NAME}... "
    pkill -x "$APP_NAME" || true
    sleep 1
    echo -e "${GREEN}done${NC}"
fi

# ── 2. Stop and delete the Lima VM ────────────────────────────────────────
if command -v limactl &>/dev/null; then
    if limactl list --format '{{.Name}}' 2>/dev/null | grep -qx "$LIMA_INSTANCE"; then
        STATUS=$(limactl list --format '{{.Name}} {{.Status}}' 2>/dev/null \
                   | awk -v name="$LIMA_INSTANCE" '$1==name{print $2}')
        if [ "$STATUS" = "Running" ]; then
            echo -n "Stopping Lima VM '${LIMA_INSTANCE}'... "
            limactl stop "$LIMA_INSTANCE" 2>/dev/null || true
            echo -e "${GREEN}done${NC}"
        fi
        echo -n "Deleting Lima VM '${LIMA_INSTANCE}'... "
        limactl delete "$LIMA_INSTANCE" 2>/dev/null || true
        echo -e "${GREEN}done${NC}"
    else
        echo -e "${YELLOW}Lima VM '${LIMA_INSTANCE}' not found — skipping.${NC}"
    fi
else
    echo -e "${YELLOW}limactl not installed — skipping Lima VM removal.${NC}"
fi

# Fallback: remove the Lima data directory directly if limactl left it behind
if [ -d "$HOME/.lima/$LIMA_INSTANCE" ]; then
    echo -n "Removing ~/.lima/${LIMA_INSTANCE}... "
    rm -rf "$HOME/.lima/$LIMA_INSTANCE"
    echo -e "${GREEN}done${NC}"
fi

# ── 3. Remove the .app bundle ─────────────────────────────────────────────
if [ -d "/Applications/${APP_NAME}.app" ]; then
    echo -n "Removing /Applications/${APP_NAME}.app... "
    rm -rf "/Applications/${APP_NAME}.app"
    echo -e "${GREEN}done${NC}"
else
    echo -e "${YELLOW}/Applications/${APP_NAME}.app not found — skipping.${NC}"
fi

# ── 4. Remove app data & caches ───────────────────────────────────────────
declare -a PATHS=(
    "$HOME/Library/Application Support/${APP_NAME}"
    "$HOME/Library/Caches/${APP_ID}"
    "$HOME/Library/Caches/${APP_NAME}"
    "$HOME/Library/Logs/${APP_NAME}"
    "$HOME/Library/Preferences/${APP_ID}.plist"
    "$HOME/Library/Saved Application State/${APP_ID}.savedState"
    "$HOME/Library/WebKit/${APP_ID}"
    "$HOME/Library/HTTPStorages/${APP_ID}"
)

for p in "${PATHS[@]}"; do
    if [ -e "$p" ]; then
        echo -n "Removing ${p/$HOME/~}... "
        rm -rf "$p"
        echo -e "${GREEN}done${NC}"
    fi
done

echo ""
echo -e "${GREEN}========================================"
echo "  HexAgent uninstalled successfully."
echo -e "========================================${NC}"
echo ""
