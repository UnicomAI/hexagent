#!/usr/bin/env bash
# Build the Python backend with PyInstaller.
#
# Usage:
#   bash build-backend.sh           # Build for current architecture
#   bash build-backend.sh arm64     # Build for arm64 (macOS)
#   bash build-backend.sh x64       # Build for x86_64 via Rosetta (macOS)
#   bash build-backend.sh universal # Build both and lipo merge
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ELECTRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$(cd "$ELECTRON_DIR/../backend" && pwd)"
TARGET_ARCH="${1:-}"

# ── PyInstaller flags (shared) ──
PYINSTALLER_ARGS=(
    --name openagent_api_server
    --onedir
    --noconfirm
    --clean
    --hidden-import uvicorn.logging
    --hidden-import uvicorn.loops
    --hidden-import uvicorn.loops.auto
    --hidden-import uvicorn.loops.asyncio
    --hidden-import uvicorn.protocols
    --hidden-import uvicorn.protocols.http
    --hidden-import uvicorn.protocols.http.auto
    --hidden-import uvicorn.protocols.http.h11_impl
    --hidden-import uvicorn.protocols.http.httptools_impl
    --hidden-import uvicorn.protocols.websockets
    --hidden-import uvicorn.protocols.websockets.auto
    --hidden-import uvicorn.protocols.websockets.wsproto_impl
    --hidden-import uvicorn.protocols.websockets.websockets_impl
    --hidden-import uvicorn.lifespan
    --hidden-import uvicorn.lifespan.on
    --hidden-import uvicorn.lifespan.off
    --collect-submodules openagent_api
    --collect-submodules openagent
    --collect-data openagent
    --add-data "skills:skills"
    --add-data "../../openagent/sandbox/vm:sandbox/vm"
    openagent_api/server.py
)

run_pyinstaller() {
    # Build for the current (native) architecture.
    echo "==> Installing PyInstaller..."
    cd "$BACKEND_DIR"
    uv pip install pyinstaller

    echo "==> Building backend with PyInstaller..."
    uv run pyinstaller "${PYINSTALLER_ARGS[@]}"

    echo "==> Copying dist to electron/backend_dist..."
    rm -rf "$ELECTRON_DIR/backend_dist"
    cp -r "$BACKEND_DIR/dist/openagent_api_server" "$ELECTRON_DIR/backend_dist"
}

run_pyinstaller_arch() {
    # Build for a specific architecture using `arch` to force the CPU mode.
    # Uses a separate venv per arch so native extensions match the target.
    local target_arch="$1"
    local arch_flag="$target_arch"

    if [ "$target_arch" = "x64" ] || [ "$target_arch" = "x86_64" ]; then
        arch_flag="x86_64"
        echo "==> Building x86_64 backend via Rosetta..."
        if ! arch -x86_64 true 2>/dev/null; then
            echo "ERROR: Rosetta 2 not installed. Install with: softwareupdate --install-rosetta"
            exit 1
        fi
    else
        echo "==> Building $target_arch backend..."
    fi

    cd "$BACKEND_DIR"

    # Use a per-arch venv so native extensions match the target architecture.
    local arch_venv="$BACKEND_DIR/.venv-${arch_flag}"
    export UV_PROJECT_ENVIRONMENT="$arch_venv"

    # Create fresh venv if it doesn't exist or architecture doesn't match
    if [ ! -d "$arch_venv" ]; then
        echo "==> Creating $arch_flag venv..."
        arch -"$arch_flag" uv venv "$arch_venv"
    fi

    echo "==> Installing dependencies for $arch_flag..."
    arch -"$arch_flag" uv sync
    uv pip install --python "$arch_venv/bin/python" pyinstaller

    echo "==> Running PyInstaller for $arch_flag..."
    arch -"$arch_flag" "$arch_venv/bin/python" -m PyInstaller "${PYINSTALLER_ARGS[@]}" --target-architecture "$arch_flag"

    unset UV_PROJECT_ENVIRONMENT

    rm -rf "$ELECTRON_DIR/backend_dist"
    cp -r "$BACKEND_DIR/dist/openagent_api_server" "$ELECTRON_DIR/backend_dist"
}

# ── Build based on target architecture ──
case "$TARGET_ARCH" in
    x64|x86_64)
        run_pyinstaller_arch x86_64
        ;;
    arm64)
        run_pyinstaller_arch arm64
        ;;
    "")
        run_pyinstaller
        ;;
    universal)
        echo "==> Building universal backend (arm64 + x86_64)..."
        # Build arm64 first
        run_pyinstaller_arch arm64
        mv "$ELECTRON_DIR/backend_dist" "$ELECTRON_DIR/backend_dist_arm64"
        # Build x64
        run_pyinstaller_arch x86_64
        mv "$ELECTRON_DIR/backend_dist" "$ELECTRON_DIR/backend_dist_x64"
        # Merge with lipo
        echo "==> Creating universal binary with lipo..."
        cp -r "$ELECTRON_DIR/backend_dist_arm64" "$ELECTRON_DIR/backend_dist"
        lipo -create \
            "$ELECTRON_DIR/backend_dist_arm64/openagent_api_server" \
            "$ELECTRON_DIR/backend_dist_x64/openagent_api_server" \
            -output "$ELECTRON_DIR/backend_dist/openagent_api_server"
        rm -rf "$ELECTRON_DIR/backend_dist_arm64" "$ELECTRON_DIR/backend_dist_x64"
        ;;
    *)
        echo "Usage: $0 [arm64|x64|universal]"
        exit 1
        ;;
esac

# ── Bundle Lima (macOS only) ──
if [ "$(uname)" = "Darwin" ]; then
    echo "==> Bundling Lima..."
    LIMA_PREFIX="$(brew --prefix lima 2>/dev/null || true)"
    if [ -z "$LIMA_PREFIX" ]; then
        LIMACTL_PATH="$(which limactl 2>/dev/null || true)"
        if [ -n "$LIMACTL_PATH" ]; then
            LIMACTL_REAL="$(readlink -f "$LIMACTL_PATH")"
            LIMA_PREFIX="$(dirname "$(dirname "$LIMACTL_REAL")")"
        fi
    fi

    if [ -n "$LIMA_PREFIX" ] && [ -f "$LIMA_PREFIX/bin/limactl" ]; then
        LIMA_DIST="$ELECTRON_DIR/lima_dist"
        rm -rf "$LIMA_DIST"
        mkdir -p "$LIMA_DIST/bin"
        cp "$LIMA_PREFIX/bin/limactl" "$LIMA_DIST/bin/"
        if [ -d "$LIMA_PREFIX/share/lima" ]; then
            mkdir -p "$LIMA_DIST/share"
            cp -r "$LIMA_PREFIX/share/lima" "$LIMA_DIST/share/"
        fi
        echo "==> Lima bundled from $LIMA_PREFIX"
    else
        echo "WARNING: limactl not found, Lima will not be bundled"
    fi
fi

echo "==> Backend build complete."
