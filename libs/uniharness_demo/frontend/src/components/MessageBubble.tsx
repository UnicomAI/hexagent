import { useState, useCallback, useMemo, forwardRef } from "react";
import { Copy, Check, FileText } from "lucide-react";
import Markdown from "./Markdown";
import ToolCallBlock from "./ToolCallBlock";
import SubagentBlock from "./SubagentBlock";
import ThinkingBlock from "./ThinkingBlock";
import PresentFilesResult from "../tools/renderers/PresentFilesResult";
import type { Message, ContentBlock } from "../types";

interface MessageBubbleProps {
  message: Message;
  streamingBlocks?: ContentBlock[];
  isStreaming?: boolean;
  isLastAssistant?: boolean;
}

const MessageBubble = forwardRef<HTMLDivElement, MessageBubbleProps>(function MessageBubble({ message, streamingBlocks, isStreaming, isLastAssistant }, ref) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard not available
    }
  }, [message.content]);

  const isUser = message.role === "user";
  const blocks = streamingBlocks ?? message.blocks;
  const hasContent = blocks ? blocks.length > 0 : !!message.content;
  const showActions = hasContent && !isStreaming;

  // Collect completed PresentToUser tool outputs and merge into a single string
  // so all files from the same message render in one unified list
  const presentedFilesOutput = useMemo(() => {
    if (isUser || !blocks) return "";
    return collectPresentFilesOutputs(blocks).join("\n");
  }, [isUser, blocks]);

  const dateObj = new Date(message.created_at);
  const timeStr = isNaN(dateObj.getTime()) ? "" : dateObj.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  return (
    <div ref={ref} className={`message-row ${isUser ? "user" : "assistant"}`}>
      <div className={`message-bubble ${isUser ? "user" : "assistant"}`}>
        {isUser ? (
          <>
            {message.attachments && message.attachments.length > 0 && (
              <div className="message-attachments">
                {message.attachments.map((a, i) => (
                  <div key={i} className="message-attachment-chip">
                    <FileText className="message-attachment-icon" />
                    <span>{a.filename}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="message-content" style={{ whiteSpace: "pre-wrap" }}>
              {message.content.replace(/\n?\n?\[Attached file: [^\]]+\]/g, "").trim()}
            </div>
          </>
        ) : (
          <AssistantContent blocks={blocks} message={message} isStreaming={isStreaming} />
        )}
      </div>

      {presentedFilesOutput && (
        <div className="present-files-section">
          <PresentFilesResult output={presentedFilesOutput} input={{}} />
        </div>
      )}

      {showActions && (
        <div className={`message-actions ${isUser ? "user" : "assistant"} ${isLastAssistant ? "always-visible" : ""}`}>
          {isUser && <span className="message-time">{timeStr}</span>}
          <button className="message-action-btn" onClick={handleCopy} title="Copy message">
            {copied ? <Check /> : <Copy />}
          </button>
        </div>
      )}
    </div>
  );
});

export default MessageBubble;

/** Collect output strings from completed PresentToUser tool calls in blocks. */
function collectPresentFilesOutputs(blocks: ContentBlock[]): string[] {
  const outputs: string[] = [];
  for (const b of blocks) {
    if (b.type === "tool_call" && b.tool.name === "PresentToUser" && b.tool.output) {
      outputs.push(b.tool.output);
    }
    if (b.type === "subagent") {
      for (const sb of b.subagent.blocks) {
        if (sb.type === "tool_call" && sb.tool.name === "PresentToUser" && sb.tool.output) {
          outputs.push(sb.tool.output);
        }
      }
    }
  }
  return outputs;
}

/** Show breathing dot when waiting for model response (no blocks yet, or all tools completed). */
function showWaitingIndicator(blocks: ContentBlock[] | undefined): boolean {
  if (!blocks || blocks.length === 0) return true;
  const last = blocks[blocks.length - 1];
  // All tools done — waiting for next model call
  if (last.type === "tool_call" && last.tool.output !== undefined) return true;
  // Subagent done
  if (last.type === "subagent" && last.subagent.parent_tool.output !== undefined) return true;
  // Tool call in progress — don't show dot
  if (last.type === "tool_call" && last.tool.output === undefined) return false;
  if (last.type === "subagent" && last.subagent.parent_tool.output === undefined) return false;
  return false;
}

function AssistantContent({
  blocks,
  message,
  isStreaming,
}: {
  blocks: ContentBlock[] | undefined;
  message: Message;
  isStreaming?: boolean;
}) {
  return (
    <>
      {blocks ? (
        blocks.map((block, i) => {
          if (block.type === "tool_call") {
            return <ToolCallBlock key={block.tool.id} toolCall={block.tool} />;
          }
          if (block.type === "subagent") {
            return (
              <SubagentBlock
                key={block.subagent.parent_tool.id}
                subagent={block.subagent}
                isStreaming={isStreaming}
              />
            );
          }
          if (block.type === "thinking") {
            return (
              <ThinkingBlock
                key={`thinking-${i}`}
                text={block.text}
                startedAt={block.startedAt}
                endedAt={block.endedAt}
              />
            );
          }
          return (
            <div className="message-content" key={`text-${i}`}>
              <Markdown>{block.text}</Markdown>
            </div>
          );
        })
      ) : message.content ? (
        <div className="message-content">
          <Markdown>{message.content}</Markdown>
        </div>
      ) : null}

      {isStreaming && showWaitingIndicator(blocks) && (
        <div className="streaming-indicator">
          <span className="streaming-cursor" />
        </div>
      )}
    </>
  );
}
