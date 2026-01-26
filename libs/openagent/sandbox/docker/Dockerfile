# =============================================================================
# Agent CLI-based Computer Image
# =============================================================================
# This Dockerfile defines a CLI-based computer sandbox environment purpose-built
# for agent execution. It includes development tools, document processing
# capabilities, data science packages, and browser automation tools.
#
# Base: Ubuntu 24.04 LTS (Noble Numbat)
# Architecture: amd64/x86_64
#
# Build:
#   docker build -t openagent-sandbox .
#
# Run:
#   docker run -it --rm openagent-sandbox
# =============================================================================

FROM ubuntu:24.04

# =============================================================================
# Environment Configuration
# =============================================================================
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    IS_SANDBOX=yes

# =============================================================================
# Base Prerequisites (needed for subsequent downloads)
# =============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# Node.js 22.x from NodeSource
# =============================================================================
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# =============================================================================
# System Packages
# =============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core utilities
    bash \
    coreutils \
    wget \
    git \
    apt-transport-https \
    software-properties-common \
    # Build essentials (includes gcc, g++, make)
    build-essential \
    pkg-config \
    # Python
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    pipx \
    # Java
    default-jre-headless \
    # Compression
    zip \
    unzip \
    bzip2 \
    xz-utils \
    # Text processing
    perl \
    patch \
    # Network
    netcat-openbsd \
    # File utilities
    file \
    findutils \
    # PDF tools
    poppler-utils \
    qpdf \
    pdftk-java \
    wkhtmltopdf \
    # Document conversion
    pandoc \
    # LibreOffice
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    libreoffice-draw \
    libreoffice-base-core \
    libreoffice-common \
    libreoffice-java-common \
    # Image processing
    imagemagick \
    libmagickwand-dev \
    # OCR
    tesseract-ocr \
    tesseract-ocr-eng \
    # Diagrams
    graphviz \
    # LaTeX
    texlive-base \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-xetex \
    texlive-science \
    texlive-pictures \
    latexmk \
    # Multimedia
    ffmpeg \
    # Fonts
    fonts-liberation \
    fonts-liberation2 \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-dejavu-mono \
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
    # X Virtual Framebuffer
    xvfb \
    x11-xkb-utils \
    xfonts-base \
    xfonts-scalable \
    xfonts-cyrillic \
    xfonts-utils \
    # Libraries for Playwright/Chrome
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
    # Development libraries for Python C extensions
    libffi-dev \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    libpq-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libwebp-dev \
    libopenjp2-7-dev \
    libfreetype-dev \
    libfontconfig1-dev \
    libcairo2-dev \
    libpango1.0-dev \
    libglib2.0-dev \
    libxml2-dev \
    libxslt1-dev \
    libhdf5-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# =============================================================================
# NPM Configuration and Global Packages
# =============================================================================
RUN npm config set prefix /home/openagent/.npm-global && \
    npm install -g \
    docx@9.5.1 \
    pptxgenjs@4.0.1 \
    pdf-lib@1.17.1 \
    pdfjs-dist \
    marked \
    markdown-pdf \
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
    playwright && \
    echo "PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers" >> /home/openagent/.npmrc

# =============================================================================
# Python Packages
# =============================================================================
RUN pip3 install --break-system-packages --no-cache-dir --ignore-installed \
    numpy \
    pandas \
    scipy \
    scikit-learn \
    scikit-image \
    matplotlib \
    seaborn \
    networkx \
    sympy \
    jax \
    jaxlib \
    onnxruntime \
    mediapipe \
    pillow \
    opencv-python \
    opencv-contrib-python \
    opencv-python-headless \
    imageio \
    imageio-ffmpeg \
    Wand \
    pdfplumber \
    pdfminer.six \
    pypdf \
    pikepdf \
    pdf2image \
    pdfkit \
    img2pdf \
    "camelot-py[cv]" \
    reportlab \
    pypdfium2 \
    python-docx \
    python-pptx \
    openpyxl \
    xlsxwriter \
    odfpy \
    markitdown \
    markdownify \
    requests \
    beautifulsoup4 \
    lxml \
    Flask \
    httplib2 \
    mistune \
    markdown-it-py \
    marko \
    mkdocs \
    mkdocs-material \
    mkdocs-material-extensions \
    mkdocs-get-deps \
    pymdown-extensions \
    click \
    colorama \
    coloredlogs \
    humanfriendly \
    tabulate \
    tqdm \
    python-dotenv \
    psutil \
    watchdog \
    pytesseract \
    playwright \
    unoserver \
    pyoo \
    pycairo \
    graphviz \
    freetype-py \
    attrs \
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

# =============================================================================
# Runtime Environment Configuration
# =============================================================================
ENV PATH=/home/openagent/.npm-global/bin:/home/openagent/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PIP_CACHE_DIR=/home/openagent/.cache/pip

# =============================================================================
# Install Playwright browsers (shared between Node.js and Python)
# =============================================================================
RUN npx playwright install chromium && \
    npx playwright install-deps chromium

# =============================================================================
# ImageMagick Policy (allow PDF operations)
# =============================================================================
RUN if [ -f /etc/ImageMagick-6/policy.xml ]; then \
    sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' /etc/ImageMagick-6/policy.xml; \
    fi

# =============================================================================
# CUSTOMIZATION: Mount Points
# =============================================================================
RUN mkdir -p \
    /mnt/uploads \
    /mnt/outputs \
    /mnt/skills

# =============================================================================
# Working Directory (running as root)
# =============================================================================
WORKDIR /home/openagent
USER root

# =============================================================================
# Default command
# =============================================================================
CMD ["/bin/sh"]