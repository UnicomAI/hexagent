import { useState, useCallback, useRef } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { Copy, Check } from "lucide-react";
import { useSyntaxTheme } from "../hooks/useSyntaxTheme";

interface CodeBlockProps {
  language?: string;
  children: string;
  /** Extra action buttons rendered alongside the copy button (inside the sticky anchor) */
  extraActions?: React.ReactNode;
}

export default function CodeBlock({ language, children, extraActions }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard not available
    }
  }, [children]);

  const containerRef = useRef<HTMLDivElement>(null);
  const scrollTimer = useRef<ReturnType<typeof setTimeout>>(null);

  const handleScroll = useCallback(() => {
    containerRef.current?.classList.add("scrolling");
    if (scrollTimer.current) clearTimeout(scrollTimer.current);
    scrollTimer.current = setTimeout(() => {
      containerRef.current?.classList.remove("scrolling");
    }, 1000);
  }, []);

  const theme = useSyntaxTheme();

  return (
    <div className="code-block" ref={containerRef} onScroll={handleScroll}>
      <div className="code-block-copy-anchor">
        <div className="code-block-actions">
          {extraActions}
          <button
            className="code-block-action-btn"
            onClick={handleCopy}
            title="Copy code"
          >
            {copied ? <Check /> : <Copy />}
          </button>
        </div>
      </div>
      <div className="code-block-header">
        <span className="code-block-lang">{language || "text"}</span>
      </div>
      <SyntaxHighlighter
        language={language || "text"}
        style={theme}
        customStyle={{
          background: "transparent",
          margin: 0,
        }}
        codeTagProps={{
          style: {
            fontFamily: "var(--font-mono)",
            fontSize: "var(--font-xs)",
          },
        }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  );
}
