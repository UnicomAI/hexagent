#!/usr/bin/env bash
# Create a DMG with custom background using the `create-dmg` CLI tool.
#
# Usage:
#   bash create-dmg.sh <arch>    # "arm64" or "x64"
#
# Requires: brew install create-dmg
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ELECTRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ARCH="${1:?Usage: create-dmg.sh <arm64|x64>}"

VERSION=$(node -p "require('$ELECTRON_DIR/package.json').version")
PRODUCT_NAME=$(node -p "require('$ELECTRON_DIR/package.json').build.productName")

# electron-builder outputs to dist/mac-arm64/ or dist/mac/ (for x64)
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

# Remove previous DMG if it exists
rm -f "$DMG_PATH"

echo "Creating DMG: $(basename "$DMG_PATH")"

# Electron Framework uses hardlinks extensively. `du` counts hardlinked inodes
# once, causing create-dmg to underestimate the DMG size needed and fail with
# "No space left on device". Copy the app first to break hardlinks so that
# the size estimate matches the actual bytes written.
STAGING_DIR=$(mktemp -d)
APP_PATH_COPY="$STAGING_DIR/${PRODUCT_NAME}.app"
echo "Staging app (resolving hardlinks)..."
ditto "$APP_PATH" "$APP_PATH_COPY"

create-dmg \
    --volname "$PRODUCT_NAME" \
    --background "$BACKGROUND" \
    --window-size 540 380 \
    --icon-size 64 \
    --icon "$PRODUCT_NAME.app" 135 185 \
    --app-drop-link 415 185 \
    --no-internet-enable \
    "$DMG_PATH" \
    "$APP_PATH_COPY"

rm -rf "$STAGING_DIR"

echo "DMG created: $DMG_PATH"
