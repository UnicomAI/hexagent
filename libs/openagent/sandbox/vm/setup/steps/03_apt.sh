#!/bin/bash
# System packages (core utils, Python, Java, PDF, LaTeX, fonts, etc.)
set -uo pipefail
# No -e: apt_install handles its own errors with retries.

apt-get update

emit 03_apt progress "group=core_utils (17 packages)"
apt_install \
    bash coreutils wget curl git zip unzip bzip2 xz-utils \
    file findutils patch perl jq tree sqlite3 ripgrep \
    netcat-openbsd apt-transport-https software-properties-common

emit 03_apt progress "group=build_tools (2 packages)"
apt_install build-essential pkg-config

emit 03_apt progress "group=python (5 packages)"
apt_install python3 python3-dev python3-pip python3-venv pipx

emit 03_apt progress "group=java (1 package)"
apt_install default-jre-headless

emit 03_apt progress "group=pdf_tools (5 packages)"
apt_install poppler-utils qpdf pdftk-java wkhtmltopdf ghostscript

emit 03_apt progress "group=pandoc (1 package)"
apt_install pandoc

emit 03_apt progress "group=libreoffice (5 packages)"
apt_install \
    libreoffice-writer libreoffice-calc libreoffice-impress \
    libreoffice-common libreoffice-java-common

emit 03_apt progress "group=media (3 packages)"
apt_install imagemagick graphviz ffmpeg

emit 03_apt progress "group=ocr (2 packages)"
apt_install tesseract-ocr tesseract-ocr-eng

emit 03_apt progress "group=latex (9 packages)"
apt_install \
    texlive-base texlive-latex-base texlive-latex-recommended \
    texlive-latex-extra texlive-fonts-recommended texlive-xetex \
    texlive-science texlive-pictures latexmk

emit 03_apt progress "group=fonts (12 packages)"
apt_install \
    fonts-liberation2 fonts-dejavu fonts-freefont-ttf \
    fonts-noto-cjk fonts-noto-color-emoji \
    fonts-crosextra-caladea fonts-crosextra-carlito \
    fonts-lmodern fonts-texgyre fonts-opensymbol \
    fonts-wqy-zenhei fonts-ipafont-gothic

emit 03_apt progress "group=x11_display (5 packages)"
apt_install \
    xvfb x11-xkb-utils xfonts-scalable xfonts-cyrillic xfonts-utils

emit 03_apt progress "group=browser_libs (17 packages)"
apt_install \
    libnss3 libnss3-tools libatk1.0-0t64 libatk-bridge2.0-0t64 \
    libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2t64 libpango-1.0-0 \
    libcairo2 libatspi2.0-0t64 libgtk-3-0t64 libgtk-4-1

emit 03_apt progress "group=dev_libs (7 packages)"
apt_install \
    libffi-dev zlib1g-dev libpng-dev libfreetype-dev libcairo2-dev \
    libglib2.0-dev libbz2-dev

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
