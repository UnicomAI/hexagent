#!/bin/bash
# NPM global packages
set -euo pipefail

emit 04_npm progress "Installing npm global packages"
npm install -g \
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

if [[ "$ARCH" == "x86_64" ]]; then
    emit 04_npm progress "Installing markdown-pdf (x86_64 only)"
    npm install -g markdown-pdf
fi
