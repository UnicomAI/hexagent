#!/bin/bash
# NPM global packages (minimal baseline; install extras on demand)
set -euo pipefail

if [[ "${OPENAGENT_USE_CN_MIRRORS:-0}" == "1" ]]; then
    emit 04_npm progress "Configuring npm registry mirror"
    npm config set registry "${OPENAGENT_NPM_REGISTRY}" >/dev/null 2>&1 || true
fi

emit 04_npm progress "Installing npm global packages"
npm install -g typescript tsx playwright
