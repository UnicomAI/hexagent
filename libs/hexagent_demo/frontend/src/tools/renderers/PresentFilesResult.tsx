/**
 * Custom inline renderer for PresentToUser tool results.
 *
 * Parses the XML output to extract file entries and renders them
 * as clickable cards with icons, filenames, and download buttons.
 */

import { useMemo, useCallback, memo } from "react";
import { FileText, FileCode, Image, FileSpreadsheet, Music, Video, File, Download, AlertCircle } from "lucide-react";
import { useAppContext } from "../../store";
import ScrollableText from "../../components/ScrollableText";
import { withApiBase } from "../../apiBase";
import type { ResultRendererProps } from "../types";

interface PresentedFile {
  path: string;
  mimeType: string;
}

/** Parse the XML tool output into structured file entries. */
function parseOutput(output: string): { files: PresentedFile[]; error?: string } {
  const errorMatch = output.match(/<error>([\s\S]*?)<\/error>/);
  if (errorMatch) {
    return { files: [], error: errorMatch[1].trim() };
  }

  const files: PresentedFile[] = [];
  const seen = new Set<string>();
  const fileRegex =
    /<file>\s*<file_path>([\s\S]*?)<\/file_path>\s*<mime_type>([\s\S]*?)<\/mime_type>\s*<\/file>/g;
  let match;
  while ((match = fileRegex.exec(output)) !== null) {
    const path = match[1].trim();
    const mimeType = match[2].trim();
    // Deduplicate repeated PresentToUser entries for the same file in one render batch.
    const key = path.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    files.push({ path, mimeType });
  }
  return { files };
}

/** Extract the basename from a file path. */
function basename(path: string): string {
  return path.split("/").pop() || path;
}

/** Extensions that map to code preview (subset of FilePreview's EXT_TO_LANGUAGE). */
const CODE_EXTENSIONS = new Set([
  ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".rb", ".java", ".kt",
  ".kts", ".scala", ".c", ".h", ".cpp", ".cxx", ".cc", ".hpp", ".cs",
  ".swift", ".m", ".php", ".r", ".R", ".lua", ".pl", ".pm", ".sh", ".bash",
  ".zsh", ".fish", ".ps1", ".sql", ".yaml", ".yml", ".toml", ".ini", ".cfg",
  ".conf", ".dockerfile", ".tf", ".hcl", ".proto", ".graphql", ".gql",
  ".dart", ".ex", ".exs", ".erl", ".hs", ".ml", ".mli", ".clj", ".vim",
  ".css", ".scss", ".sass", ".less", ".makefile", ".cmake",
]);

/** Pick a lucide icon based on MIME type and file path. Previewable files
 *  get a distinct icon; unsupported types get the generic File icon. */
const UNSUPPORTED_EXTS = new Set([
  ".avi", ".wmv", ".flv", ".mkv",
  ".odp", ".ods", ".odt", ".rtf",
  ".doc", ".ppt", ".xls",
]);

const FileIcon = memo(function FileIcon({ mimeType, path }: { mimeType: string; path: string }) {
  const ext = (path.split("/").pop() || "").toLowerCase();
  const dotIdx = ext.lastIndexOf(".");
  const fileExt = dotIdx > 0 ? ext.slice(dotIdx) : "";

  if (mimeType.startsWith("image/")) return <Image size={20} />;
  if (mimeType.startsWith("audio/")) return <Music size={20} />;
  if (UNSUPPORTED_EXTS.has(fileExt)) return <File size={20} />;
  if (mimeType.startsWith("video/")) return <Video size={20} />;

  if (mimeType.includes("pdf")) return <FileText size={20} />;
  if (mimeType.includes("spreadsheet") || mimeType.includes("csv") || mimeType.includes("excel"))
    return <FileSpreadsheet size={20} />;
  if (mimeType.includes("word") || mimeType.includes("document") || mimeType.includes("powerpoint") || mimeType.includes("presentation"))
    return <FileText size={20} />;
  if (mimeType === "application/json" || mimeType === "application/xml" || mimeType === "text/xml")
    return <FileCode size={20} />;

  const base = ext;

  if (fileExt === ".md" || fileExt === ".mdx" || mimeType === "text/markdown") return <FileText size={20} />;
  if (fileExt === ".html" || fileExt === ".htm" || mimeType === "text/html") return <FileCode size={20} />;
  if (fileExt === ".csv" || mimeType === "text/csv") return <FileSpreadsheet size={20} />;
  if (fileExt === ".json") return <FileCode size={20} />;
  if (fileExt === ".xml") return <FileCode size={20} />;
  if (CODE_EXTENSIONS.has(fileExt)) return <FileCode size={20} />;
  if (base === "makefile" || base === "dockerfile" || base === "jenkinsfile") return <FileCode size={20} />;

  // Generic text fallback — still previewable
  if (mimeType.startsWith("text/") || mimeType === "application/javascript" || mimeType === "application/x-sh")
    return <FileText size={20} />;

  // Not previewable
  return <File size={20} />;
});

