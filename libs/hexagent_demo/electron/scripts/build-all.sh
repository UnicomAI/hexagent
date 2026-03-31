#!/usr/bin/env bash
# Build UniClaw desktop app for specified platforms.
#
# Usage:
#   bash build-all.sh                    # macOS arm64 (default)
#   bash build-all.sh mac-arm64          # macOS arm64
#   bash build-all.sh mac-x64            # macOS x86_64 (via Rosetta)
#   bash build-all.sh mac-all            # macOS arm64 + x64 (two DMGs)
#   bash build-all.sh win                # Windows x64 (must run on Windows)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ELECTRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="${1:-mac-arm64}"

echo "========================================="
echo "  UniClaw Desktop 鈥?Build ($TARGET)"
echo "========================================="

# ---------------------------------------------------------------------------
# Build flags — control runtime behaviour of the packaged app.
# Override via environment variable before running this script, e.g.:
#   CLEAR_USER_DATA_ON_START=false bash build-all.sh
#
#   CLEAR_USER_DATA_ON_START=true  — wipe ~/Library/Application Support/…
#                                    on every app start (default: dev builds)
#   CLEAR_USER_DATA_ON_START=false — preserve user data across restarts
#                                    (set this for production/release builds)
# ---------------------------------------------------------------------------
CLEAR_USER_DATA_ON_START="${CLEAR_USER_DATA_ON_START:-true}"

echo "Build flags: CLEAR_USER_DATA_ON_START=$CLEAR_USER_DATA_ON_START"
cat > "$ELECTRON_DIR/build_flags.json" << EOF
{
  "clear_user_data_on_start": $CLEAR_USER_DATA_ON_START
}
EOF

echo ""
echo "[1/3] Building frontend..."
bash "$SCRIPT_DIR/build-frontend.sh"

echo ""
echo "[2/3] Installing electron dependencies..."
cd "$ELECTRON_DIR"
ELECTRON_MIRROR="${ELECTRON_MIRROR:-}" npm install

case "$TARGET" in
    mac-arm64)
        echo ""
        echo "[2.5/4] Building backend (arm64)..."
        bash "$SCRIPT_DIR/build-backend.sh" arm64

        echo ""
        echo "[3/4] Packaging macOS arm64 app..."
        npx electron-builder --mac --arm64

        echo ""
        echo "[4/4] Creating DMG..."
        bash "$SCRIPT_DIR/create-dmg.sh" arm64
        ;;
    mac-x64)
        echo ""
        echo "[2.5/4] Building backend (x64)..."
        bash "$SCRIPT_DIR/build-backend.sh" x64

        echo ""
        echo "[3/4] Packaging macOS x64 app..."
        npx electron-builder --mac --x64

        echo ""
        echo "[4/4] Creating DMG..."
        bash "$SCRIPT_DIR/create-dmg.sh" x64
        ;;
    mac-all)
        # Build arm64 first
        echo ""
        echo "[2.5/4] Building backend (arm64)..."
        bash "$SCRIPT_DIR/build-backend.sh" arm64

        echo ""
        echo "[3a/4] Packaging macOS arm64 app..."
        npx electron-builder --mac --arm64

        echo ""
        echo "[4a/4] Creating arm64 DMG..."
        bash "$SCRIPT_DIR/create-dmg.sh" arm64

        # Then build x64
        echo ""
        echo "[2.5/4] Building backend (x64)..."
        bash "$SCRIPT_DIR/build-backend.sh" x64

        echo ""
        echo "[3b/4] Packaging macOS x64 app..."
        npx electron-builder --mac --x64

        echo ""
        echo "[4b/4] Creating x64 DMG..."
        bash "$SCRIPT_DIR/create-dmg.sh" x64
        ;;
    win)
        echo ""
        echo "[2.5/3] Building backend..."
        bash "$SCRIPT_DIR/build-backend.sh"

        echo ""
        echo "[3/3] Packaging Windows x64 installer..."
        npx electron-builder --win --x64
        ;;
    *)
        echo "Unknown target: $TARGET"
        echo "Usage: $0 [mac-arm64|mac-x64|mac-all|win]"
        exit 1
        ;;
esac

echo ""
echo "========================================="
echo "  Build complete! Output in dist/"
echo "========================================="
ls -lh "$ELECTRON_DIR/dist/"*.{dmg,exe,blockmap} 2>/dev/null || true

