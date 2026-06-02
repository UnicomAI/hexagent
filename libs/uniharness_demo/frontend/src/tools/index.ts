/**
 * Public API for tool UI rendering.
 *
 * Usage:
 *   import { getToolIcon, getToolLabel, getResultTarget } from "../tools";
 */

import {
  Plug,
  Terminal,
  FileText,
  FilePen,
  Pencil,
  FolderSearch,
  FileSearchCorner,
  Search,
  Globe,
  Bot,
  Eye,
  Code,
  FileCode,
  Braces,
  Database,
  Cpu,
  ScrollText,
} from "lucide-react";
import { BUILTIN_TOOLS } from "./registry";
import type { ResultTarget, ResultRendererProps } from "./types";

export type { ToolUIConfig, ResultTarget, ResultRendererProps } from "./types";

// ── Icons ──

/**
 * Keyword-based icon fallback for unknown / MCP tools.
 * Only used when the tool name doesn't match a built-in.
 */
const KEYWORD_ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  bash: Terminal, shell: Terminal, execute: Terminal, run_command: Terminal, computer: Terminal,
  read: FileText, read_file: FileText, cat: FileText, view: Eye,
  write: FilePen, write_file: FilePen, create_file: FilePen, save_file: FilePen,
  edit: Pencil, edit_file: Pencil, patch: Pencil, replace: Pencil,
  glob: FolderSearch, find: FolderSearch, list: FolderSearch, list_directory: FolderSearch, ls: FolderSearch,
  grep: FileSearchCorner, search: Search, ripgrep: FileSearchCorner,
  fetch: Globe, web_fetch: Globe, web_search: Globe, tavily_search: Globe, browse: Globe,
  agent: Bot,
  skill: ScrollText,
  code: Code, python: FileCode, javascript: FileCode,
  json: Braces, database: Database, sql: Database,
  system: Cpu,
};

function isMcpTool(name: string): boolean {
  const lower = name.toLowerCase();
  return lower.includes(":") || lower.startsWith("mcp_") || lower.startsWith("mcp-");
}

/** Get the icon component for a tool by name. */
export function getToolIcon(name: string): React.ComponentType<{ className?: string }> {
  // 1. Exact match in built-in registry
  const builtin = BUILTIN_TOOLS[name];
  if (builtin) return builtin.icon;

  // 2. Keyword-based fallback
  const lower = name.toLowerCase();
  if (KEYWORD_ICON_MAP[lower]) return KEYWORD_ICON_MAP[lower];
  for (const [key, icon] of Object.entries(KEYWORD_ICON_MAP)) {
    if (lower.includes(key)) return icon;
  }

  // 3. MCP tools get puzzle icon
  if (isMcpTool(name)) return Plug;

  return Plug;
}

// ── Labels ──

/**
 * Get a human-readable label for a tool call.
 * During streaming, pass argsText for partial field extraction.
 * Returns the tool-specific label if available, otherwise a formatted tool name.
 */
export function getToolLabel(name: string, input: Record<string, unknown>, argsText?: string): string {
  const builtin = BUILTIN_TOOLS[name];
  if (builtin?.getLabel) {
    const label = builtin.getLabel(input, argsText);
    if (label) return label;
  }
  // Default: format tool name
  return name.replace(/__/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()).replace(/\bMcp\b/g, "MCP");
}

// ── Result target ──

/** Where should a tool's result be rendered? */
export function getResultTarget(name: string): ResultTarget {
  return BUILTIN_TOOLS[name]?.resultTarget ?? "inline";
}

/** Get the custom result component for a tool (if any). */
export function getResultComponent(name: string): React.ComponentType<ResultRendererProps> | undefined {
  return BUILTIN_TOOLS[name]?.ResultComponent;
}

// ── Dynamic icon domain ──

/** Get domain info for favicon loading, or undefined. */
export function getIconDomain(name: string, input: Record<string, unknown>, argsText?: string): { domain: string; siteUrl?: string } | undefined {
  return BUILTIN_TOOLS[name]?.getIconDomain?.(input, argsText);
}

// ── Custom status ──

/** Get custom done-status text/class for a tool, or undefined for default. */
export function getStatus(name: string, output: string): { text: string; className: string } | undefined {
  return BUILTIN_TOOLS[name]?.getStatus?.(output);
}

// ── Click URL ──

/** Get a URL to open when the tool header is clicked (after done), or undefined. */
export function getClickUrl(name: string, input: Record<string, unknown>): string | undefined {
  return BUILTIN_TOOLS[name]?.getClickUrl?.(input);
}

// ── Icon fallback ──

/** Get letter/color fallback when dynamic icon fails. */
export function getIconFallback(name: string, input: Record<string, unknown>, argsText?: string): { letter: string; color: string } | undefined {
  return BUILTIN_TOOLS[name]?.getIconFallback?.(input, argsText);
}

// ── No fold body ──

/** Whether a tool should never show the fold body. */
export function hasNoFoldBody(name: string): boolean {
  return BUILTIN_TOOLS[name]?.noFoldBody === true;
}

// ── Input content ──

/** Get custom input content for the fold body, or undefined for default. */
export function getInputContent(name: string, input: Record<string, unknown>, argsText?: string): { text: string; language: string } | undefined {
  return BUILTIN_TOOLS[name]?.getInputContent?.(input, argsText);
}

// ── Built-in check ──

/** Whether a tool is a built-in (registered in the registry). */
export function isBuiltinTool(name: string): boolean {
  return name in BUILTIN_TOOLS;
}
