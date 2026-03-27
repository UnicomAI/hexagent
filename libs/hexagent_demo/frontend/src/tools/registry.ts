/**
 * Central registry of built-in tool UI configurations.
 *
 * Adding a new built-in tool's UI = adding one entry here.
 */

import {
  Terminal,
  FileText,
  FilePen,
  Pencil,
  FolderSearch,
  FileSearchCorner,
  Globe,
  Bot,
  ListTodo,
  ScrollText,
  FileOutput,
} from "lucide-react";
import type { ToolUIConfig } from "./types";
import { extractPartialField, countPartialArrayItems, letterColor } from "./parse";
import WebSearchResult from "./renderers/WebSearchResult";

/**
 * Create a label extractor that reads a string field from input,
 * falling back to partial extraction from streaming argsText.
 *
 * @param emptyLabel - Returned when the field isn't available yet (during early streaming).
 *                     Prevents the raw tool name from flashing before the real label.
 */
function fieldLabel(
  field: string,
  format: (value: string) => string = (v) => v,
  emptyLabel?: string,
): (input: Record<string, unknown>, argsText?: string) => string | undefined {
  return (input, argsText) => {
    // 1. Try parsed input (available after streaming completes)
    if (typeof input[field] === "string" && input[field]) {
      return format(input[field] as string);
    }
    // 2. Try partial extraction from streaming argsText
    if (argsText) {
      const partial = extractPartialField(argsText, field);
      if (partial) return format(partial);
    }
    // 3. Static prefix while field hasn't arrived yet
    return emptyLabel;
  };
}

/**
 * Try to extract a hostname from a URL string, returning undefined if not parseable.
 */
function tryHostname(url: string): string | undefined {
  try {
    return new URL(url).hostname;
  } catch {
    return undefined;
  }
}

/** Extract a URL from input or streaming argsText. */
function extractUrl(input: Record<string, unknown>, argsText?: string): string | undefined {
  if (typeof input.url === "string" && input.url) return input.url;
  if (argsText) return extractPartialField(argsText, "url");
  return undefined;
}

/**
 * Check if the domain part of a URL is fully streamed.
 * True when we've seen the path separator after the host (e.g. `https://www.domain.com/`)
 * or when the URL comes from fully-parsed input (not streaming).
 */
function isDomainComplete(input: Record<string, unknown>, argsText?: string): boolean {
  // Fully parsed — always complete
  if (typeof input.url === "string" && input.url) return true;
  // During streaming, check for a `/` after `://`
  const partial = argsText ? extractPartialField(argsText, "url") : undefined;
  if (!partial) return false;
  const protoEnd = partial.indexOf("://");
  if (protoEnd === -1) return false;
  return partial.indexOf("/", protoEnd + 3) !== -1;
}

/** Detect `<error>` tags in tool output — shared across all native tools. */
function errorStatus(output: string): { text: string; className: string } | undefined {
  if (/<error>[\s\S]*<\/error>/.test(output)) {
    return { text: "Failed", className: "is-failed" };
  }
  return undefined;
}

/**
 * Built-in tool UI configurations, keyed by exact tool name (case-sensitive).
 */
export const BUILTIN_TOOLS: Record<string, ToolUIConfig> = {
  Bash: {
    icon: Terminal,
    getLabel: fieldLabel("description"),
    getInputContent: (input, argsText?) => {
      const cmd = typeof input.command === "string" ? input.command : extractPartialField(argsText || "", "command");
      return cmd ? { text: cmd, language: "bash" } : undefined;
    },
  },
  Read:      { icon: FileText,         getLabel: fieldLabel("description"), getStatus: errorStatus },
  Write:     { icon: FilePen,          getLabel: fieldLabel("description"), getStatus: errorStatus },
  Edit:      { icon: Pencil,           getLabel: fieldLabel("description"), getStatus: errorStatus },
  Glob:      { icon: FolderSearch,     getLabel: fieldLabel("description"), getStatus: errorStatus },
  Grep:      { icon: FileSearchCorner, getLabel: fieldLabel("description"), getStatus: errorStatus },
  WebSearch: {
    icon: Globe,
    getLabel: fieldLabel("query", (v) => `Search "${v}"`, "Search"),
    resultTarget: "custom-inline",
    ResultComponent: WebSearchResult,
    getStatus: errorStatus,
  },
  WebFetch: {
    icon: Globe,
    getLabel: (input, argsText?) => {
      const url = extractUrl(input, argsText);
      if (url) {
        const host = tryHostname(url);
        return host ? `Fetch ${host}` : `Fetch ${url}`;
      }
      return "Fetch";
    },
    getIconDomain: (input, argsText?) => {
      if (!isDomainComplete(input, argsText)) return undefined;
      const url = extractUrl(input, argsText);
      if (!url) return undefined;
      const host = tryHostname(url);
      return host ? { domain: host, siteUrl: url } : undefined;
    },
    getIconFallback: (input, argsText?) => {
      const url = extractUrl(input, argsText);
      if (url) {
        const host = tryHostname(url) || url;
        const base = host.replace(/^www\./, "");
        return {
          letter: (base[0] || "?").toUpperCase(),
          color: letterColor(base),
        };
      }
      return undefined;
    },
    getStatus: errorStatus,
    getClickUrl: (input) => {
      if (typeof input.url === "string" && input.url) return input.url;
      return undefined;
    },
    noFoldBody: true,
  },
  Agent:     { icon: Bot, getStatus: errorStatus },
  Skill:     { icon: ScrollText, getLabel: fieldLabel("skill", (v) => `Launch skill "${v}"`, "Launch skill"), noFoldBody: true, getStatus: errorStatus },
  TodoWrite: { icon: ListTodo, resultTarget: "sidebar", getLabel: () => "Update todo list", noFoldBody: true, getStatus: errorStatus },
  PresentToUser: {
    icon: FileOutput,
    getLabel: (input, argsText?) => {
      const paths = input.filepaths as string[] | undefined;
      if (paths && paths.length > 0) {
        return `Present ${paths.length} file${paths.length > 1 ? "s" : ""}`;
      }
      if (argsText) {
        const count = countPartialArrayItems(argsText, "filepaths");
        if (count && count > 0) {
          return `Present ${count} file${count > 1 ? "s" : ""}`;
        }
      }
      return "Present files";
    },
    noFoldBody: true,
    getStatus: errorStatus,
  },
};
