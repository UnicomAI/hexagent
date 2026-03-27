import { useRef, useEffect, useLayoutEffect, useState, useCallback } from "react";
import { ChevronRight, Check, X, ExternalLink } from "lucide-react";
import { useTranslation } from "../i18n";
import {
  getToolIcon,
  getToolLabel,
  getResultTarget,
  getResultComponent,
  getIconFallback,
  getStatus,
  getClickUrl,
  hasNoFoldBody,
  getIconDomain,
  getInputContent,
  isBuiltinTool,
} from "../tools";
import { useFavicon } from "../tools/useFavicon";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { ToolCall } from "../types";

interface ToolCallBlockProps {
  toolCall: ToolCall;
}

export default function ToolCallBlock({ toolCall }: ToolCallBlockProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const userToggled = useRef(false);
  const argsBoxRef = useRef<HTMLDivElement>(null);
  const foldBodyRef = useRef<HTMLDivElement>(null);
  // When true, the expand animation has finished and we're waiting to auto-fold.
  const pendingFold = useRef(false);
  // Output is only rendered once the user manually re-expands after completion.
  const [revealOutput, setRevealOutput] = useState(false);

  const isStreaming = !!toolCall.streaming;
  const isRunning = !isStreaming && toolCall.output === undefined;
  const isDone = toolCall.output !== undefined;
  const resultTarget = getResultTarget(toolCall.name);
  const isSidebarResult = resultTarget === "sidebar";
  const isCustomInline = resultTarget === "custom-inline";
  const CustomResult = getResultComponent(toolCall.name);
  const noBody = hasNoFoldBody(toolCall.name);

  const label = toolCall.name
    ? getToolLabel(toolCall.name, toolCall.input, toolCall.argsText)
    : t("tool.tool");
  const FallbackIcon = getToolIcon(toolCall.name);
  const iconDomain = getIconDomain(toolCall.name, toolCall.input, toolCall.argsText);
  const iconFallback = getIconFallback(toolCall.name, toolCall.input, toolCall.argsText);
  const clickUrl = getClickUrl(toolCall.name, toolCall.input);
  const showExternalLink = clickUrl || iconDomain;
  const cleanOutput = isDone && toolCall.output ? stripSystemTags(toolCall.output) : undefined;
  const customStatus = isDone && toolCall.output ? getStatus(toolCall.name, toolCall.output) : undefined;

  // Favicon loading with cascading fallback
  const faviconSiteUrl = iconDomain?.siteUrl;
  const favicon = useFavicon(iconDomain?.domain, faviconSiteUrl);

  const inputContent = getInputContent(toolCall.name, toolCall.input, toolCall.argsText);
  const argsContent = inputContent
    ? undefined
    : (isStreaming ? stripBuiltinDescription(toolCall.name, toolCall.argsText || "") : formatInput(toolCall));

  // Auto-expand when streaming or running (skip for sidebar, no-body, and custom-inline tools)
  useEffect(() => {
    if (isSidebarResult || noBody || isCustomInline) return;
    if (isStreaming || isRunning) {
      setExpanded(true);
      pendingFold.current = false;
      userToggled.current = false;
      setRevealOutput(false);
    }
  }, [isStreaming, isRunning, isSidebarResult, noBody, isCustomInline]);

  // Custom-inline tools: auto-expand and reveal results when output arrives (no auto-fold)
  useEffect(() => {
    if (!isCustomInline || !isDone || userToggled.current) return;
    setExpanded(true);
    setRevealOutput(true);
  }, [isCustomInline, isDone]);

  // When tool completes, schedule a fold (skip for custom-inline — they stay open)
  useEffect(() => {
    if (isCustomInline) return;
    if (isDone && !userToggled.current) {
      pendingFold.current = true;
      // If the fold-body is not currently animating (expand already finished),
      // fold immediately — onTransitionEnd won't fire for an already-settled element.
      const el = foldBodyRef.current;
      if (el) {
        const running = el.getAnimations().some((a) => a.playState === "running");
        if (!running) {
          pendingFold.current = false;
          setExpanded(false);
        }
      }
    }
  }, [isDone, isCustomInline]);

  // When the fold-body's expand transition ends, execute the pending fold.
  const handleTransitionEnd = useCallback((e: React.TransitionEvent) => {
    if (e.target !== foldBodyRef.current) return;
    if (pendingFold.current) {
      pendingFold.current = false;
      setExpanded(false);
    }
  }, []);

  // Persist scroll position across SyntaxHighlighter re-renders (which recreate the <pre>)
  const lastScrollLeft = useRef(0);

  // useLayoutEffect runs before paint, so the new <pre> gets scrolled before the user sees it
  useLayoutEffect(() => {
    if (!isStreaming || !argsBoxRef.current) {
      lastScrollLeft.current = 0;
      return;
    }
    const pre = argsBoxRef.current.querySelector<HTMLPreElement>(".tool-pre");
    if (!pre) return;
    const maxScroll = pre.scrollWidth - pre.clientWidth;
    const target = Math.max(lastScrollLeft.current, maxScroll);
    pre.scrollTop = pre.scrollHeight;
    pre.scrollLeft = target;
    lastScrollLeft.current = target;
  }, [isStreaming, toolCall.argsText]);

  const handleToggle = () => {
    // If there's a click URL and tool is done, open it instead
    if (clickUrl) {
      window.open(clickUrl, "_blank", "noopener,noreferrer");
      return;
    }
    if (noBody) return;
    userToggled.current = true;
    pendingFold.current = false;
    const next = !expanded;
    setExpanded(next);
    if (next && isDone) {
      setRevealOutput(true);
    }
  };

  const isFailed = customStatus?.className === "is-failed";

  // Determine which icon to render
  let iconElement: React.ReactNode;
  if (favicon.src) {
    iconElement = <img className="fold-icon-img" src={favicon.src} alt="" />;
  } else if (favicon.showFallback && iconFallback) {
    iconElement = (
      <span
        className="fold-icon-img fold-icon-letter"
        style={{ background: iconFallback.color }}
      >
        {iconFallback.letter}
      </span>
    );
  } else if (iconDomain) {
    // Still loading — show empty placeholder to avoid layout shift
    iconElement = <span className="fold-icon-img" />;
  } else {
    iconElement = <FallbackIcon />;
  }

  return (
    <div className="fold-block">
      <div className="fold-icon">
        {iconElement}
      </div>
      <button className="fold-header" onClick={handleToggle}>
        <span className="fold-label">
          {label}
          {showExternalLink && <ExternalLink size={12} className="fold-external-link" />}
        </span>
        <span className="fold-meta">
          {isStreaming && <span className="tool-status is-streaming">{t("tool.streaming")}<AnimatedDots /></span>}
          {isRunning && <span className="tool-status is-running">{t("tool.running")}<AnimatedDots /></span>}
          {isDone && (
            customStatus ? (
              <span className={`tool-status ${customStatus.className}`}>
                {isFailed ? <X size={13} /> : <Check size={13} />}
                {customStatus.text}
              </span>
            ) : (
              <span className="tool-status is-done">
                <Check size={13} />
                {t("tool.done")}
              </span>
            )
          )}
          <ChevronRight className={`fold-chevron ${expanded ? "rotated" : ""}`} />
        </span>
      </button>

      {!noBody && (
        <div
          ref={foldBodyRef}
          className={`fold-body ${expanded ? "expanded" : ""}`}
          onTransitionEnd={handleTransitionEnd}
        >
          <div className="fold-body-clip">
            <div className="fold-body-grid">
              <div className="fold-line" />
              <div className="tool-content">
                {/* Custom inline renderer replaces raw input/output */}
                {CustomResult && revealOutput && isDone && cleanOutput ? (
                  <CustomResult output={cleanOutput} input={toolCall.input} />
                ) : (
                  <>
                    {inputContent ? (
                      <div className={`tool-box${isStreaming ? " is-streaming" : ""}`} ref={argsBoxRef}>
                        <div className="tool-box-label">{t("common.request")}</div>
                        <SyntaxHighlighter
                          language={inputContent.language}
                          style={isDarkTheme() ? oneDark : oneLight}
                          PreTag={({ children, ...rest }: React.HTMLAttributes<HTMLPreElement>) => (
                            <pre {...rest} className="tool-pre">{children}</pre>
                          )}
                          customStyle={{ background: "transparent", margin: 0, padding: 0 }}
                          codeTagProps={{ style: { fontFamily: "inherit", fontSize: "inherit" } }}
                        >
                          {inputContent.text}
                        </SyntaxHighlighter>
                      </div>
                    ) : argsContent ? (
                      <div className={`tool-box${isStreaming ? " is-streaming" : ""}`} ref={argsBoxRef}>
                        <div className="tool-box-label">{t("common.request")}</div>
                        <SyntaxHighlighter
                          language="json"
                          style={isDarkTheme() ? oneDark : oneLight}
                          PreTag={({ children, ...rest }: React.HTMLAttributes<HTMLPreElement>) => (
                            <pre {...rest} className="tool-pre">{children}</pre>
                          )}
                          customStyle={{ background: "transparent", margin: 0, padding: 0 }}
                          codeTagProps={{ style: { fontFamily: "inherit", fontSize: "inherit" } }}
                        >
                          {argsContent}
                        </SyntaxHighlighter>
                      </div>
                    ) : null}
                    {revealOutput && isDone && (
                      <div className="tool-box">
                        <div className="tool-box-label">{t("common.response")}</div>
                        <pre className="tool-pre">
                          {cleanOutput
                            ? <code>{cleanOutput}</code>
                            : <code className="tool-output-empty">{t("common.empty")}</code>
                          }
                        </pre>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Animated ellipsis that cycles through ., .., ... */
function AnimatedDots() {
  const [count, setCount] = useState(1);
  useEffect(() => {
    const id = setInterval(() => setCount((c) => (c % 3) + 1), 400);
    return () => clearInterval(id);
  }, []);
  // Use a fixed-width wrapper so the text doesn't shift
  return <span style={{ display: "inline-block", width: "1.2em", textAlign: "left" }}>{".".repeat(count)}</span>;
}

/** Strip internal system tags from tool output for display. */
function stripSystemTags(text: string): string {
  return text
    .replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, "")
    .replace(/<system>[\s\S]*?<\/system>/g, "")
    .trim();
}

function isDarkTheme(): boolean {
  return document.documentElement.getAttribute("data-theme") !== "light";
}

/** Strip the "description" field from raw JSON text for built-in tools.
 *  Handles partial streaming: if description value is still being streamed,
 *  hide everything from the field start onward until it completes. */
function stripBuiltinDescription(name: string, text: string): string {
  if (!isBuiltinTool(name) || !text) return text;

  // Match the start of a "description" field (as first key or later key)
  // Handles both: `{ "description": ...` and `..., "description": ...`
  const patterns = [
    /^\s*\{\s*"description"\s*:\s*/, // first key
    /,\s*"description"\s*:\s*/,      // non-first key
  ];

  for (const pattern of patterns) {
    const match = pattern.exec(text);
    if (!match) continue;
    const valueStart = match.index + match[0].length;

    // Check if the value is a string starting with "
    if (text[valueStart] !== '"') continue;

    // Find end of string value (handling escapes)
    let i = valueStart + 1;
    let closed = false;
    while (i < text.length) {
      if (text[i] === '\\') { i += 2; continue; }
      if (text[i] === '"') { closed = true; i++; break; }
      i++;
    }

    if (!closed) {
      // Description value is still being streamed — hide from field start onward
      const before = text.slice(0, match.index);
      // If it was the first key, keep just "{"
      if (pattern === patterns[0]) return before + "{";
      return before;
    }

    // Value is complete — skip optional trailing comma/whitespace
    if (i < text.length && /[\s,]/.test(text[i])) {
      while (i < text.length && /[\s,]/.test(text[i])) i++;
    }

    // Reconstruct without the description field
    const before = text.slice(0, match.index);
    const after = text.slice(i);
    // If it was the first key, rejoin as `{ <after>`
    if (pattern === patterns[0]) {
      text = before + "{" + after;
    } else {
      text = before + (after ? ", " + after : after);
    }
    // Don't break — re-check in case there's another occurrence (unlikely but safe)
  }

  return text;
}

function formatInput(toolCall: ToolCall): string {
  if (toolCall.argsText) return stripBuiltinDescription(toolCall.name, toolCall.argsText);
  let input = toolCall.input;
  if (isBuiltinTool(toolCall.name) && "description" in input) {
    const { description: _, ...rest } = input;
    input = rest;
  }
  const str = JSON.stringify(input, null, 2);
  return str === "{}" ? "" : str;
}
