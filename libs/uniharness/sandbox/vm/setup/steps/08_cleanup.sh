#!/bin/bash
# Cache cleanup to minimize image size
set -euo pipefail

emit 08_cleanup progress "Cleaning apt cache"
apt-get clean

emit 08_cleanup progress "Removing temporary files"
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* 2>/dev/null || true
rm -rf /root/.cache /root/.npm/_cacache 2>/dev/null || true
