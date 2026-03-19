import { useState, useMemo, useRef, useCallback, useEffect } from "react";
import { ChevronDown } from "lucide-react";
import TodoProgress, { extractTodos } from "../tools/renderers/TodoProgress";
import PresentFilesResult from "../tools/renderers/PresentFilesResult";
import type { Conversation, ContentBlock, ToolCall } from "../types";

interface RightPanelProps {
  visible: boolean;
  conversation: Conversation | null;
  /** Live streaming blocks (for real-time progress during generation). */
  streamingBlocks?: ContentBlock[];
}

export default function RightPanel({ visible, conversation, streamingBlocks }: RightPanelProps) {
  const [progressOpen, setProgressOpen] = useState(true);
  const [artifactsOpen, setArtifactsOpen] = useState(true);
  const progressBodyRef = useRef<HTMLDivElement>(null);
  const progressScrollRef = useRef<HTMLDivElement>(null);

  const allToolCalls = useMemo<ToolCall[]>(() => {
    if (!conversation) return [];
    const calls: ToolCall[] = [];
    for (const m of conversation.messages) {
      if (!m.blocks) continue;
      collectToolCalls(m.blocks, calls);
    }
    return calls;
  }, [conversation]);

  // Also collect tool calls from live streaming blocks
  const streamingToolCalls = useMemo<ToolCall[]>(() => {
    if (!streamingBlocks || streamingBlocks.length === 0) return [];
    const calls: ToolCall[] = [];
    collectToolCalls(streamingBlocks, calls);
    return calls;
  }, [streamingBlocks]);

  const combinedToolCalls = useMemo(
    () => [...allToolCalls, ...streamingToolCalls],
    [allToolCalls, streamingToolCalls],
  );

  // Extract todos from the latest *completed* TodoWrite call.
  // While a new TodoWrite is streaming/running, keep showing the previous result.
  const todos = useMemo(() => {
    const all = combinedToolCalls;
    for (let i = all.length - 1; i >= 0; i--) {
      if (all[i].name === "TodoWrite" && all[i].output !== undefined) {
        return extractTodos(all[i].input);
      }
    }
    return null;
  }, [combinedToolCalls]);

  // Collect all completed PresentToUser outputs, merged into a single string
  const artifactOutput = useMemo(() => {
    const outputs: string[] = [];
    for (const tc of combinedToolCalls) {
      if (tc.name === "PresentToUser" && tc.output) {
        outputs.push(tc.output);
      }
    }
    return outputs.join("\n");
  }, [combinedToolCalls]);

  // Scroll fade shadows for progress section
  const updateFade = useCallback(() => {
    const el = progressScrollRef.current;
    const body = progressBodyRef.current;
    if (!el || !body) return;
    const maxScroll = el.scrollHeight - el.clientHeight;
    if (maxScroll <= 0) {
      body.style.setProperty("--fade-top", "0");
      body.style.setProperty("--fade-bottom", "0");
      return;
    }
    const ramp = 10;
    const t = Math.min(el.scrollTop / ramp, 1);
    const b = Math.min((maxScroll - el.scrollTop) / ramp, 1);
    body.style.setProperty("--fade-top", String(t * t));
    body.style.setProperty("--fade-bottom", String(b * b));
  }, []);

  // Re-evaluate fade when todos change or section expands/collapses.
  // When collapsing, immediately clear shadows. When expanding, wait for
  // the CSS grid transition to finish so scrollHeight is accurate.
  useEffect(() => {
    if (!progressOpen) {
      const body = progressBodyRef.current;
      if (body) {
        body.style.setProperty("--fade-top", "0");
        body.style.setProperty("--fade-bottom", "0");
      }
      return;
    }
    const body = progressBodyRef.current;
    if (!body) {
      requestAnimationFrame(updateFade);
      return;
    }
    const onEnd = () => updateFade();
    body.addEventListener("transitionend", onEnd, { once: true });
    // Also run after a rAF in case transition doesn't fire (e.g. no height change)
    const raf = requestAnimationFrame(updateFade);
    return () => {
      body.removeEventListener("transitionend", onEnd);
      cancelAnimationFrame(raf);
    };
  }, [todos, progressOpen, updateFade]);

  return (
    <div className={`right-panel ${!visible ? "hidden" : ""}`}>
      <div className="right-panel-content">
        {/* Progress section — always shown */}
        <div className="right-panel-section">
          <div
            className="right-panel-section-header"
            onClick={() => setProgressOpen((p) => !p)}
          >
            <span className="right-panel-section-title">Progress</span>
            <span className={`right-panel-section-toggle ${!progressOpen ? "collapsed" : ""}`}>
              <ChevronDown />
            </span>
          </div>
          <div
            ref={progressBodyRef}
            className={`right-panel-section-body ${progressOpen ? "expanded" : ""}`}
          >
            <div
              ref={progressScrollRef}
              className="right-panel-section-body-inner"
              onScroll={updateFade}
            >
              <TodoProgress todos={todos} />
            </div>
          </div>
        </div>

        {/* Artifacts section — shown when PresentToUser has been called */}
        {artifactOutput && (
          <div className="right-panel-section">
            <div
              className="right-panel-section-header"
              onClick={() => setArtifactsOpen((p) => !p)}
            >
              <span className="right-panel-section-title">Artifacts</span>
              <span className={`right-panel-section-toggle ${!artifactsOpen ? "collapsed" : ""}`}>
                <ChevronDown />
              </span>
            </div>
            <div className={`right-panel-section-body ${artifactsOpen ? "expanded" : ""}`}>
              <div className="right-panel-section-body-inner right-panel-artifacts">
                <PresentFilesResult output={artifactOutput} input={{}} />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Collect all tool calls from content blocks (including nested subagent blocks). */
function collectToolCalls(blocks: ContentBlock[], out: ToolCall[]): void {
  for (const b of blocks) {
    if (b.type === "tool_call") {
      out.push(b.tool);
    } else if (b.type === "subagent") {
      out.push(b.subagent.parent_tool);
      for (const sb of b.subagent.blocks) {
        if (sb.type === "tool_call") out.push(sb.tool);
      }
    }
  }
}