/** Human-readable label for a MIME type, with extension fallback. */
function mimeLabel(mimeType: string, path: string): string {
  const mimeMap: Record<string, string> = {
    "image/png": "PNG Image",
    "image/jpeg": "JPEG Image",
    "image/gif": "GIF Image",
    "image/svg+xml": "SVG Image",
    "image/webp": "WebP Image",
    "image/tiff": "TIFF Image",
    "image/bmp": "BMP Image",
    "image/x-icon": "ICO Image",
    "image/vnd.microsoft.icon": "ICO Image",
    "image/avif": "AVIF Image",
    "image/heic": "HEIC Image",
    "image/heif": "HEIF Image",
    "application/pdf": "PDF Document",
    "text/plain": "Plain Text",
    "text/csv": "CSV File",
    "text/html": "HTML Document",
    "text/markdown": "Markdown",
    "text/xml": "XML File",
    "application/json": "JSON File",
    "application/xml": "XML File",
    "application/javascript": "JavaScript",
    "application/x-sh": "Shell Script",
    "application/zip": "ZIP Archive",
    "application/gzip": "GZIP Archive",
    "application/x-tar": "TAR Archive",
    "application/x-7z-compressed": "7z Archive",
    "application/x-rar-compressed": "RAR Archive",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word Document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel Spreadsheet",
    "application/msword": "Word Document",
    "application/vnd.ms-powerpoint": "PowerPoint",
    "application/vnd.ms-excel": "Excel Spreadsheet",
  };
  if (mimeMap[mimeType]) return mimeMap[mimeType];

  // Extension-based fallback
  const name = path.split("/").pop() || "";
  const dotIdx = name.lastIndexOf(".");
  const ext = dotIdx > 0 ? name.slice(dotIdx + 1).toLowerCase() : "";

  const extMap: Record<string, string> = {
    py: "Python", js: "JavaScript", jsx: "JavaScript (JSX)",
    ts: "TypeScript", tsx: "TypeScript (TSX)", go: "Go", rs: "Rust",
    rb: "Ruby", java: "Java", kt: "Kotlin", scala: "Scala",
    c: "C", h: "C Header", cpp: "C++", cc: "C++", hpp: "C++ Header",
    cs: "C#", swift: "Swift", php: "PHP", r: "R", lua: "Lua",
    sh: "Shell Script", bash: "Bash Script", zsh: "Zsh Script",
    sql: "SQL", yaml: "YAML", yml: "YAML", toml: "TOML",
    ini: "INI Config", conf: "Config", proto: "Protobuf",
    graphql: "GraphQL", dart: "Dart", ex: "Elixir", hs: "Haskell",
    md: "Markdown", mdx: "MDX", css: "CSS", scss: "SCSS", less: "Less",
    html: "HTML Document", htm: "HTML Document", xml: "XML File",
    csv: "CSV File", json: "JSON File", svg: "SVG Image",
    ico: "ICO Image", tif: "TIFF Image", tiff: "TIFF Image",
    bmp: "BMP Image", avif: "AVIF Image", heic: "HEIC Image",
    mp3: "MP3 Audio", wav: "WAV Audio", ogg: "OGG Audio", flac: "FLAC Audio",
    mp4: "MP4 Video", webm: "WebM Video", mov: "MOV Video", avi: "AVI Video",
    zip: "ZIP Archive", gz: "GZIP Archive", tar: "TAR Archive",
    "7z": "7z Archive", rar: "RAR Archive",
    docx: "Word Document", doc: "Word Document", odt: "OpenDocument Text", rtf: "Rich Text",
    pptx: "PowerPoint", ppt: "PowerPoint", odp: "OpenDocument Presentation",
    xlsx: "Excel Spreadsheet", xls: "Excel Spreadsheet", ods: "OpenDocument Spreadsheet",
  };
  if (ext && extMap[ext]) return extMap[ext];

  // Category-based fallback (e.g. "audio/aac" → "AAC Audio")
  const [category, sub] = mimeType.split("/");
  if (sub) {
    // Strip vendor/x- prefixes: "vnd.microsoft.icon" → "icon", "x-sh" → "sh"
    const clean = sub.replace(/^(vnd\.|x-)+/g, "").replace(/[.+-]/g, " ").trim();
    const label = clean.charAt(0).toUpperCase() + clean.slice(1);
    const suffix: Record<string, string> = { image: "Image", audio: "Audio", video: "Video", text: "File" };
    return suffix[category] ? `${label} ${suffix[category]}` : label;
  }

  return ext ? ext.toUpperCase() : "File";
}

export default memo(function PresentFilesResult({ output }: ResultRendererProps) {
  const { state, dispatch } = useAppContext();
  const conversationId = state.activeConversationId;

  const { files, error } = useMemo(() => parseOutput(output), [output]);

  const handleDownload = useCallback((e: React.MouseEvent, file: PresentedFile) => {
    e.stopPropagation();
    if (!conversationId) return;
    const url = withApiBase(
      `/api/files/${conversationId}?path=${encodeURIComponent(file.path)}`,
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = basename(file.path);
    a.click();
  }, [conversationId]);

  const handleCardClick = useCallback((file: PresentedFile) => {
    if (!conversationId) return;
    dispatch({
      type: "SET_FILE_PREVIEW",
      payload: { path: file.path, mimeType: file.mimeType, conversationId },
    });
  }, [conversationId, dispatch]);

  if (error) {
    return (
      <div className="present-files-error">
        <AlertCircle size={16} />
        <span>{error}</span>
      </div>
    );
  }

  if (files.length === 0) return null;

  return (
    <div className="present-files-list">
      {files.map((file) => (
        <div
          key={file.path}
          className="present-file-card"
          onClick={() => handleCardClick(file)}
        >
          <span className="present-file-icon">
            <FileIcon mimeType={file.mimeType} path={file.path} />
          </span>
          <div className="present-file-info">
            <ScrollableText className="present-file-name">{basename(file.path)}</ScrollableText>
            <div className="present-file-type">{mimeLabel(file.mimeType, file.path)}</div>
          </div>
          <button
            className="present-file-download"
            onClick={(e) => handleDownload(e, file)}
            title="Download"
          >
            <Download size={16} />
          </button>
        </div>
      ))}
    </div>
  );
});
