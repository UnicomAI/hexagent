# =============================================================================
# Agent CLI-based Computer Image
# =============================================================================
# CLI-based computer sandbox environment for agent execution. Includes
# development tools, document processing, data science packages, and
# browser automation.
#
# Base: Ubuntu 24.04 LTS (Noble Numbat)
#
# Build:
#   docker build -t openagent-sandbox .
#
# Run:
#   docker run -it --rm openagent-sandbox
# =============================================================================

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    IS_SANDBOX=yes

# =============================================================================
# Base Prerequisites
# =============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# Node.js 22.x
# =============================================================================
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# =============================================================================
# System Packages
# =============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    coreutils \
    wget \
    curl \
    git \
    zip \
    unzip \
    bzip2 \
    xz-utils \
    file \
    findutils \
    patch \
    perl \
    jq \
    tree \
    sqlite3 \
    ripgrep \
    netcat-openbsd \
    apt-transport-https \
    software-properties-common \
    build-essential \
    pkg-config \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    pipx \
    default-jre-headless \
    poppler-utils \
    qpdf \
    pdftk-java \
    wkhtmltopdf \
    ghostscript \
    pandoc \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    libreoffice-common \
    libreoffice-java-common \
    imagemagick \
    graphviz \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-eng \
    texlive-base \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-xetex \
    texlive-science \
    texlive-pictures \
    latexmk \
    fonts-liberation2 \
    fonts-dejavu \
    fonts-freefont-ttf \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-crosextra-caladea \
    fonts-crosextra-carlito \
    fonts-lmodern \
    fonts-texgyre \
    fonts-opensymbol \
    fonts-wqy-zenhei \
    fonts-ipafont-gothic \
    xvfb \
    x11-xkb-utils \
    xfonts-scalable \
    xfonts-cyrillic \
    xfonts-utils \
    libnss3 \
    libnss3-tools \
    libatk1.0-0t64 \
    libatk-bridge2.0-0t64 \
    libcups2t64 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2t64 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0t64 \
    libgtk-3-0t64 \
    libgtk-4-1 \
    libffi-dev \
    zlib1g-dev \
    libpng-dev \
    libfreetype-dev \
    libcairo2-dev \
    libglib2.0-dev \
    libbz2-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# =============================================================================
# NPM Global Packages
# =============================================================================
RUN npm install -g \
    docx@9 \
    pptxgenjs@4.0.1 \
    pdf-lib@1.17.1 \
    pdfjs-dist \
    marked \
    markdown-toc \
    markdownlint-cli \
    markdownlint-cli2 \
    remark-cli \
    remark-preset-lint-recommended \
    @mermaid-js/mermaid-cli \
    graphviz \
    react \
    react-dom \
    react-icons \
    typescript \
    ts-node \
    tsx \
    sharp \
    playwright

RUN if [ "$(uname -m)" = "x86_64" ]; then npm install -g markdown-pdf; fi

# =============================================================================
# Python Packages
# =============================================================================
RUN pip3 install --break-system-packages --no-cache-dir --ignore-installed blinker

RUN pip3 install --break-system-packages --no-cache-dir \
    # --- Core numeric / scientific ---
    numpy \
    pandas \
    scipy \
    sympy \
    # --- ML / CV ---
    scikit-learn \
    scikit-image \
    onnxruntime \
    opencv-python \
    opencv-contrib-python \
    opencv-python-headless \
    # --- Visualization ---
    matplotlib \
    seaborn \
    networkx \
    # --- Image / media ---
    pillow \
    imageio \
    imageio-ffmpeg \
    Wand \
    pytesseract \
    # --- PDF tools ---
    pdfplumber \
    pdfminer.six \
    pypdf \
    pikepdf \
    pdf2image \
    pdfkit \
    img2pdf \
    camelot-py \
    tabula-py \
    reportlab \
    pypdfium2 \
    pymupdf \
    # --- Office documents ---
    python-docx \
    python-pptx \
    openpyxl \
    xlsxwriter \
    odfpy \
    # --- Markdown / docs ---
    markitdown \
    markdownify \
    markdown \
    grip \
    mistune \
    markdown-it-py \
    marko \
    mkdocs \
    mkdocs-material \
    mkdocs-material-extensions \
    mkdocs-get-deps \
    pymdown-extensions \
    # --- Web / HTTP ---
    requests \
    beautifulsoup4 \
    lxml \
    Flask \
    httplib2 \
    # --- Automation / browser ---
    playwright \
    unoserver \
    pyoo \
    # --- System utilities ---
    uv \
    magika \
    click \
    colorama \
    coloredlogs \
    humanfriendly \
    tabulate \
    python-dotenv \
    psutil \
    watchdog \
    sounddevice \
    pycairo \
    graphviz \
    freetype-py \
    # --- Foundational / low-level ---
    attrs \
    bcrypt \
    jsonschema \
    python-magic \
    livereload \
    tornado \
    PyYAML \
    certifi \
    charset-normalizer \
    cryptography \
    defusedxml \
    idna \
    joblib \
    packaging \
    protobuf \
    python-dateutil \
    pytz \
    typing_extensions \
    urllib3

RUN if [ "$(uname -m)" = "x86_64" ]; then \
    pip3 install --break-system-packages --no-cache-dir "mediapipe>=0.10.32"; \
    fi

# =============================================================================
# Playwright Browsers + ImageMagick Policy
# =============================================================================
RUN npx playwright install-deps chromium && \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers npx playwright install chromium

RUN if [ -f /etc/ImageMagick-6/policy.xml ]; then \
    sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' /etc/ImageMagick-6/policy.xml; \
    fi

# =============================================================================
# Finalize
# =============================================================================
RUN ln -sf /usr/bin/python3 /usr/bin/python

RUN mkdir -p /mnt/uploads /mnt/outputs /mnt/skills

WORKDIR /home/openagent
USER root

CMD ["/bin/sh"]
