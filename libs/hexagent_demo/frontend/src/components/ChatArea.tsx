import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { PanelRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAppContext } from "../store";
import { getVMStatus } from "../api";
import WelcomeScreen from "./WelcomeScreen";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import FilePreview from "./FilePreview";
import type { Attachment, Conversation, ConversationMode, ContentBlock, SubagentContentBlock } from "../types";

const EMPTY_BLOCKS: ContentBlock[] = [];

interface ChatAreaProps {
  conversation: Conversation | null;
  onSendMessage: (content: string, options?: { workingDir?: string; attachments?: Attachment[] }) => void;
  onOpenSettings: (tab?: string) => void;
  rightPanel?: React.ReactNode;
}

export default function ChatArea({ conversation, onSendMessage, onOpenSettings, rightPanel }: ChatAreaProps) {
  const { t } = useTranslation("chat");
  const { state, dispatch } = useAppContext();
  const [editingTitle, setEditingTitle] = useState(false);
  const chatAreaRef = useRef<HTMLDivElement>(null);

  const streamingEntry = conversation?.id
    ? state.streamingByConversation[conversation.id]
    : undefined;
  const thisConvStreaming = !!streamingEntry;
  const hasMessages = !!conversation && (
    (conversation.messages && conversation.messages.length > 0) ||
    thisConvStreaming
  );

  // Only consider streaming blocks that belong to this conversation (stable ref when not streaming)
  const activeStreamingBlocks = useMemo(
    () => streamingEntry?.blocks ?? EMPTY_BLOCKS,
    [streamingEntry?.blocks],
  );

  // Check if conversation has any PresentToUser or TodoWrite tool calls
  const hasPresentedFiles = useMemo(() => {
    const has = (blocks: (ContentBlock | SubagentContentBlock)[]): boolean =>
      blocks.some((b) => {
        if (b.type === "tool_call" && b.tool.name === "PresentToUser") return true;
        if (b.type === "subagent") return has(b.subagent.blocks);
        return false;
      });
    return (conversation?.messages?.some((m) => m.blocks && has(m.blocks)) ?? false)
      || (activeStreamingBlocks.length > 0 && has(activeStreamingBlocks));
  }, [conversation?.messages, activeStreamingBlocks]);

  const hasTodoWrite = useMemo(() => {
    const has = (blocks: (ContentBlock | SubagentContentBlock)[]): boolean =>
      blocks.some((b) => {
        if (b.type === "tool_call" && b.tool.name === "TodoWrite") return true;
        if (b.type === "subagent") return has(b.subagent.blocks);
        return false;
      });
    return (conversation?.messages?.some((m) => m.blocks && has(m.blocks)) ?? false)
      || (activeStreamingBlocks.length > 0 && has(activeStreamingBlocks));
  }, [conversation?.messages, activeStreamingBlocks]);

  // Auto-show right panel (once per conversation) when relevant tools are first detected
  useEffect(() => {
    if (!conversation) return;
    if (hasPresentedFiles || hasTodoWrite) {
      dispatch({ type: "AUTO_SHOW_RIGHT_PANEL", payload: conversation.id });
    }
  }, [hasPresentedFiles, hasTodoWrite, conversation?.id, dispatch]);

  // Mode: use conversation's mode if it has one, otherwise the global selection
  const currentMode = conversation?.mode || state.selectedMode;

  const isMac = navigator.platform.toUpperCase().includes("MAC");
  const isChatAvailable = !!state.serverConfig?.sandbox?.chat_enabled && !!state.serverConfig?.sandbox?.e2b_api_key;

  const handleModeChange = useCallback(
    async (mode: ConversationMode) => {
      if (mode === "cowork") {
        try {
          const vs = await getVMStatus();
          dispatch({ type: "SET_VM_STATUS", payload: vs });
        } catch {
          // Best-effort refresh; keep UX responsive.
        }
      }
      dispatch({ type: "SET_SELECTED_MODE", payload: mode });
    },
    [dispatch]
  );

  // Keyboard shortcuts: Cmd/Ctrl+Shift+1 鈫?Chat, Cmd/Ctrl+Shift+2 鈫?Cowork
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const mod = isMac ? e.metaKey : e.ctrlKey;
      if (!mod || !e.shiftKey) return;
      if ((e.key === "1" || e.key === "!") && isChatAvailable) {
        e.preventDefault();
        handleModeChange("chat");
      } else if (e.key === "2" || e.key === "@") {
        e.preventDefault();
        handleModeChange("cowork");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isMac, handleModeChange, isChatAvailable]);

  const handleTitleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (!conversation) return;
      dispatch({
        type: "UPDATE_CONVERSATION_TITLE",
        payload: { id: conversation.id, title: e.target.value },
      });
    },
    [conversation, dispatch]
  );

  const handleTitleBlur = useCallback(() => {
    setEditingTitle(false);
  }, []);

  const handleTitleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        setEditingTitle(false);
      }
    },
    []
  );

  return (
    <div className="main-content" data-mode={currentMode}>
      <div className="chat-header">
        {hasMessages && conversation && (
          <input
            className="chat-title"
            value={conversation.title}
            onChange={handleTitleChange}
            onFocus={() => setEditingTitle(true)}
            onBlur={handleTitleBlur}
            onKeyDown={handleTitleKeyDown}
            readOnly={!editingTitle}
            onClick={() => setEditingTitle(true)}
          />
        )}

        {isChatAvailable && (
          <div className="mode-toggle" data-active={currentMode}>
            {(["chat", "cowork"] as ConversationMode[]).map((mode, idx) => (
              <button
                key={mode}
                className={`mode-toggle-btn custom-tooltip-trigger ${currentMode === mode ? "mode-toggle-btn--active" : ""}`}
                onClick={() => handleModeChange(mode)}
                type="button"
              >
                {t(`mode.${mode}`)}
                <span className="custom-tooltip">
                  {t(`mode.${mode}`)}
                  <span className="custom-tooltip-shortcut">{isMac ? "鈬р寴" : "Ctrl+Shift+"}{idx + 1}</span>
                </span>
              </button>
            ))}
          </div>
        )}

        {hasMessages && (
          <div className="header-panel-toggles">
            <button
              className="right-panel-toggle"
              onClick={() => dispatch({ type: "SET_RIGHT_PANEL", payload: !(state.rightPanelByConversation[conversation?.id ?? ""] ?? false) })}
              title={t("toggleSidePanel")}
            >
              <PanelRight />
            </button>
          </div>
        )}
      </div>

      <div className="main-content-body">
        <div className="chat-area" ref={chatAreaRef}>
          <div className="chat-area-content">
            {!hasMessages ? (
              <WelcomeScreen onSubmit={onSendMessage} mode={currentMode} onOpenSettings={onOpenSettings} />
            ) : (
              <>
                <MessageList conversation={conversation} scrollContainerRef={chatAreaRef} />
                <ChatInput conversationId={conversation!.id} onSend={onSendMessage} scrollContainerRef={chatAreaRef} onOpenSettings={onOpenSettings} />
              </>
            )}
          </div>
        </div>
        {hasMessages && state.filePreview && state.filePreview.conversationId === conversation?.id && <FilePreview visible={state.filePreviewVisible} />}
        {hasMessages && rightPanel}
      </div>
    </div>
  );
}
