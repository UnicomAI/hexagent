import { useRef, useEffect, useState, useCallback } from "react";
import { ChevronRight, Check, X, ExternalLink } from "lucide-react";
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
} from "../tools";
import { useFavicon } from "../tools/useFavicon";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { ToolCall } from "../types";

interface ToolCallBlockProps {
  toolCall: ToolCall;
}

export default function ToolCallBlock({ toolCall }: ToolCallBlockProps) {
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
    : "Tool";
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
    : (isStreaming ? (toolCall.argsText || "") : formatInput(toolCall));

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

  // Auto-scroll streaming args box
  useEffect(() => {
    if (isStreaming && argsBoxRef.current) {
      argsBoxRef.current.scrollTop = argsBoxRef.current.scrollHeight;
    }
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
          {isStreaming && <span className="tool-status is-running">Streaming...</span>}
          {isRunning && <span className="tool-status is-running">Running...</span>}
          {isDone && (
            customStatus ? (
              <span className={`tool-status ${customStatus.className}`}>
                {isFailed ? <X size={13} /> : <Check size={13} />}
                {customStatus.text}
              </span>
            ) : (
              <span className="tool-status is-done">
                <Check size={13} />
                Done
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
                      <div className="tool-box" ref={argsBoxRef}>
                        <div className="tool-box-label">Request</div>
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
                        {isStreaming && <span className="streaming-cursor" />}
                      </div>
                    ) : argsContent ? (
                      <div className="tool-box" ref={argsBoxRef}>
                        <div className="tool-box-label">Request</div>
                        <pre className="tool-pre">
                          <code>{argsContent}</code>
                          {isStreaming && <span className="streaming-cursor" />}
                        </pre>
                      </div>
                    ) : null}
                    {revealOutput && isDone && (
                      <div className="tool-box">
                        <div className="tool-box-label">Response</div>
                        <pre className="tool-pre">
                          {cleanOutput
                            ? <code>{cleanOutput}</code>
                            : <code className="tool-output-empty">(empty)</code>
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

function formatInput(toolCall: ToolCall): string {
  if (toolCall.argsText) return toolCall.argsText;
  const str = JSON.stringify(toolCall.input, null, 2);
  return str === "{}" ? "" : str;
}
