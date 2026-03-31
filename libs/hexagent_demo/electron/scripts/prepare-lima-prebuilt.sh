#!/usr/bin/env bash
# Export the local hexagent Lima VM as a prebuilt archive for offline packaging.
#
# The resulting archive lets a fresh install skip both the base image download
# and the full provisioning step; the BuildManager restores it directly.
#
# Output:
#   libs/hexagent/sandbox/vm/lima/prebuilt/hexagent-prebuilt.tar.gz
#
# Environment variables:
#   HEXAGENT_LIMA_INSTANCE         — Lima instance name (default: hexagent)
#   HEXAGENT_FORCE_REBUILD_LIMA_PREBUILT — "1" to re-export even if archive exists
#
# Usage:
#   bash prepare-lima-prebuilt.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HEXAGENT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PREBUILT_DIR="$HEXAGENT_ROOT/hexagent/sandbox/vm/lima/prebuilt"
PREBUILT_GZ="$PREBUILT_DIR/hexagent-prebuilt.tar.gz"
LEGACY_PREBUILT_GZ="$PREBUILT_DIR/openagent-prebuilt.tar.gz"

DISTRO_NAME="${HEXAGENT_LIMA_INSTANCE:-hexagent}"
FORCE_REBUILD="${HEXAGENT_FORCE_REBUILD_LIMA_PREBUILT:-0}"
LIMA_HOME="${LIMA_HOME:-$HOME/.lima}"

if [ "$(uname)" != "Darwin" ]; then
    echo "Skipping Lima prebuilt export: non-macOS environment."
    exit 0
fi

mkdir -p "$PREBUILT_DIR"

# Rename legacy archive if present
if [ ! -f "$PREBUILT_GZ" ] && [ -f "$LEGACY_PREBUILT_GZ" ]; then
    echo "==> Found legacy prebuilt archive name, renaming to hexagent-prebuilt.tar.gz ..."
    mv -f "$LEGACY_PREBUILT_GZ" "$PREBUILT_GZ"
fi

# Reuse existing archive unless force-rebuild is requested
if [ -f "$PREBUILT_GZ" ] && [ "$FORCE_REBUILD" != "1" ]; then
    size_mb=$(python3 -c "import os; print(f'{os.path.getsize(\"$PREBUILT_GZ\") / 1048576:.1f}')")
    echo "==> Reusing existing Lima prebuilt image: $PREBUILT_GZ (${size_mb} MB)"
    exit 0
fi

# Verify Lima is available
if ! command -v limactl >/dev/null 2>&1; then
    echo "ERROR: limactl not found. Install Lima first (brew install lima)." >&2
    exit 1
fi

INSTANCE_DIR="$LIMA_HOME/$DISTRO_NAME"

# Verify the instance exists and is runnable
echo "==> Verifying Lima instance '$DISTRO_NAME' can start..."
if ! limactl list --json 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        entry = json.loads(line)
    except:
        continue
    if entry.get('name') == '$DISTRO_NAME':
        sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
    echo "ERROR: Lima instance '$DISTRO_NAME' is not available." >&2
    echo "       Initialize the VM first, or provide an existing hexagent-prebuilt.tar.gz." >&2
    exit 1
fi

# Stop the instance (required for a clean snapshot)
echo "==> Stopping Lima instance '$DISTRO_NAME'..."
limactl stop "$DISTRO_NAME" 2>/dev/null || true

# Write metadata for path fixup on restore (different machines may have different LIMA_HOME)
echo "$LIMA_HOME" > "$INSTANCE_DIR/.prebuilt-lima-home"

# Remove the previous archive if rebuilding
if [ -f "$PREBUILT_GZ" ]; then
    rm -f "$PREBUILT_GZ"
fi

echo "==> Archiving Lima instance '$DISTRO_NAME' to $PREBUILT_GZ ..."
echo "    (This may take several minutes depending on disk size)"

# Archive the instance directory, excluding runtime-only files
tar -czf "$PREBUILT_GZ" \
    -C "$LIMA_HOME" \
    --exclude="${DISTRO_NAME}/*.sock" \
    --exclude="${DISTRO_NAME}/*.pid" \
    --exclude="${DISTRO_NAME}/.guest-agent.sock" \
    --exclude="${DISTRO_NAME}/logs" \
    --exclude="${DISTRO_NAME}/ssh.pub" \
    --exclude="${DISTRO_NAME}/ssh" \
    "$DISTRO_NAME"

if [ ! -f "$PREBUILT_GZ" ]; then
    echo "ERROR: Archive was not created: $PREBUILT_GZ" >&2
    exit 1
fi

size_mb=$(python3 -c "import os; print(f'{os.path.getsize(\"$PREBUILT_GZ\") / 1048576:.1f}')")
echo "==> Lima prebuilt image ready: $PREBUILT_GZ (${size_mb} MB)"
