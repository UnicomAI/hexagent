#!/usr/bin/env bash
# Create a DMG with custom background.
#
# Usage:
#   bash create-dmg.sh <arch>    # "arm64" or "x64"
#
# Why we don't use `create-dmg` directly:
#   `hdiutil create -srcfolder` fails with EBUSY on macOS 15 when the source
#   contains large Mach-O binaries (e.g. limactl with virtualization entitlements).
#   We work around this by:
#     1. Creating a blank writable DMG sized to fit the app  (avoids -srcfolder)
#     2. Mounting it and copying the app in manually
#     3. Adding an /Applications symlink for drag-to-install UX
#     4. Applying window layout via AppleScript (background, icon positions)
#     5. Converting to a compressed read-only UDZO DMG
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ELECTRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ARCH="${1:?Usage: create-dmg.sh <arm64|x64>}"

VERSION=$(node -p "require('$ELECTRON_DIR/package.json').version")
PRODUCT_NAME=$(node -p "require('$ELECTRON_DIR/package.json').build.productName")

if [ "$ARCH" = "arm64" ]; then
    APP_DIR="$ELECTRON_DIR/dist/mac-arm64"
else
    APP_DIR="$ELECTRON_DIR/dist/mac"
fi

APP_PATH="$APP_DIR/${PRODUCT_NAME}.app"
DMG_PATH="$ELECTRON_DIR/dist/${PRODUCT_NAME}-${VERSION}-mac-${ARCH}.dmg"
BACKGROUND="$ELECTRON_DIR/resources/background.png"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: $APP_PATH not found. Run electron-builder first."
    exit 1
fi

rm -f "$DMG_PATH"

# Clean up any stale writable working images left by a previous failed run.
# They stay mounted after a failure and cause the next hdiutil call to get EBUSY.
for stale in "$ELECTRON_DIR"/dist/rw.*.dmg; do
    [ -f "$stale" ] || continue
    echo "Cleaning up stale working image: $(basename "$stale")"
    hdiutil detach "$stale" -force 2>/dev/null || true
    rm -f "$stale"
done

echo "Creating DMG: $(basename "$DMG_PATH")"

# ── Temp files ───────────────────────────────────────────────────────────────
TMP_DIR=$(mktemp -d)
RW_DMG="$TMP_DIR/rw.dmg"
MOUNT_POINT=""
trap 'hdiutil detach "$MOUNT_POINT" -force 2>/dev/null || true; rm -rf "$TMP_DIR"' EXIT

# ── 1. Size: app + 20 MB headroom ────────────────────────────────────────────
APP_SIZE_MB=$(du -sm "$APP_PATH" | cut -f1)
DMG_SIZE_MB=$(( APP_SIZE_MB + 200 ))

# ── 2. Create a blank writable HFS+ image ────────────────────────────────────
hdiutil create -size "${DMG_SIZE_MB}m" \
    -fs HFS+ -volname "$PRODUCT_NAME" \
    "$RW_DMG"

# ── 3. Mount ──────────────────────────────────────────────────────────────────
# Eject any stale volume with the same name so there is no /Volumes conflict.
if [ -d "/Volumes/$PRODUCT_NAME" ]; then
    hdiutil detach "/Volumes/$PRODUCT_NAME" -force 2>/dev/null || true
fi
MOUNT_POINT=$(hdiutil attach "$RW_DMG" -readwrite -noverify -noautoopen \
    | awk '/\/Volumes\//{print $NF}')
echo "Mounted at: $MOUNT_POINT"

# ── 4. Copy app and add /Applications symlink ────────────────────────────────
ditto "$APP_PATH" "$MOUNT_POINT/${PRODUCT_NAME}.app"
ln -s /Applications "$MOUNT_POINT/Applications"

# ── 5. Copy background image ─────────────────────────────────────────────────
if [ -f "$BACKGROUND" ]; then
    mkdir -p "$MOUNT_POINT/.background"
    cp "$BACKGROUND" "$MOUNT_POINT/.background/background.png"
fi

# ── 6. Set Finder window layout via AppleScript ──────────────────────────────
if [ -f "$BACKGROUND" ]; then
osascript <<APPLESCRIPT
tell application "Finder"
    tell disk "$PRODUCT_NAME"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set bounds of container window to {200, 120, 740, 500}
        set theViewOptions to the icon view options of container window
        set arrangement of theViewOptions to not arranged
        set icon size of theViewOptions to 64
        set background picture of theViewOptions to file ".background:background.png"
        set position of item "${PRODUCT_NAME}.app" of container window to {135, 185}
        set position of item "Applications" of container window to {415, 185}
        close
        open
        update without registering applications
        delay 2
        close
    end tell
end tell
APPLESCRIPT
fi

# ── 7. Unmount ────────────────────────────────────────────────────────────────
hdiutil detach "$MOUNT_POINT" -force

# ── 8. Convert to compressed read-only DMG ───────────────────────────────────
hdiutil convert "$RW_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH"

echo "DMG created: $DMG_PATH"
