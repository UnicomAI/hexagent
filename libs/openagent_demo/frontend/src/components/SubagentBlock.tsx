import { useState } from "react";
import { ChevronDown, Bot, Check } from "lucide-react";
import Markdown from "./Markdown";
import ThinkingBlock from "./ThinkingBlock";
import ToolIcon from "./ToolIcon";
import type { SubagentState, SubagentContentBlock } from "../types";

interface SubagentBlockProps {
  subagent: SubagentState;
  isStreaming?: boolean;
}

export default function SubagentBlock({ subagent, isStreaming }: SubagentBlockProps) {
  const [collapsed, setCollapsed] = useState(false);

  const description =
    typeof subagent.parent_tool.input.description === "string"
      ? subagent.parent_tool.input.description
      : subagent.task_id;

  const prompt =
    typeof subagent.parent_tool.input.prompt === "string"
      ? subagent.parent_tool.input.prompt
      : "";

  const isComplete = subagent.parent_tool.output !== undefined;
  const hasContent = subagent.blocks.length > 0;
  const isActive = !isComplete && isStreaming;

  return (
    <div className={`subagent-block ${isActive ? "active" : ""}`}>
      <div className="subagent-header" onClick={() => setCollapsed((p) => !p)}>
        <div className="subagent-header-left">
          <div className="subagent-icon">
            <Bot />
          </div>
          <span className="subagent-description">{description}</span>
        </div>
        <div className="subagent-header-right">
          {isActive && <span className="subagent-status-badge active">Running</span>}
          {isComplete && (
            <span className="subagent-status-badge complete">
              <Check className="subagent-done-check" />
              Done
            </span>
          )}
          <ChevronDown
            className={`subagent-chevron ${collapsed ? "collapsed" : ""}`}
          />
        </div>
      </div>

      {!collapsed && (
        <div className="subagent-body">
          {prompt && (
            <div className="subagent-prompt">
              <span className="subagent-prompt-label">Prompt</span>
              <div className="subagent-prompt-text">{prompt.length > 200 ? prompt.slice(0, 200) + "..." : prompt}</div>
            </div>
          )}

          {hasContent && (
            <div className="subagent-content">
              {subagent.blocks.map((block, i) => (
                <SubagentInnerBlock key={i} block={block} />
              ))}
              {isActive && (
                <span className="streaming-cursor" />
              )}
            </div>
          )}

          {!hasContent && isActive && (
            <ThinkingBlock text="" />
          )}
        </div>
      )}
    </div>
  );
}

function SubagentInnerBlock({ block }: { block: SubagentContentBlock }) {
  const [expanded, setExpanded] = useState(false);

  if (block.type === "thinking" && block.text) {
    return (
      <ThinkingBlock
        text={block.text}
        startedAt={block.startedAt}
        endedAt={block.endedAt}
      />
    );
  }

  if (block.type === "text" && block.text) {
    return (
      <div className="subagent-text message-content">
        <Markdown>{block.text}</Markdown>
      </div>
    );
  }

  if (block.type === "tool_call") {
    const tc = block.tool;
    const summary = getToolSummary(tc);
    const hasOutput = tc.output !== undefined;

    return (
      <div className="subagent-tool">
        <div className="subagent-tool-header" onClick={() => setExpanded((p) => !p)}>
          <ToolIcon name={tc.name} className="subagent-tool-icon" />
          <span className="subagent-tool-summary">{summary}</span>
          <div className="subagent-tool-right">
            {hasOutput && (
              <span className="subagent-tool-done">
                <Check className="subagent-tool-done-icon" />
              </span>
            )}
            {!hasOutput && <span className="subagent-tool-running" />}
          </div>
        </div>
        {expanded && (
          <div className="subagent-tool-body">
            <pre className="subagent-tool-json">{JSON.stringify(tc.input, null, 2)}</pre>
            {tc.output !== undefined && (
              <div className="subagent-tool-output">
                {tc.output.length > 500 ? tc.output.slice(0, 500) + "..." : tc.output}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  return null;
}

function getToolSummary(tc: { name: string; input: Record<string, unknown> }): string {
  const input = tc.input;
  const name = tc.name.toLowerCase();

  if ("command" in input && typeof input.command === "string") {
    const cmd = String(input.command);
    return cmd.length > 50 ? cmd.slice(0, 50) + "..." : cmd;
  }
  if ("file_path" in input && typeof input.file_path === "string") {
    const parts = String(input.file_path).split("/");
    const filename = parts[parts.length - 1] || String(input.file_path);
    if (name.includes("read")) return `Read ${filename}`;
    if (name.includes("write") || name.includes("create")) return `Write ${filename}`;
    if (name.includes("edit") || name.includes("patch")) return `Edit ${filename}`;
    return filename;
  }
  if ("query" in input && typeof input.query === "string") {
    const q = String(input.query);
    return q.length > 40 ? q.slice(0, 40) + "..." : q;
  }
  if ("pattern" in input && typeof input.pattern === "string") {
    return `Search ${String(input.pattern)}`;
  }
  return tc.name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
