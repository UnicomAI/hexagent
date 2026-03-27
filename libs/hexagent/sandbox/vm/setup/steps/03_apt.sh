#!/bin/bash
# System packages (minimal baseline; install extras on demand)
set -uo pipefail
# No -e: apt_install handles its own errors with retries.

apt-get update

emit 03_apt progress "group=core_utils"
apt_install \
    bash coreutils wget curl git zip unzip jq tree ripgrep \
    file findutils patch sqlite3 || exit 1

emit 03_apt progress "group=build_tools"
apt_install build-essential pkg-config || exit 1

emit 03_apt progress "group=python"
apt_install python3 python3-dev python3-pip python3-venv pipx || exit 1

emit 03_apt progress "group=media"
apt_install imagemagick graphviz || exit 1

emit 03_apt progress "group=fonts"
apt_install \
    fonts-liberation2 fonts-dejavu || exit 1

emit 03_apt progress "group=dev_libs"
apt_install \
    libffi-dev zlib1g-dev libpng-dev libfreetype-dev libbz2-dev || exit 1

# Cleanup
emit 03_apt progress "Cleaning apt cache"
rm -rf /var/lib/apt/lists/*
apt-get autoremove -y
apt-get clean

# Verify nothing is broken
if ! dpkg --audit 2>/dev/null || dpkg -l | grep -q '^iF'; then
    echo ">>> WARNING: Some packages are in a broken state"
    dpkg -l | grep '^iF' || true
    exit 1
fi
