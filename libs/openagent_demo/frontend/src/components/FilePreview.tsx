/**
 * File preview panel — shows a preview of a file presented by the PresentToUser tool.
 *
 * Renders in place of (or alongside) the RightPanel when a user clicks a file card.
 * Supports image, SVG, PDF, markdown, HTML, CSV, JSON, XML, code, office docs,
 * audio, video, and plain text previews.
 */

import { useState, useEffect, useLayoutEffect, useMemo, useCallback, useRef, memo, createElement, lazy, Suspense } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import * as UTIF from "utif2";
import { useSyntaxTheme } from "../hooks/useSyntaxTheme";
import { X, Download, Copy, Check, File, Eye, CodeXml, Loader2 } from "lucide-react";
import { useAppContext } from "../store";
import Markdown from "./Markdown";

const LazyPdfViewer = lazy(() => import("./PdfViewer"));
const LazyDocxViewer = lazy(() => import("./DocxViewer"));
const LazyXlsxViewer = lazy(() => import("./XlsxViewer"));
const LazyPptxViewer = lazy(() => import("./PptxViewer"));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function basename(path: string): string {
  return path.split("/").pop() || path;
}

function extname(path: string): string {
  const base = basename(path);
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(dot).toLowerCase() : "";
}

// ---------------------------------------------------------------------------
// Category detection
// ---------------------------------------------------------------------------

type Category =
  | "image"
  | "svg"
  | "tiff"
  | "pdf"
  | "markdown"
  | "html"
  | "csv"
  | "json"
  | "xml"
  | "code"
  | "docx"
  | "xlsx"
  | "pptx"
  | "audio"
  | "video"
  | "text"
  | "unsupported";

const EXT_TO_LANGUAGE: Record<string, string> = {
  ".py": "python",
  ".js": "javascript",
  ".jsx": "jsx",
  ".ts": "typescript",
  ".tsx": "tsx",
  ".go": "go",
  ".rs": "rust",
  ".rb": "ruby",
  ".java": "java",
  ".kt": "kotlin",
  ".kts": "kotlin",
  ".scala": "scala",
  ".c": "c",
  ".h": "c",
  ".cpp": "cpp",
  ".cxx": "cpp",
  ".cc": "cpp",
  ".hpp": "cpp",
  ".cs": "csharp",
  ".swift": "swift",
  ".m": "objectivec",
  ".php": "php",
  ".r": "r",
  ".R": "r",
  ".lua": "lua",
  ".pl": "perl",
  ".pm": "perl",
  ".sh": "bash",
  ".bash": "bash",
  ".zsh": "bash",
  ".fish": "bash",
  ".ps1": "powershell",
  ".sql": "sql",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".toml": "toml",
  ".ini": "ini",
  ".cfg": "ini",
  ".conf": "nginx",
  ".dockerfile": "docker",
  ".tf": "hcl",
  ".hcl": "hcl",
  ".proto": "protobuf",
  ".graphql": "graphql",
  ".gql": "graphql",
  ".dart": "dart",
  ".ex": "elixir",
  ".exs": "elixir",
  ".erl": "erlang",
  ".hs": "haskell",
  ".ml": "ocaml",
  ".mli": "ocaml",
  ".clj": "clojure",
  ".vim": "vim",
  ".css": "css",
  ".scss": "scss",
  ".sass": "sass",
  ".less": "less",
  ".makefile": "makefile",
  ".cmake": "cmake",
};


