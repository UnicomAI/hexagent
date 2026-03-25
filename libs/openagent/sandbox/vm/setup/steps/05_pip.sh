#!/bin/bash
# Python packages (minimal baseline; install extras on demand)
set -euo pipefail

emit 05_pip progress "Core data & visualization"
pip_install numpy pandas matplotlib pillow

emit 05_pip progress "Web & HTTP"
pip_install requests beautifulsoup4 lxml

emit 05_pip progress "Utilities"
pip_install \
    uv click pyyaml python-dotenv tabulate

# Cleanup
emit 05_pip progress "Cleaning pip cache"
pip3 cache purge
rm -rf /root/.cache/pip /tmp/pip-* 2>/dev/null || true
