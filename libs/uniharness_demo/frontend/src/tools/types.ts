/**
 * Tool UI configuration types.
 *
 * Each built-in tool can declare how it should be rendered:
 * icon, label extraction, and where its result appears.
 */

/**
 * Where the tool result should be rendered.
 * - "inline": default fold-body display (raw JSON input/output)
 * - "sidebar": rendered in the right panel (e.g. TodoWrite → Progress)
 * - "custom-inline": replaces the fold body with a custom component (e.g. WebSearch)
 */
export type ResultTarget = "inline" | "sidebar" | "custom-inline";

/** Props passed to custom inline result renderers. */
export interface ResultRendererProps {
  output: string;
  input: Record<string, unknown>;
}

export interface ToolUIConfig {
  /** Lucide icon component for this tool. */
  icon: React.ComponentType<{ className?: string }>;

  /**
   * Extract a human-readable label from tool call input.
   * During streaming, argsText contains the incomplete JSON being accumulated.
   * Return undefined to fall back to the default (formatted tool name).
   */
  getLabel?: (input: Record<string, unknown>, argsText?: string) => string | undefined;

  /**
   * Where this tool's result should be rendered.
   * Defaults to "inline" if not specified.
   */
  resultTarget?: ResultTarget;

  /**
   * Custom component for rendering tool results inline.
   * Only used when resultTarget is "custom-inline".
   */
  ResultComponent?: React.ComponentType<ResultRendererProps>;

  /**
   * Return domain info for favicon loading.
   * The useFavicon hook handles probing /favicon.ico, Google, and DuckDuckGo
   * with cascading fallback and background retry.
   */
  getIconDomain?: (input: Record<string, unknown>, argsText?: string) => { domain: string; siteUrl?: string } | undefined;

  /**
   * Custom status text and style when tool is done.
   * Return undefined to use the default "Done" status.
   */
  getStatus?: (output: string) => { text: string; className: string } | undefined;

  /**
   * Return a URL to open when the header is clicked (after tool is done).
   * When set, clicking the header opens this URL instead of toggling the fold.
   */
  getClickUrl?: (input: Record<string, unknown>) => string | undefined;

  /**
   * Letter fallback when dynamic icon (getIconUrl) fails to load.
   * Returns { letter, color } for a colored circle, or undefined for default icon.
   */
  getIconFallback?: (input: Record<string, unknown>, argsText?: string) => { letter: string; color: string } | undefined;

  /**
   * When true, the fold body is never shown (no expand/collapse).
   */
  noFoldBody?: boolean;

  /**
   * Extract the content to display in the fold body input section.
   * Return { text, language } for syntax-highlighted code blocks,
   * or undefined to fall back to the default raw JSON display.
   * During streaming, argsText contains the incomplete JSON being accumulated.
   */
  getInputContent?: (input: Record<string, unknown>, argsText?: string) => { text: string; language: string } | undefined;
}
