#!/bin/bash
# Playwright browsers + ImageMagick policy
set -euo pipefail

# Recover any broken dpkg/apt state from prior steps
dpkg --configure -a || true
apt-get install -y -f || true

# Install Playwright OS deps (apt) retry-wrapped
max_attempts=5
deps_ok=0
for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    emit 06_playwright progress "install-deps attempt $attempt/$max_attempts"
    if npx playwright install-deps chromium; then
        deps_ok=1
        break
    fi
    echo ">>> Retrying in 5s..."
    sleep 5
    dpkg --configure -a || true
    apt-get install -y -f || true
    apt-get update || true
done

if [[ $deps_ok -ne 1 ]]; then
    emit 06_playwright error "Failed to install Playwright system dependencies"
    exit 1
fi

# Download Chromium binary
emit 06_playwright progress "Downloading Chromium binary"
mirror_host="${OPENAGENT_PLAYWRIGHT_DOWNLOAD_HOST:-}"
browser_ok=0

# If bundled browsers are already present in the VM image, skip network download.
if find /opt/pw-browsers -type f \( -name "chrome-headless-shell" -o -name "chrome" \) 2>/dev/null | grep -q .; then
    emit 06_playwright progress "Bundled Playwright browser detected under /opt/pw-browsers, skipping download"
    browser_ok=1
fi

for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if [[ $browser_ok -eq 1 ]]; then
        break
    fi

    if [[ "${OPENAGENT_USE_CN_MIRRORS:-0}" == "1" && -n "$mirror_host" ]]; then
        emit 06_playwright progress "browser install attempt $attempt/$max_attempts (mirror)"
        if PLAYWRIGHT_DOWNLOAD_HOST="$mirror_host" \
           PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
           npx playwright install chromium; then
            browser_ok=1
            break
        fi
        emit 06_playwright progress "Mirror unavailable, retrying with official host"
    else
        emit 06_playwright progress "browser install attempt $attempt/$max_attempts"
    fi

    if env -u PLAYWRIGHT_DOWNLOAD_HOST PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers npx playwright install chromium; then
        browser_ok=1
        break
    fi
    echo ">>> Browser download attempt $attempt failed. Retrying in 5s..."
    sleep 5
done

if [[ $browser_ok -ne 1 ]]; then
    emit 06_playwright error "Failed to download Chromium browser"
    exit 1
fi

# Allow PDF operations in ImageMagick (if restricted)
if [[ -f /etc/ImageMagick-6/policy.xml ]] && \
   grep -q 'rights="none" pattern="PDF"' /etc/ImageMagick-6/policy.xml; then
    sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' \
        /etc/ImageMagick-6/policy.xml
    emit 06_playwright progress "ImageMagick PDF policy updated"
fi
