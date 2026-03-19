import { useRef, useState, useEffect } from "react";
import { ChevronRight } from "lucide-react";
import Markdown from "./Markdown";

interface ThinkingBlockProps {
  text: string;
  startedAt?: number;
  endedAt?: number;
}

function formatDuration(startedAt: number, endedAt: number): string {
  const ms = Math.max(0, endedAt - startedAt);
  const totalSec = ms / 1000;
  if (totalSec < 10) return `${Math.max(0.1, totalSec).toFixed(1)}s`;
  if (totalSec < 60) return `${Math.round(totalSec)}s`;
  const min = Math.floor(totalSec / 60);
  const sec = Math.round(totalSec % 60);
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`;
}

export default function ThinkingBlock({ text, startedAt, endedAt }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const userToggled = useRef(false);
  const contentRef = useRef<HTMLDivElement>(null);

  const isActive = !endedAt && !!startedAt;
  const label = isActive
    ? "Thinking ..."
    : startedAt
      ? `Thought for ${formatDuration(startedAt, endedAt!)}`
      : "Thought process";

  // Auto-expand while thinking
  useEffect(() => {
    if (isActive) {
      setExpanded(true);
      userToggled.current = false;
    }
  }, [isActive]);

  // Auto-fold when done (unless user manually toggled)
  useEffect(() => {
    if (!isActive && !userToggled.current) {
      setExpanded(false);
    }
  }, [isActive]);

  // Auto-scroll to bottom while thinking streams
  useEffect(() => {
    if (isActive && expanded && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [text, isActive, expanded]);

  const handleToggle = () => {
    userToggled.current = true;
    setExpanded((p) => !p);
  };

  return (
    <div className="fold-block">
      <button className="fold-header no-icon" onClick={handleToggle}>
        <span className={`thinking-label ${isActive ? "active" : ""}`}>
          {label}
        </span>
        <ChevronRight className={`fold-chevron ${expanded ? "rotated" : ""}`} />
      </button>

      <div className={`fold-body ${expanded ? "expanded" : ""}`}>
        <div className="fold-body-clip">
          <div className="fold-body-grid">
            <div className="fold-line" />
            <div ref={contentRef} className="thinking-content message-content">
              <Markdown>{text}</Markdown>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
