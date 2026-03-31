#!/usr/bin/env bash
# Uninstall UniClaw-Work from macOS.
#
# Removes:
#   - UniClaw-Work.app from /Applications
#   - All app data, caches, logs, preferences (com.hexagent.app)
#   - The "hexagent" Lima VM instance and its disk image
#
# Usage:
#   bash uninstall-mac-hexagent.sh           # interactive (asks for confirmation)
#   bash uninstall-mac-hexagent.sh --force   # skip confirmation prompt
set -euo pipefail

APP_NAME="UniClaw-Work"
APP_ID="com.hexagent.app"
LIMA_INSTANCE="hexagent"
FORCE="${1:-}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { printf "${GREEN}done${NC}\n"; }
warn() { printf "${YELLOW}%s${NC}\n" "$*"; }

echo ""
echo "========================================"
echo "  $APP_NAME Uninstaller"
echo "========================================"
echo ""
echo "This will permanently delete:"
echo "  • /Applications/${APP_NAME}.app"
echo "  • ~/Library/Application Support/${APP_NAME} / hexagent"
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
    printf "Quitting %s... " "$APP_NAME"
    pkill -x "$APP_NAME" || true
    sleep 1
    ok
fi

# ── 2. Stop and delete the Lima VM instance ───────────────────────────────
if command -v limactl &>/dev/null; then
    if limactl list --format '{{.Name}}' 2>/dev/null | grep -qx "$LIMA_INSTANCE"; then
        STATUS=$(limactl list --format '{{.Name}} {{.Status}}' 2>/dev/null \
                   | awk -v name="$LIMA_INSTANCE" '$1==name{print $2}')
        if [ "$STATUS" = "Running" ]; then
            printf "Stopping Lima VM '%s'... " "$LIMA_INSTANCE"
            limactl stop "$LIMA_INSTANCE" 2>/dev/null || true
            ok
        fi
        printf "Deleting Lima VM '%s'... " "$LIMA_INSTANCE"
        limactl delete "$LIMA_INSTANCE" 2>/dev/null || true
        ok
    else
        warn "Lima VM '${LIMA_INSTANCE}' not found — skipping."
    fi
else
    warn "limactl not installed — skipping Lima VM removal."
fi

# Fallback: remove the Lima VM data directory directly if limactl left it behind
if [ -d "$HOME/.lima/$LIMA_INSTANCE" ]; then
    printf "Removing ~/.lima/%s... " "$LIMA_INSTANCE"
    rm -rf "$HOME/.lima/$LIMA_INSTANCE"
    ok
fi

# ── 3. Remove the .app bundle ─────────────────────────────────────────────
if [ -d "/Applications/${APP_NAME}.app" ]; then
    printf "Removing /Applications/%s.app... " "$APP_NAME"
    rm -rf "/Applications/${APP_NAME}.app"
    ok
else
    warn "/Applications/${APP_NAME}.app not found — skipping."
fi

# ── 4. Remove app data & caches ───────────────────────────────────────────
# Electron uses package.json "name" as the userData folder name ("hexagent"),
# which differs from productName ("UniClaw-Work"). Both are cleaned up.
PATHS=(
    "$HOME/Library/Application Support/${APP_NAME}"
    "$HOME/Library/Application Support/hexagent"
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
        printf "Removing %s... " "${p/$HOME/~}"
        rm -rf "$p"
        ok
    fi
done

echo ""
printf "${GREEN}========================================\n"
printf "  %s uninstalled successfully.\n" "$APP_NAME"
printf "========================================${NC}\n"
echo ""
