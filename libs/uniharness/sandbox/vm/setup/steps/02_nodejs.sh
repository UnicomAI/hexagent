#!/bin/bash
# Node.js 22.x (NodeSource with tarball fallback)
set -euo pipefail

NODE_MAJOR=22

# --- Attempt 1: NodeSource apt repo (retried) ---
nodesource_ok=false
for attempt in 1 2 3; do
    emit 02_nodejs progress "NodeSource setup attempt $attempt/3"
    if curl -fsSL --retry 3 --retry-delay 5 \
        "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -; then
        if apt-get install -y nodejs; then
            nodesource_ok=true
            break
        fi
    fi
    echo ">>> Attempt $attempt failed. Retrying in $((attempt * 5))s..."
    sleep $((attempt * 5))
done

# --- Attempt 2: Official binary tarball ---
if [[ "$nodesource_ok" == false ]]; then
    emit 02_nodejs progress "Falling back to official binary tarball"
    apt-get remove -y nodejs npm 2>/dev/null || true

    case "$ARCH" in
        x86_64)  NODE_ARCH="x64" ;;
        aarch64) NODE_ARCH="arm64" ;;
        *)       echo "ERROR: Unsupported architecture: $ARCH"; exit 1 ;;
    esac

    NODE_VERSION=$(curl -fsSL --retry 3 \
        "https://nodejs.org/dist/latest-v${NODE_MAJOR}.x/" \
        | grep -oP 'node-v\K[0-9]+\.[0-9]+\.[0-9]+' | head -1)

    if [[ -z "$NODE_VERSION" ]]; then
        echo "ERROR: Could not determine latest Node.js ${NODE_MAJOR}.x version"
        exit 1
    fi

    TARBALL="node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz"
    URL="https://nodejs.org/dist/v${NODE_VERSION}/${TARBALL}"

    emit 02_nodejs progress "Downloading Node.js v${NODE_VERSION} for ${NODE_ARCH}"
    curl -fsSL --retry 3 --retry-delay 5 -o "/tmp/${TARBALL}" "$URL"
    tar -xJf "/tmp/${TARBALL}" -C /usr/local --strip-components=1
    rm -f "/tmp/${TARBALL}"
fi

# --- Verify ---
node --version
npm --version

if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm is not available after Node.js installation"
    exit 1
fi

emit 02_nodejs progress "Node.js $(node --version) with npm $(npm --version) installed"
