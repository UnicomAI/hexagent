#!/bin/bash
# Python packages (11 batches)
set -uo pipefail
# No -e: pip_install handles its own retries.

# Preflight: fix blinker conflict with system Flask
emit 05_pip progress "Preflight: fixing blinker"
pip3 install --break-system-packages --timeout 120 --ignore-installed blinker

emit 05_pip progress "Batch 1/11 — Core numeric (4 packages)"
pip_install numpy pandas scipy sympy

emit 05_pip progress "Batch 2/11 — ML / CV (3 packages)"
pip_install scikit-learn scikit-image onnxruntime

emit 05_pip progress "Batch 3/11 — ML / CV OpenCV (3 packages)"
pip_install opencv-python opencv-contrib-python opencv-python-headless

emit 05_pip progress "Batch 4/11 — Visualization (3 packages)"
pip_install matplotlib seaborn networkx

emit 05_pip progress "Batch 5/11 — Image / media (5 packages)"
pip_install pillow imageio imageio-ffmpeg Wand pytesseract

emit 05_pip progress "Batch 6/11 — PDF tools (11 packages)"
pip_install \
    pdfplumber pdfminer.six pypdf pikepdf pdf2image pdfkit \
    img2pdf camelot-py tabula-py reportlab pypdfium2 pymupdf

emit 05_pip progress "Batch 7/11 — Office documents (5 packages)"
pip_install python-docx python-pptx openpyxl xlsxwriter odfpy

emit 05_pip progress "Batch 8/11 — Markdown / docs (11 packages)"
pip_install \
    markitdown markdownify markdown grip mistune markdown-it-py \
    marko mkdocs mkdocs-material mkdocs-material-extensions \
    mkdocs-get-deps pymdown-extensions

emit 05_pip progress "Batch 9/11 — Web / HTTP (5 packages)"
pip_install requests beautifulsoup4 lxml Flask httplib2

emit 05_pip progress "Batch 10/11 — Automation / browser (3 packages)"
pip_install playwright unoserver pyoo

emit 05_pip progress "Batch 11/11 — System utilities (14 packages)"
pip_install \
    uv magika click colorama coloredlogs humanfriendly tabulate \
    python-dotenv psutil watchdog sounddevice pycairo graphviz freetype-py

# Foundational (many already installed as transitive deps — pip will no-op)
emit 05_pip progress "Foundational / low-level (17 packages)"
pip_install \
    attrs bcrypt jsonschema python-magic livereload tornado PyYAML \
    certifi charset-normalizer cryptography defusedxml idna joblib \
    packaging protobuf python-dateutil pytz typing_extensions urllib3

# Platform-specific
if [[ "$ARCH" == "x86_64" ]]; then
    emit 05_pip progress "Platform-specific: mediapipe (x86_64 only)"
    pip_install "mediapipe>=0.10.32"
fi

# Cleanup
emit 05_pip progress "Cleaning pip cache"
pip3 cache purge
rm -rf /root/.cache/pip /tmp/pip-* 2>/dev/null || true
