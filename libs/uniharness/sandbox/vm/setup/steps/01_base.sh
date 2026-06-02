#!/bin/bash
# Base prerequisites
set -euo pipefail

emit 01_base progress "Running apt-get update"
apt-get update

emit 01_base progress "Installing ca-certificates, curl, gnupg"
apt_install ca-certificates curl gnupg