function detectCategory(mimeType: string, path: string): Category {
  const ext = extname(path);

  // SVG before generic image
  if (mimeType === "image/svg+xml" || ext === ".svg") return "svg";
  // TIFF — needs client-side decoding for cross-browser support
  if (mimeType === "image/tiff" || ext === ".tif" || ext === ".tiff") return "tiff";
  if (mimeType.startsWith("image/")) return "image";

  if (mimeType === "application/pdf" || ext === ".pdf") return "pdf";

  if (mimeType === "text/markdown" || ext === ".md" || ext === ".mdx") return "markdown";
  if (mimeType === "text/html" || ext === ".html" || ext === ".htm") return "html";
  if (mimeType === "text/csv" || ext === ".csv") return "csv";
  if (mimeType === "application/json" || ext === ".json") return "json";
  if (
    mimeType === "application/xml" ||
    mimeType === "text/xml" ||
    ext === ".xml"
  )
    return "xml";

  // Office — format-specific strategies
  if (ext === ".docx" || mimeType === "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return "docx";
  if (ext === ".xlsx" || mimeType === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return "xlsx";
  if (ext === ".pptx" || mimeType === "application/vnd.openxmlformats-officedocument.presentationml.presentation")
    return "pptx";

  if (mimeType.startsWith("audio/")) return "audio";

  // Formats not previewable in-browser — fall through to unsupported
  const UNSUPPORTED_EXTS = new Set([
    ".avi", ".wmv", ".flv", ".mkv",
    ".odp", ".ods", ".odt", ".rtf",
    ".doc", ".ppt", ".xls",
  ]);
  if (UNSUPPORTED_EXTS.has(ext)) return "unsupported";
  if (mimeType.startsWith("video/")) return "video";

  // Code — check extension map
  if (EXT_TO_LANGUAGE[ext]) return "code";

  // Makefile / Dockerfile without typical extensions
  const base = basename(path).toLowerCase();
  if (base === "makefile" || base === "dockerfile" || base === "jenkinsfile")
    return "code";

  // Generic text fallback
  if (
    mimeType.startsWith("text/") ||
    mimeType === "application/javascript" ||
    mimeType === "application/x-sh"
  )
    return "text";

  return "unsupported";
}

function languageForPath(path: string): string {
  const ext = extname(path);
  if (EXT_TO_LANGUAGE[ext]) return EXT_TO_LANGUAGE[ext];
  const base = basename(path).toLowerCase();
  if (base === "makefile") return "makefile";
  if (base === "dockerfile") return "docker";
  if (base === "jenkinsfile") return "groovy";
  return "text";
}

// ---------------------------------------------------------------------------
// useTextContent hook
// ---------------------------------------------------------------------------

function useTextContent(url: string) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setContent(null);
    setError(false);
    setLoading(true);
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch");
        return res.text();
      })
      .then((text) => {
        if (!cancelled) {
          setContent(text);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  return { content, error, loading };
}

/**
 * Decode a TIFF image to a PNG blob URL for cross-browser display.
 * Safari supports TIFF natively but Chrome/Firefox do not.
 */
function useTiffUrl(url: string) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setBlobUrl(null);
    setError(false);
    setLoading(true);

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch");
        return res.arrayBuffer();
      })
      .then((buf) => {
        const ifds = UTIF.decode(buf);
        if (ifds.length === 0) throw new Error("No pages in TIFF");
        UTIF.decodeImage(buf, ifds[0]);
        const rgba = UTIF.toRGBA8(ifds[0]);
        const w = ifds[0].width;
        const h = ifds[0].height;
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d")!;
        const imageData = ctx.createImageData(w, h);
        imageData.data.set(new Uint8Array(rgba));
        ctx.putImageData(imageData, 0, 0);
        return new Promise<Blob>((resolve, reject) => {
          canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Canvas toBlob failed"))), "image/png");
        });
      })
      .then((blob) => {
        if (!cancelled) {
          setBlobUrl(URL.createObjectURL(blob));
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [url]);

  // Cleanup blob URL
  useEffect(() => {
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [blobUrl]);

  return { blobUrl, error, loading };
}

// ---------------------------------------------------------------------------
// ViewToggle
// ---------------------------------------------------------------------------

function ViewToggle({ onToggle }: { onToggle: () => void }) {
  return (
    <div className="file-preview-view-toggle">
      <button className="file-preview-toggle-btn" onClick={onToggle} title="Preview">
        <Eye size={14} />
      </button>
      <button className="file-preview-toggle-btn" onClick={onToggle} title="Code">
        <CodeXml size={14} />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CodeViewer — unified viewer for all code & plain-text files
//
// Design principles:
//   • Edge-to-edge — fills the entire content area, no inner border/radius
//   • Sticky gutter — line numbers stay visible during horizontal scroll
//   • Word wrap — toggleable; state is lifted from parent via props
//   • Single component for code + text (language="text" disables highlighting)
// ---------------------------------------------------------------------------

/**
 * CodeViewer — flex-row-per-line layout with real DOM line-number elements.
 *
 * Uses a custom renderer for react-syntax-highlighter so each line is a
 * flex row: [line-number] [code-content]. This gives full control over
 * alignment, word-wrap sync, and styling — matching best-in-class code
 * viewers.
 */

/**
 * Convert a HAST (HTML Abstract Syntax Tree) node to a React element,
 * resolving syntax-highlight colors from the stylesheet the same way
 * react-syntax-highlighter's built-in createElement does.
 */
function hastToReact(
  node: any,
  key: number | string,
  stylesheet: Record<string, React.CSSProperties>,
): React.ReactNode {
  if (node.type === "text") return node.value;
  if (node.type !== "element") return null;
  const { tagName, properties = {}, children = [] } = node;
  const classNames: string[] = properties.className || [];

  // Merge styles from the theme stylesheet based on token classNames,
  // then layer any explicit inline styles on top.
  const classStyles = classNames.reduce<Record<string, any>>(
    (acc, cn) => ({ ...acc, ...(stylesheet[cn] || {}) }),
    {},
  );
  const merged = { ...classStyles, ...(properties.style || {}) };

  const props: Record<string, any> = { key };
  if (Object.keys(merged).length > 0) props.style = merged;

  return createElement(
    tagName,
    props,
    ...children.map((c: any, i: number) => hastToReact(c, i, stylesheet)),
  );
}

/** Check if a HAST node tree has any non-empty text content. */
function hasVisibleContent(children: any[]): boolean {
  return children.some((c: any) => {
    if (c.type === "text") return c.value.replace(/\n/g, "").length > 0;
    if (c.type === "element" && c.children) return hasVisibleContent(c.children);
    return false;
  });
}

// Hoisted constants to avoid creating new objects on every render
const CUSTOM_STYLE: React.CSSProperties = {
  background: "transparent",
  margin: 0,
  padding: 0,
  border: "none",
  fontSize: "inherit",
  lineHeight: "inherit",
  fontFamily: "inherit",
  overflow: "visible",
};
const CODE_TAG_PROPS = {
  style: {
    fontFamily: "inherit",
    fontSize: "inherit",
    background: "transparent",
    border: "none",
    padding: 0,
    display: "block",
  },
};

const CodeViewer = memo(function CodeViewer({
  children,
  language,
}: {
  children: string;
  language: string;
}) {
  const theme = useSyntaxTheme();

  const lineCount = (children.endsWith("\n")
    ? children.slice(0, -1)
    : children
  ).split("\n").length;
  const gutterWidth = `${(Math.max(2, String(lineCount).length) * 0.6 + 0.8).toFixed(1)}rem`;

  const renderer = useCallback(
    ({ rows, stylesheet }: { rows: any[]; stylesheet: Record<string, React.CSSProperties>; useInlineStyles: boolean }) =>
      rows.map((row: any, i: number) => {
        const lineNum = i + 1;
        const rowChildren = row.children || [];
        const tokens = rowChildren.map((child: any, j: number) =>
          hastToReact(child, j, stylesheet),
        );
        const empty = !hasVisibleContent(rowChildren);

        return (
          <div key={i} className="cv-line">
            <span className="cv-ln">{lineNum}</span>
            <div className="cv-code">
              {empty ? "\u00A0" : tokens}
            </div>
          </div>
        );
      }),
    [],
  );

  return (
    <div
      className="code-viewer"
      style={{ "--cv-gutter-w": gutterWidth } as React.CSSProperties}
    >
      <SyntaxHighlighter
        language={language}
        style={theme}
        wrapLines
        renderer={renderer}
        customStyle={CUSTOM_STYLE}
        codeTagProps={CODE_TAG_PROPS}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  );
});

// ---------------------------------------------------------------------------
// Sub-renderers
// ---------------------------------------------------------------------------

function LoadingView() {
  return (
    <div className="file-preview-loading">
      <Loader2 size={24} className="file-preview-spinner" />
    </div>
  );
}

function ErrorView() {
  return (
    <div className="file-preview-unsupported">Failed to load file content.</div>
  );
}

function ImagePreview({ url, alt, visible }: { url: string; alt: string; visible: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const scaleRef = useRef(1);
  const translateRef = useRef({ x: 0, y: 0 });
  const [, forceRender] = useState(0);
  const isPanning = useRef(false);
  const lastMouse = useRef({ x: 0, y: 0 });
  const wasVisible = useRef(visible);

  // Reset zoom/pan when panel reopens (false → true)
  if (visible && !wasVisible.current) {
    scaleRef.current = 1;
    translateRef.current = { x: 0, y: 0 };
  }
  wasVisible.current = visible;

  /**
   * Clamp translation so the image edge can't go past the container edge.
   * A 40px margin is kept so the image is always clearly visible,
   * even for users with reduced vision.
   */
  const clampTranslation = useCallback(() => {
    const container = containerRef.current;
    const img = imgRef.current;
    if (!container || !img) return;
    const s = scaleRef.current;
    const t = translateRef.current;
    const margin = 30;
    const limitX = Math.max(0, (img.clientWidth * s) / 2 + container.clientWidth / 2 - margin);
    const limitY = Math.max(0, (img.clientHeight * s) / 2 + container.clientHeight / 2 - margin);
    translateRef.current = {
      x: Math.max(-limitX, Math.min(limitX, t.x)),
      y: Math.max(-limitY, Math.min(limitY, t.y)),
    };
  }, []);

  // Register a non-passive wheel listener so preventDefault() actually works.
  // React's onWheel is passive by default — it cannot prevent the browser
  // from zooming the entire page on ctrl+wheel / pinch.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        scaleRef.current = Math.min(10, Math.max(0.1, scaleRef.current - e.deltaY * 0.01));
        clampTranslation();
        forceRender((n) => n + 1);
      } else if (scaleRef.current !== 1) {
        e.preventDefault();
        translateRef.current = {
          x: translateRef.current.x - e.deltaX,
          y: translateRef.current.y - e.deltaY,
        };
        clampTranslation();
        forceRender((n) => n + 1);
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [clampTranslation]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (scaleRef.current === 1) return;
    e.preventDefault();
    isPanning.current = true;
    lastMouse.current = { x: e.clientX, y: e.clientY };

    const onMouseMove = (ev: MouseEvent) => {
      if (!isPanning.current) return;
      const dx = ev.clientX - lastMouse.current.x;
      const dy = ev.clientY - lastMouse.current.y;
      lastMouse.current = { x: ev.clientX, y: ev.clientY };
      translateRef.current = {
        x: translateRef.current.x + dx,
        y: translateRef.current.y + dy,
      };
      clampTranslation();
      forceRender((n) => n + 1);
    };
    const onMouseUp = () => {
      isPanning.current = false;
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }, [clampTranslation]);

  // Double-click to reset zoom
  const handleDoubleClick = useCallback(() => {
    scaleRef.current = 1;
    translateRef.current = { x: 0, y: 0 };
    forceRender((n) => n + 1);
  }, []);

  const scale = scaleRef.current;
  const translate = translateRef.current;

  return (
    <div
      className="file-preview-image-container"
      ref={containerRef}
      onMouseDown={handleMouseDown}
      onDoubleClick={handleDoubleClick}
      style={{ cursor: scale !== 1 ? "grab" : "default" }}
    >
      <img
        className="file-preview-image"
        ref={imgRef}
        src={url}
        alt={alt}
        draggable={false}
        style={{
          transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
        }}
      />
      {scale !== 1 && (
        <span className="file-preview-zoom-badge">{Math.round(scale * 100)}%</span>
      )}
    </div>
  );
}

function TiffPreview({ url, alt, visible }: { url: string; alt: string; visible: boolean }) {
  const { blobUrl, error, loading } = useTiffUrl(url);
  if (loading) return <LoadingView />;
  if (error || !blobUrl) return <ErrorView />;
  return <ImagePreview url={blobUrl} alt={alt} visible={visible} />;
}

function CodePreview({
  url,
  language,
  onContentLoaded,
}: {
  url: string;
  language: string;
  onContentLoaded?: (content: string) => void;
}) {
  const { content, error, loading } = useTextContent(url);

  useEffect(() => {
    if (content !== null && onContentLoaded) onContentLoaded(content);
  }, [content, onContentLoaded]);

  if (loading) return <LoadingView />;
  if (error || content === null) return <ErrorView />;
  return <CodeViewer language={language}>{content}</CodeViewer>;
}

function MarkdownPreview({
  url,
  onContentLoaded,
}: {
  url: string;
  onContentLoaded?: (content: string) => void;
}) {
  const { content, error, loading } = useTextContent(url);

  useEffect(() => {
    if (content !== null && onContentLoaded) onContentLoaded(content);
  }, [content, onContentLoaded]);

  if (loading) return <LoadingView />;
  if (error || content === null) return <ErrorView />;
  return (
    <div className="file-preview-dual">
      <div className="file-preview-dual-layer file-preview-dual-preview">
        <div className="file-preview-markdown message-content">
          <Markdown>{content}</Markdown>
        </div>
      </div>
      <div className="file-preview-dual-layer file-preview-dual-code">
        <CodeViewer language="markdown">{content}</CodeViewer>
      </div>
    </div>
  );
}

function HtmlPreview({
  url,
  onContentLoaded,
}: {
  url: string;
  onContentLoaded?: (content: string) => void;
}) {
  const { content, error, loading } = useTextContent(url);

  useEffect(() => {
    if (content !== null && onContentLoaded) onContentLoaded(content);
  }, [content, onContentLoaded]);

  if (loading) return <LoadingView />;
  if (error || content === null) return <ErrorView />;
  return (
    <div className="file-preview-dual">
      <div className="file-preview-dual-layer file-preview-dual-preview">
        <iframe
          className="file-preview-iframe"
          srcDoc={content}
          title="HTML preview"
          sandbox="allow-same-origin allow-scripts"
        />
      </div>
      <div className="file-preview-dual-layer file-preview-dual-code">
        <CodeViewer language="html">{content}</CodeViewer>
      </div>
    </div>
  );
}

function SvgPreview({
  url,
  visible,
  onContentLoaded,
}: {
  url: string;
  visible: boolean;
  onContentLoaded?: (content: string) => void;
}) {
  const { content, error, loading } = useTextContent(url);

  useEffect(() => {
    if (content !== null && onContentLoaded) onContentLoaded(content);
  }, [content, onContentLoaded]);

  return (
    <div className="file-preview-dual">
      <div className="file-preview-dual-layer file-preview-dual-preview">
        <ImagePreview url={url} alt="SVG preview" visible={visible} />
      </div>
      <div className="file-preview-dual-layer file-preview-dual-code">
        {loading ? <LoadingView /> :
         error || content === null ? <ErrorView /> :
         <CodeViewer language="xml">{content}</CodeViewer>}
      </div>
    </div>
  );
}

function parseCsv(text: string): string[][] {
  return text
    .trim()
    .split("\n")
    .map((line) => {
      const result: string[] = [];
      let current = "";
      let inQuotes = false;
      for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"') {
          if (inQuotes && line[i + 1] === '"') {
            current += '"';
            i++;
          } else {
            inQuotes = !inQuotes;
          }
        } else if (ch === "," && !inQuotes) {
          result.push(current);
          current = "";
        } else {
          current += ch;
        }
      }
      result.push(current);
      return result;
    });
}

const CSV_MAX_ROWS = 500;

function CsvPreview({
  url,
  onContentLoaded,
}: {
  url: string;
  onContentLoaded?: (content: string) => void;
}) {
  const { content, error, loading } = useTextContent(url);

  useEffect(() => {
    if (content !== null && onContentLoaded) onContentLoaded(content);
  }, [content, onContentLoaded]);

  const { header, body, totalRows } = useMemo(() => {
    if (!content) return { header: [] as string[], body: [] as string[][], totalRows: 0 };
    const parsed = parseCsv(content);
    if (parsed.length === 0) return { header: [], body: [], totalRows: 0 };
    const [hdr, ...rest] = parsed;
    return { header: hdr, body: rest.slice(0, CSV_MAX_ROWS), totalRows: rest.length };
  }, [content]);

  if (loading) return <LoadingView />;
  if (error || content === null) return <ErrorView />;
  if (header.length === 0 && body.length === 0) return <ErrorView />;

  const capped = totalRows > CSV_MAX_ROWS;

  return (
    <div className="file-preview-dual">
      <div className="file-preview-dual-layer file-preview-dual-preview">
        <div className="csv-viewer">
          <div className="csv-viewer-table-wrapper">
            <table className="csv-viewer-table">
              <thead>
                <tr>
                  <th className="csv-viewer-corner" />
                  {header.map((cell, i) => (
                    <th key={i}>{cell}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {body.map((row, ri) => (
                  <tr key={ri}>
                    <td className="csv-viewer-row-num">{ri + 1}</td>
                    {row.map((cell, ci) => (
                      <td key={ci}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {capped && (
            <div className="csv-viewer-cap-notice">
              Showing {CSV_MAX_ROWS} of {totalRows.toLocaleString()} rows. Download to see all data.
            </div>
          )}
        </div>
      </div>
      <div className="file-preview-dual-layer file-preview-dual-code">
        <CodeViewer language="text">{content}</CodeViewer>
      </div>
    </div>
  );
}

/**
 * PptxPreview — shows client-side render instantly, swaps to high-fidelity
 * LibreOffice PDF as soon as it's ready. Caches the PDF blob URL so
 * re-opening the same file is instant.
 *
 * If LibreOffice is unavailable or fails, the client-side render stays
 * without any error shown to the user.
 */
const _pptxPdfCache = new Map<string, string>();

function PptxPreview({
  conversationId,
  path,
  previewUrl,
  visible,
}: {
  conversationId: string;
  path: string;
  previewUrl: string;
  visible: boolean;
}) {
  const cacheKey = `${conversationId}:${path}`;
  const [pdfUrl, setPdfUrl] = useState<string | null>(
    () => _pptxPdfCache.get(cacheKey) ?? null,
  );

  useEffect(() => {
    if (_pptxPdfCache.has(cacheKey)) {
      setPdfUrl(_pptxPdfCache.get(cacheKey)!);
      return;
    }

    let cancelled = false;
    const previewEndpoint = `/api/files/${conversationId}/preview?path=${encodeURIComponent(path)}`;

    fetch(previewEndpoint)
      .then(async (res) => {
        if (!res.ok) throw new Error("server conversion failed");
        return res.blob();
      })
      .then((blob) => {
        if (!cancelled) {
          const url = URL.createObjectURL(blob);
          _pptxPdfCache.set(cacheKey, url);
          setPdfUrl(url);
        }
      })
      .catch(() => {
        // LibreOffice unavailable or failed — client-side render stays
      });

    return () => {
      cancelled = true;
    };
  }, [conversationId, path, cacheKey]);

  if (pdfUrl) {
    return (
      <Suspense fallback={<LoadingView />}>
        <LazyPdfViewer url={pdfUrl} visible={visible} />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<LoadingView />}>
      <LazyPptxViewer url={previewUrl} visible={visible} />
    </Suspense>
  );
}

/**
 * PdfPreview — re-mounts its <embed> on each panel open so the PDF viewer
 * re-applies #view=FitH at the current container width. The browser's HTTP
 * cache serves the file instantly; the panel's expand animation masks the
 * PDF viewer's initialization time.
 */
// Kept as fallback — swap LazyPdfViewer to PdfPreview if react-pdf has issues
// @ts-expect-error intentionally unused
function PdfPreview({ url, visible }: { url: string; visible: boolean }) {
  const mountKey = useRef(0);
  const wasVisible = useRef(visible);
  if (visible && !wasVisible.current) {
    mountKey.current += 1;
  }
  wasVisible.current = visible;

  return (
    <embed
      key={mountKey.current}
      className="file-preview-pdf"
      src={`${url}#toolbar=0&navpanes=0&scrollbar=1&view=FitH`}
      type="application/pdf"
    />
  );
}

function AudioPreview({ url, fileName }: { url: string; fileName: string }) {
  return (
    <div className="file-preview-audio">
      <audio controls controlsList="nodownload" src={url} title={fileName}>
        Your browser does not support audio playback.
      </audio>
    </div>
  );
}

function VideoPreview({ url, fileName }: { url: string; fileName: string }) {
  return (
    <div className="file-preview-video">
      <video controls controlsList="nodownload" disablePictureInPicture src={url} title={fileName}>
        Your browser does not support video playback.
      </video>
    </div>
  );
}

function TextPreview({
  url,
  onContentLoaded,
}: {
  url: string;
  onContentLoaded?: (content: string) => void;
}) {
  const { content, error, loading } = useTextContent(url);

  useEffect(() => {
    if (content !== null && onContentLoaded) onContentLoaded(content);
  }, [content, onContentLoaded]);

  if (loading) return <LoadingView />;
  if (error || content === null) return <ErrorView />;
  return <CodeViewer language="text">{content}</CodeViewer>;
}

// ---------------------------------------------------------------------------
// Categories that show a copy button in the header
// ---------------------------------------------------------------------------

const COPYABLE_CATEGORIES = new Set<Category>([
  "code",
  "json",
  "xml",
  "csv",
  "markdown",
  "html",
  "svg",
  "text",
]);

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const MIN_WIDTH = 400;
const MIN_CHAT_WIDTH = 400;
export default function FilePreview({ visible }: { visible: boolean }) {
  const { state, dispatch } = useAppContext();
  const preview = state.filePreview;
  const viewModeRef = useRef<"preview" | "code">("preview");
  const [textContent, setTextContent] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const gripRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // ── Ratio-based width management ──
  // Store the split as a ratio (0–1) of the flex container so the panel
  // scales proportionally when the browser is resized.
  const ratioRef = useRef(0.5); // default: half-half
  const hasSetInitialWidth = useRef(false);

  /** Read the container width (the flex row holding chat + grip + panel). */
  const getContainerWidth = useCallback(() => {
    const panel = panelRef.current;
    if (!panel) return 0;
    const container = panel.closest(".main-content-body");
    return container ? container.clientWidth : 0;
  }, []);

  /** Apply the current ratio as pixel width, clamped to min-widths. */
  const applyRatio = useCallback(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const cw = getContainerWidth();
    if (cw === 0) return;
    const target = Math.floor(cw * ratioRef.current);
    const maxW = cw - MIN_CHAT_WIDTH;
    const w = Math.min(maxW, Math.max(MIN_WIDTH, target));
    panel.style.width = `${w}px`;
    panel.style.minWidth = `${w}px`;
  }, [getContainerWidth]);

  // Set initial width (no transition on first paint)
  useEffect(() => {
    if (hasSetInitialWidth.current) return;
    const panel = panelRef.current;
    if (!panel) return;
    panel.style.transition = "none";
    applyRatio();
    requestAnimationFrame(() => { panel.style.transition = ""; });
    hasSetInitialWidth.current = true;
  }, [applyRatio]);

  // Recompute pixels on window resize to maintain the ratio
  useEffect(() => {
    if (!visible) return;
    const onResize = () => {
      const panel = panelRef.current;
      if (!panel) return;
      // Resize should be instant, not animated
      panel.style.transition = "none";
      applyRatio();
      requestAnimationFrame(() => { panel.style.transition = ""; });
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [visible, applyRatio]);

  // Resize drag — uses Pointer Capture so the grip keeps receiving events
  // even when the cursor moves over iframes, embeds, or other interactive
  // content that would otherwise swallow mouse events.
  const handleDragStart = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    if (!visible) return;
    const panel = panelRef.current;
    const grip = gripRef.current;
    if (!panel || !grip) return;

    // Capture all pointer events to the grip element — this is the key fix
    // for iframes/embeds stealing mousemove during drag.
    grip.setPointerCapture(e.pointerId);

    const panelRight = panel.getBoundingClientRect().right;
    const chatArea = panel.closest(".main-content-body")?.querySelector(".chat-area");
    const chatLeft = chatArea ? chatArea.getBoundingClientRect().left : 0;
    const maxWidth = panelRight - chatLeft - MIN_CHAT_WIDTH;
    const containerWidth = getContainerWidth();

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    grip.classList.add("is-dragging");
    panel.style.transition = "none";
    // Unfreeze content in case it was frozen by expand/collapse transition
    const content = contentRef.current;
    if (content) {
      content.style.width = "";
      content.style.minWidth = "";
    }

    const onPointerMove = (ev: PointerEvent) => {
      const w = Math.min(maxWidth, Math.max(MIN_WIDTH, panelRight - ev.clientX));
      panel.style.width = `${w}px`;
      panel.style.minWidth = `${w}px`;
      if (containerWidth > 0) {
        ratioRef.current = w / containerWidth;
      }
    };

    const onPointerUp = () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      grip.classList.remove("is-dragging");
      panel.style.transition = "";
      grip.removeEventListener("pointermove", onPointerMove);
      grip.removeEventListener("pointerup", onPointerUp);
    };

    // With pointer capture, events route to the grip element, not window
    grip.addEventListener("pointermove", onPointerMove);
    grip.addEventListener("pointerup", onPointerUp);
  }, [visible, getContainerWidth]);

  // Double-click grip to reset to half-half
  const handleDoubleClick = useCallback(() => {
    ratioRef.current = 0.5;
    applyRatio();
  }, [applyRatio]);

  // ── Freeze content width during expand/collapse transition ──
  // Without this, the browser recomputes pre-wrap line breaks on every
  // animation frame as the panel width changes — thousands of spans reflowed
  // 60x/sec. Freezing gives the content a fixed width so the panel just
  // clips the overflow. One layout before, one after, zero during.
  // useLayoutEffect so freeze happens BEFORE paint — the animation starts
  // with content already frozen, avoiding jank in the first frames.
  useLayoutEffect(() => {
    const panel = panelRef.current;
    const content = contentRef.current;
    if (!panel || !content) return;

    // Skip if content is already frozen (DOM-first handler already did it)
    const alreadyFrozen = !!content.style.width;

    if (visible && !alreadyFrozen) {
      // Expanding: freeze content at target width so it layouts once at final size.
      const cw = getContainerWidth();
      if (cw > 0) {
        const target = Math.floor(cw * ratioRef.current);
        const maxW = cw - MIN_CHAT_WIDTH;
        const w = Math.min(maxW, Math.max(MIN_WIDTH, target));
        content.style.width = `${w}px`;
        content.style.minWidth = `${w}px`;
      }
    }
    // Collapsing freeze is handled by the DOM-first close handler.
    // If it wasn't (e.g. state-driven close), freeze here as fallback.
    if (!visible && !alreadyFrozen) {
      const currentW = content.offsetWidth;
      if (currentW > 0) {
        content.style.width = `${currentW}px`;
        content.style.minWidth = `${currentW}px`;
      }
    }

    const unfreeze = () => {
      content.style.width = "";
      content.style.minWidth = "";
    };

    const onEnd = (e: TransitionEvent) => {
      if (e.target !== panel || e.propertyName !== "width") return;
      unfreeze();
    };

    panel.addEventListener("transitionend", onEnd);
    const fallback = setTimeout(unfreeze, 350);
    return () => {
      panel.removeEventListener("transitionend", onEnd);
      clearTimeout(fallback);
    };
  }, [visible, getContainerWidth]);

  // Reset view mode and text content when file changes
  useEffect(() => {
    viewModeRef.current = "preview";
    const panel = panelRef.current;
    if (panel) panel.dataset.viewMode = "preview";
    setTextContent(null);
    setCopied(false);
  }, [preview?.path]);

  const handleContentLoaded = useCallback((content: string) => {
    setTextContent(content);
  }, []);

  if (!preview) return null;

  const { path, mimeType, conversationId } = preview;
  const previewUrl = `/api/files/${conversationId}?path=${encodeURIComponent(path)}`;
  const downloadUrl = `${previewUrl}&download=true`;
  const fileName = basename(path);
  const category = detectCategory(mimeType, path);

  const handleClose = useCallback(() => {
    const panel = panelRef.current;
    const grip = gripRef.current;
    const content = contentRef.current;

    // Freeze content at current width before collapsing
    if (content) {
      const w = content.offsetWidth;
      if (w > 0) {
        content.style.width = `${w}px`;
        content.style.minWidth = `${w}px`;
      }
    }

    // Start animation immediately via DOM — no waiting for React
    panel?.classList.add("file-preview-collapsed");
    grip?.classList.add("file-preview-grip-collapsed");

    // Unfreeze after animation
    if (panel && content) {
      const unfreeze = () => { content.style.width = ""; content.style.minWidth = ""; };
      const onEnd = (e: TransitionEvent) => {
        if (e.target !== panel || e.propertyName !== "width") return;
        unfreeze();
        panel.removeEventListener("transitionend", onEnd);
      };
      panel.addEventListener("transitionend", onEnd);
      setTimeout(unfreeze, 350);
    }

    // Restore right panel synchronously so its transition starts in the same
    // paint frame as the preview collapse — prevents the "breathe" effect.
    if (state.rightPanelBeforePreview === true) {
      dispatch({ type: "SET_RIGHT_PANEL", payload: true });
    }

    // Defer preview state confirmation — re-render confirms what DOM already shows
    requestAnimationFrame(() => {
      dispatch({ type: "SET_FILE_PREVIEW_VISIBLE", payload: false });
    });
  }, [dispatch, state.rightPanelBeforePreview]);

  const handleDownload = () => {
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = fileName;
    a.click();
  };

  const handleCopy = async () => {
    if (!textContent) return;
    try {
      await navigator.clipboard.writeText(textContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard not available
    }
  };

  const hasDualMode = category === "markdown" || category === "html" || category === "svg" || category === "csv";
  const alwaysCode = category === "code" || category === "json" || category === "xml" || category === "text";
  const showCopy = COPYABLE_CATEGORIES.has(category);

  // Toggle view mode via direct DOM — zero React re-renders
  const toggleMode = useCallback(() => {
    const next = viewModeRef.current === "preview" ? "code" : "preview";
    viewModeRef.current = next;
    const panel = panelRef.current;
    if (panel) panel.dataset.viewMode = next;
  }, []);

  let content: React.ReactNode;
  switch (category) {
    case "image":
      content = <ImagePreview url={previewUrl} alt={fileName} visible={visible} />;
      break;
    case "tiff":
      content = <TiffPreview url={previewUrl} alt={fileName} visible={visible} />;
      break;
    case "svg":
      content = <SvgPreview url={previewUrl} visible={visible} onContentLoaded={handleContentLoaded} />;
      break;
    case "pdf":
      content = (
        <Suspense fallback={<LoadingView />}>
          <LazyPdfViewer url={previewUrl} visible={visible} />
        </Suspense>
      );
      break;
    case "markdown":
      content = <MarkdownPreview url={previewUrl} onContentLoaded={handleContentLoaded} />;
      break;
    case "html":
      content = <HtmlPreview url={previewUrl} onContentLoaded={handleContentLoaded} />;
      break;
    case "csv":
      content = <CsvPreview url={previewUrl} onContentLoaded={handleContentLoaded} />;
      break;
    case "json":
      content = <CodePreview url={previewUrl} language="json" onContentLoaded={handleContentLoaded} />;
      break;
    case "xml":
      content = <CodePreview url={previewUrl} language="xml" onContentLoaded={handleContentLoaded} />;
      break;
    case "code":
      content = <CodePreview url={previewUrl} language={languageForPath(path)} onContentLoaded={handleContentLoaded} />;
      break;
    case "docx":
      content = (
        <Suspense fallback={<LoadingView />}>
          <LazyDocxViewer url={previewUrl} visible={visible} />
        </Suspense>
      );
      break;
    case "xlsx":
      content = (
        <Suspense fallback={<LoadingView />}>
          <LazyXlsxViewer url={previewUrl} />
        </Suspense>
      );
      break;
    case "pptx":
      content = (
        <PptxPreview
          conversationId={conversationId}
          path={path}
          previewUrl={previewUrl}
          visible={visible}
        />
      );
      break;
    case "audio":
      content = <AudioPreview url={previewUrl} fileName={fileName} />;
      break;
    case "video":
      content = <VideoPreview url={previewUrl} fileName={fileName} />;
      break;
    case "text":
      content = <TextPreview url={previewUrl} onContentLoaded={handleContentLoaded} />;
      break;
    default:
      content = (
        <div className="file-preview-unsupported">
          <File size={48} strokeWidth={1.2} />
          <p>No preview for this file type</p>
          <button className="file-preview-download-btn" onClick={handleDownload}>
            <Download size={16} />
            Download
          </button>
        </div>
      );
  }

  return (
    <>
      {/* Resize grip — sits on the panel's left edge */}
      <div
        className={`file-preview-grip${!visible ? " file-preview-grip-collapsed" : ""}`}
        ref={gripRef}
        onPointerDown={handleDragStart}
        onDoubleClick={handleDoubleClick}
      >
        <div className="file-preview-grip-pill" />
      </div>

      <div
        className={`file-preview-panel${!visible ? " file-preview-collapsed" : ""}`}
        ref={panelRef}
        data-view-mode="preview"
        style={{ width: MIN_WIDTH, minWidth: MIN_WIDTH }}
      >
        <div className="file-preview-header">
          <span className="file-preview-title" title={path}>
            {fileName}
          </span>
          <div className="file-preview-actions">
            {hasDualMode && (
              <ViewToggle onToggle={toggleMode} />
            )}
            {showCopy && (
              <button
                className="file-preview-action-btn"
                onClick={handleCopy}
                title={copied ? "Copied!" : "Copy"}
                disabled={!textContent}
              >
                {copied ? <Check size={16} /> : <Copy size={16} />}
              </button>
            )}
            <button
              className="file-preview-action-btn"
              onClick={handleDownload}
              title="Download"
            >
              <Download size={16} />
            </button>
            <button
              className="file-preview-action-btn"
              onClick={handleClose}
              title="Close"
            >
              <X size={16} />
            </button>
          </div>
        </div>
        <div ref={contentRef} className={`file-preview-content${alwaysCode ? " file-preview-content--code" : ""}`}>{content}</div>
      </div>
    </>
  );
}
