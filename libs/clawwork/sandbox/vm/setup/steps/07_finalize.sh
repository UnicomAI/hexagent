#!/bin/bash
# Symlinks and session directory
set -euo pipefail

emit 07_finalize progress "Creating python symlink"
ln -sf /usr/bin/python3 /usr/bin/python

emit 07_finalize progress "Creating /sessions directory"
mkdir -p /sessions
chmod 755 /sessions
