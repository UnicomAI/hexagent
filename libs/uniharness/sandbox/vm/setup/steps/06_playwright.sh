#!/bin/bash
# Playwright browsers + ImageMagick policy
set -euo pipefail

# Recover any broken dpkg/apt state from prior steps
dpkg --configure -a || true
apt-get install -y -f || true

# Install Playwright OS deps (apt) — retry-wrapped
max_attempts=5
for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    emit 06_playwright progress "install-deps attempt $attempt/$max_attempts"
    if npx playwright install-deps chromium; then
        break
    fi
    echo ">>> Retrying in 5s..."
    sleep 5
    dpkg --configure -a || true
    apt-get install -y -f || true
    apt-get update || true
done

# Download Chromium binary
emit 06_playwright progress "Downloading Chromium binary"
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers npx playwright install chromium

# Allow PDF operations in ImageMagick (if restricted)
if [[ -f /etc/ImageMagick-6/policy.xml ]] && \
   grep -q 'rights="none" pattern="PDF"' /etc/ImageMagick-6/policy.xml; then
    sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' \
        /etc/ImageMagick-6/policy.xml
    emit 06_playwright progress "ImageMagick PDF policy updated"
fi
