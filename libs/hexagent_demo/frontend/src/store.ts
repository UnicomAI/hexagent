import { createContext, useContext } from "react";
import type {
  Conversation,
  ConversationMode,
  Message,
  ContentBlock,
  ToolCall,
  SubagentContentBlock,
} from "./types";
import type { ServerConfig, VMStatus } from "./api";

export interface Notification {
  id: string;
  message: string;
  type: "error" | "info" | "success";
}

export interface RestartRequiredModalState {
  open: boolean;
  message: string;
}

export interface StreamingEntry {
  messageId: string;
  blocks: ContentBlock[];
}

export interface AppState {
  conversations: Conversation[];
  activeConversationId: string | null;
  /** Pre-conversation warm session ID (exists before first message). */
  warmSessionId: string | null;
  /** True after user submits until SSE stream starts (or request fails). */
  isRequestPending: boolean;
  /** Per-conversation streaming state. A key exists iff that conversation is streaming. */
  streamingByConversation: Record<string, StreamingEntry>;
  sidebarCollapsed: boolean;
  /** Per-conversation right-panel visibility. */
  rightPanelByConversation: Record<string, boolean>;
  /** Tracks which conversations have already auto-showed the right panel. */
  rightPanelAutoShowed: Record<string, boolean>;
  serverConfig: ServerConfig | null;
  vmStatus: VMStatus | null;
  selectedModelId: string;
  selectedMode: ConversationMode;
  /** Remembers the last active conversation (or null=welcome) per mode. */
  lastActiveByMode: Record<ConversationMode, string | null>;
  notifications: Notification[];
  restartRequiredModal: RestartRequiredModalState;
  filePreview: { path: string; mimeType: string; conversationId: string } | null;
  filePreviewVisible: boolean;
  /** Saved right-panel state before file preview opened (for restore on close). */
  rightPanelBeforePreview: boolean | null;
}

export const initialState: AppState = {
  conversations: [],
  activeConversationId: null,
  warmSessionId: null,
  isRequestPending: false,
  streamingByConversation: {},
  sidebarCollapsed: true,
  rightPanelByConversation: {},
  rightPanelAutoShowed: {},
  serverConfig: null,
  vmStatus: null,
  selectedModelId: "",
  selectedMode: (() => {
    const m = window.location.pathname.match(/^\/(chat|cowork)/);
    return (m ? m[1] : "cowork") as ConversationMode;
  })(),
  lastActiveByMode: { chat: null, cowork: null },
  notifications: [],
  restartRequiredModal: { open: false, message: "" },
  filePreview: null,
  filePreviewVisible: false,
  rightPanelBeforePreview: null,
};

export type Action =
  | { type: "SET_CONVERSATIONS"; payload: Conversation[] }
  | { type: "ADD_CONVERSATION"; payload: Conversation }
  | { type: "DELETE_CONVERSATION"; payload: string }
  | { type: "SET_ACTIVE_CONVERSATION"; payload: string | null }
  | { type: "SET_WARM_SESSION"; payload: string | null }
  | { type: "REQUEST_START" }
  | { type: "REQUEST_END" }
  | { type: "ADD_USER_MESSAGE"; payload: { conversationId: string; message: Message } }
  | { type: "STREAM_START"; payload: { messageId: string; conversationId: string } }
  | { type: "STREAM_TEXT_DELTA"; payload: { conversationId: string; delta: string; ts?: number } }
  | { type: "STREAM_REASONING_DELTA"; payload: { conversationId: string; delta: string; ts?: number } }
  | { type: "STREAM_TOOL_CALL_DELTA"; payload: { conversationId: string; index: number; name?: string; id?: string; args?: string; ts?: number } }
  | { type: "STREAM_TOOL_USE_START"; payload: { conversationId: string; tool: ToolCall & { ts?: number } } }
  | { type: "STREAM_TOOL_RESULT"; payload: { conversationId: string; id: string; output: string } }
  | { type: "STREAM_SUBAGENT_TEXT_DELTA"; payload: { conversationId: string; task_id: string; delta: string } }
  | { type: "STREAM_SUBAGENT_REASONING_DELTA"; payload: { conversationId: string; task_id: string; delta: string } }
  | { type: "STREAM_SUBAGENT_TOOL_CALL_DELTA"; payload: { conversationId: string; task_id: string; index: number; name?: string; id?: string; args?: string } }
  | { type: "STREAM_SUBAGENT_TOOL_START"; payload: { conversationId: string; task_id: string; id: string; name: string; input: Record<string, unknown> } }
  | { type: "STREAM_SUBAGENT_TOOL_RESULT"; payload: { conversationId: string; task_id: string; id: string; output: string } }
  | { type: "STREAM_END"; payload: { conversationId: string; messageId: string } }
  | { type: "STREAM_ERROR"; payload: { conversationId: string; error: string } }
  | { type: "TOGGLE_SIDEBAR" }
  | { type: "SET_SIDEBAR_COLLAPSED"; payload: boolean }
  | { type: "SET_RIGHT_PANEL"; payload: boolean }
  | { type: "AUTO_SHOW_RIGHT_PANEL"; payload: string }
  | { type: "UPDATE_CONVERSATION_TITLE"; payload: { id: string; title: string } }
  | { type: "SET_SERVER_CONFIG"; payload: ServerConfig }
  | { type: "SET_VM_STATUS"; payload: VMStatus }
  | { type: "SET_SELECTED_MODEL"; payload: string }
  | { type: "SET_SELECTED_MODE"; payload: ConversationMode }
  | { type: "SHOW_NOTIFICATION"; payload: { message: string; type: "error" | "info" | "success" } }
  | { type: "DISMISS_NOTIFICATION"; payload: string }
  | { type: "SHOW_RESTART_REQUIRED_MODAL"; payload: { message: string } }
  | { type: "HIDE_RESTART_REQUIRED_MODAL" }
  | { type: "SET_FILE_PREVIEW"; payload: { path: string; mimeType: string; conversationId: string } | null }
  | { type: "SET_FILE_PREVIEW_VISIBLE"; payload: boolean };

// ── Block manipulation helpers ──

function finalizeStreamingTool(blocks: ContentBlock[]): ContentBlock[] {
  const last = blocks[blocks.length - 1];
  if (last && last.type === "tool_call" && last.tool.streaming) {
    const tool = { ...last.tool, streaming: false };
    try {
      if (tool.argsText) tool.input = JSON.parse(tool.argsText);
    } catch {
      // argsText may be incomplete JSON — keep input as-is
    }
    return [...blocks.slice(0, -1), { type: "tool_call", tool }];
  }
  return blocks;
}

function appendTextDelta(blocks: ContentBlock[], delta: string, ts?: number): ContentBlock[] {
  const finalized = finalizeStreamingTool(finalizeThinking(blocks, ts));
  const last = finalized[finalized.length - 1];
  if (last && last.type === "text") {
    return [...finalized.slice(0, -1), { type: "text", text: last.text + delta }];
  }
  return [...finalized, { type: "text", text: delta }];
}

function appendReasoningDelta(blocks: ContentBlock[], delta: string, ts?: number): ContentBlock[] {
  const finalized = finalizeStreamingTool(blocks);
  const last = finalized[finalized.length - 1];
  if (last && last.type === "thinking") {
    return [...finalized.slice(0, -1), { ...last, text: last.text + delta }];
  }
  return [...finalized, { type: "thinking", text: delta, startedAt: ts ?? Date.now() }];
}

/** Mark the last thinking block as ended (if it has no endedAt yet). */
function finalizeThinking(blocks: ContentBlock[], ts?: number): ContentBlock[] {
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i];
    if (b.type === "thinking" && !b.endedAt) {
      const updated = [...blocks];
      updated[i] = { ...b, endedAt: ts ?? Date.now() };
      return updated;
    }
    // Only finalize the most recent thinking block — stop searching once we hit a non-thinking block
    if (b.type !== "thinking") break;
  }
  return blocks;
}

function appendToolCallDelta(
  blocks: ContentBlock[],
  delta: { index: number; name?: string; id?: string; args?: string; ts?: number },
): ContentBlock[] {
  blocks = finalizeThinking(blocks, delta.ts);
  const last = blocks[blocks.length - 1];
  // Append to existing streaming block only if same index
  if (last && last.type === "tool_call" && last.tool.streaming && last.tool.streamIndex === delta.index) {
    const tool = { ...last.tool };
    if (delta.name) tool.name = delta.name;
    if (delta.id) tool.id = delta.id;
    if (delta.args) tool.argsText = (tool.argsText ?? "") + delta.args;
    return [...blocks.slice(0, -1), { type: "tool_call", tool }];
  }
  // Different index or no streaming block — finalize previous and create new
  blocks = finalizeStreamingTool(blocks);
  return [
    ...blocks,
    {
      type: "tool_call",
      tool: {
        id: delta.id ?? `streaming-${delta.index}`,
        name: delta.name ?? "",
        input: {},
        streaming: true,
        argsText: delta.args ?? "",
        streamIndex: delta.index,
      },
    },
  ];
}

function subFinalizeStreamingTool(inner: SubagentContentBlock[]): SubagentContentBlock[] {
  const last = inner[inner.length - 1];
  if (last && last.type === "tool_call" && last.tool.streaming) {
    const tool = { ...last.tool, streaming: false };
    try {
      if (tool.argsText) tool.input = JSON.parse(tool.argsText);
    } catch { /* incomplete JSON */ }
    return [...inner.slice(0, -1), { type: "tool_call", tool }];
  }
  return inner;
}

function subAppendToolCallDelta(
  inner: SubagentContentBlock[],
  delta: { index: number; name?: string; id?: string; args?: string },
): SubagentContentBlock[] {
  inner = subFinalizeThinking(inner);
  const last = inner[inner.length - 1];
  if (last && last.type === "tool_call" && last.tool.streaming && last.tool.streamIndex === delta.index) {
    const tool = { ...last.tool };
    if (delta.name) tool.name = delta.name;
    if (delta.id) tool.id = delta.id;
    if (delta.args) tool.argsText = (tool.argsText ?? "") + delta.args;
    return [...inner.slice(0, -1), { type: "tool_call", tool }];
  }
  inner = subFinalizeStreamingTool(inner);
  return [
    ...inner,
    {
      type: "tool_call",
      tool: {
        id: delta.id ?? `streaming-${delta.index}`,
        name: delta.name ?? "",
        input: {},
        streaming: true,
        argsText: delta.args ?? "",
        streamIndex: delta.index,
      },
    },
  ];
}

function appendToolStart(blocks: ContentBlock[], tool: ToolCall & { ts?: number }): ContentBlock[] {
  blocks = finalizeThinking(blocks, tool.ts);
  blocks = finalizeStreamingTool(blocks);

  // Find existing block: match by id first, then by name (first incomplete one)
  let matchIdx = -1;
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    if (b.type === "tool_call" && b.tool.id === tool.id) {
      matchIdx = i;
      break;
    }
  }
  if (matchIdx === -1) {
    // ID mismatch (streaming id vs run_id) — find first incomplete tool with same name
    // that hasn't already been matched to a run_id (important for parallel tool calls)
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      if (b.type === "tool_call" && b.tool.name === tool.name && b.tool.output === undefined && !b.tool.streaming && !b.tool.runId) {
        matchIdx = i;
        break;
      }
    }
  }
  if (matchIdx !== -1) {
    const updated = [...blocks];
    const existing = (blocks[matchIdx] as { type: "tool_call"; tool: ToolCall }).tool;
    updated[matchIdx] = { type: "tool_call", tool: { ...existing, ...tool, id: existing.id, runId: tool.id, streaming: false, argsText: existing.argsText } };
    if (tool.name !== "Agent") return updated;
    // For Agent, remove the matched block so it can be re-added as subagent below
    updated.splice(matchIdx, 1);
    blocks = updated;
  }
  if (tool.name === "Agent") {
    // If there's already an incomplete subagent block, update it instead of creating a duplicate
    for (let i = blocks.length - 1; i >= 0; i--) {
      const b = blocks[i];
      if (b.type === "subagent" && b.subagent.parent_tool.output === undefined) {
        const updated = [...blocks];
        updated[i] = {
          type: "subagent",
          subagent: {
            ...b.subagent,
            parent_tool: { ...tool, output: undefined },
          },
        };
        return updated;
      }
    }
    const taskId = extractTaskId(tool.input);
    return [
      ...blocks,
      {
        type: "subagent",
        subagent: {
          task_id: taskId,
          parent_tool: tool,
          blocks: [],
        },
      },
    ];
  }
  return [...blocks, { type: "tool_call", tool }];
}

function extractTaskId(input: Record<string, unknown>): string {
  if (typeof input.task_id === "string") return input.task_id;
  if (typeof input.description === "string") return input.description;
  return "subagent";
}

function updateToolResult(blocks: ContentBlock[], id: string, output: string): ContentBlock[] {
  let found = false;
  const updated = blocks.map((b) => {
    if (b.type === "tool_call" && (b.tool.id === id || b.tool.runId === id)) {
      found = true;
      return { type: "tool_call" as const, tool: { ...b.tool, output } };
    }
    if (b.type === "subagent" && b.subagent.parent_tool.id === id) {
      found = true;
      return {
        type: "subagent" as const,
        subagent: {
          ...b.subagent,
          parent_tool: { ...b.subagent.parent_tool, output },
        },
      };
    }
    return b;
  });
  if (found) return updated;

  // Fallback: find the first incomplete block (tool_call or subagent) and mark complete
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i];
    if (b.type === "tool_call" && b.tool.output === undefined) {
      const result = [...blocks];
      result[i] = { type: "tool_call", tool: { ...b.tool, output } };
      return result;
    }
    if (b.type === "subagent" && b.subagent.parent_tool.output === undefined) {
      const result = [...blocks];
      result[i] = {
        type: "subagent",
        subagent: {
          ...b.subagent,
          parent_tool: { ...b.subagent.parent_tool, output },
        },
      };
      return result;
    }
  }
  return blocks;
}

// ── Subagent inner block helpers ──

function findAndUpdateSubagent(
  blocks: ContentBlock[],
  taskId: string,
  updater: (inner: SubagentContentBlock[]) => SubagentContentBlock[],
): ContentBlock[] {
  // Find the subagent block matching the task_id
  // Since task_id from backend may not exactly match our extracted one,
  // we update the most recent subagent block
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i];
    if (b.type === "subagent") {
      const updated = [...blocks];
      updated[i] = {
        type: "subagent",
        subagent: {
          ...b.subagent,
          task_id: taskId,
          blocks: updater(b.subagent.blocks),
        },
      };
      return updated;
    }
  }
  // No subagent found — create one as a fallback
  return [
    ...blocks,
    {
      type: "subagent",
      subagent: {
        task_id: taskId,
        parent_tool: { id: taskId, name: "Agent", input: {} },
        blocks: updater([]),
      },
    },
  ];
}

function subFinalizeThinking(inner: SubagentContentBlock[]): SubagentContentBlock[] {
  for (let i = inner.length - 1; i >= 0; i--) {
    const b = inner[i];
    if (b.type === "thinking" && !b.endedAt) {
      const updated = [...inner];
      updated[i] = { ...b, endedAt: Date.now() };
      return updated;
    }
    if (b.type !== "thinking") break;
  }
  return inner;
}

function subAppendText(inner: SubagentContentBlock[], delta: string): SubagentContentBlock[] {
  const finalized = subFinalizeThinking(inner);
  const last = finalized[finalized.length - 1];
  if (last && last.type === "text") {
    return [...finalized.slice(0, -1), { type: "text", text: last.text + delta }];
  }
  return [...finalized, { type: "text", text: delta }];
}

function subAppendReasoning(inner: SubagentContentBlock[], delta: string): SubagentContentBlock[] {
  const last = inner[inner.length - 1];
  if (last && last.type === "thinking") {
    return [...inner.slice(0, -1), { ...last, text: last.text + delta }];
  }
  return [...inner, { type: "thinking", text: delta, startedAt: Date.now() }];
}

function subAppendTool(inner: SubagentContentBlock[], tool: ToolCall): SubagentContentBlock[] {
  let finalized = subFinalizeThinking(inner);
  // Finalize any streaming tool_call block
  const last = finalized[finalized.length - 1];
  if (last && last.type === "tool_call" && last.tool.streaming) {
    finalized = [...finalized.slice(0, -1), { type: "tool_call", tool: { ...tool, streaming: false } }];
    return finalized;
  }
  return [...finalized, { type: "tool_call", tool }];
}

function subUpdateToolResult(inner: SubagentContentBlock[], id: string, output: string): SubagentContentBlock[] {
  return inner.map((b) => {
    if (b.type === "tool_call" && b.tool.id === id) {
      return { type: "tool_call", tool: { ...b.tool, output } };
    }
    return b;
  });
}

function blocksToContent(blocks: ContentBlock[]): string {
  return blocks
    .filter((b): b is { type: "text"; text: string } => b.type === "text")
    .map((b) => b.text)
    .join("");
}

// ── Per-conversation stream update helper ──

function updateStreamBlocks(
  state: AppState,
  conversationId: string,
  updater: (blocks: ContentBlock[]) => ContentBlock[],
): AppState {
  const entry = state.streamingByConversation[conversationId];
  if (!entry) return state;
  return {
    ...state,
    streamingByConversation: {
      ...state.streamingByConversation,
      [conversationId]: { ...entry, blocks: updater(entry.blocks) },
    },
  };
}

// ── Reducer ──

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "SET_CONVERSATIONS":
      return {
        ...state,
        conversations: action.payload.map((c) => ({
          ...c,
          messages: (c.messages ?? []).map((m) => ({
            ...m,
            created_at: m.created_at || (m as unknown as Record<string, unknown>).timestamp as string || "",
          })),
        })),
      };

    case "ADD_CONVERSATION": {
      const conv = { ...action.payload, messages: action.payload.messages ?? [] };
      const convMode = conv.mode || "chat";
      return {
        ...state,
        conversations: [conv, ...state.conversations],
        activeConversationId: conv.id,
        lastActiveByMode: { ...state.lastActiveByMode, [convMode]: conv.id },
      };
    }

    case "DELETE_CONVERSATION": {
      const filtered = state.conversations.filter((c) => c.id !== action.payload);
      const { [action.payload]: _rpDel, ...restPanel } = state.rightPanelByConversation;
      const { [action.payload]: _asDel, ...restAutoShowed } = state.rightPanelAutoShowed;
      const { [action.payload]: _stDel, ...restStreaming } = state.streamingByConversation;
      return {
        ...state,
        conversations: filtered,
        activeConversationId:
          state.activeConversationId === action.payload
            ? (filtered[0]?.id ?? null)
            : state.activeConversationId,
        rightPanelByConversation: restPanel,
        rightPanelAutoShowed: restAutoShowed,
        streamingByConversation: restStreaming,
      };
    }

    case "SET_ACTIVE_CONVERSATION": {
      const switching = action.payload !== state.activeConversationId && action.payload !== null;
      // When navigating to a different conversation, reset its panel state
      // so auto-show can re-evaluate based on content. Mode switches (SET_SELECTED_MODE)
      // set activeConversationId directly and don't go through here, preserving state.
      const newAutoShowed = switching
        ? (({ [action.payload!]: _, ...rest }) => rest)(state.rightPanelAutoShowed)
        : state.rightPanelAutoShowed;
      const newPanelMap = switching
        ? (({ [action.payload!]: _, ...rest }) => rest)(state.rightPanelByConversation)
        : state.rightPanelByConversation;
      return {
        ...state,
        activeConversationId: action.payload,
        lastActiveByMode: { ...state.lastActiveByMode, [state.selectedMode]: action.payload },
        rightPanelAutoShowed: newAutoShowed,
        rightPanelByConversation: newPanelMap,
        // Clear file preview if it belongs to a different conversation
        ...(switching && state.filePreview && state.filePreview.conversationId !== action.payload
          ? { filePreview: null, filePreviewVisible: false, rightPanelBeforePreview: null }
          : {}),
      };
    }

    case "SET_WARM_SESSION":
      return { ...state, warmSessionId: action.payload };

    case "REQUEST_START":
      return { ...state, isRequestPending: true };

    case "REQUEST_END":
      return { ...state, isRequestPending: false };

    case "ADD_USER_MESSAGE":
      return {
        ...state,
        conversations: state.conversations.map((c) =>
          c.id === action.payload.conversationId
            ? { ...c, messages: [...(c.messages ?? []), action.payload.message] }
            : c
        ),
      };

    case "STREAM_START": {
      const { conversationId: cid, messageId } = action.payload;
      // Check if a message with this ID already exists (reconnect replay).
      // If so, just re-create the streaming entry without adding a duplicate.
      const conv = state.conversations.find((c) => c.id === cid);
      const alreadyExists = conv?.messages?.some((m) => m.id === messageId) ?? false;
      const placeholder: Message = {
        id: messageId,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
      };
      return {
        ...state,
        isRequestPending: false,
        streamingByConversation: {
          ...state.streamingByConversation,
          [cid]: { messageId, blocks: [] },
        },
        conversations: alreadyExists
          ? state.conversations
          : state.conversations.map((c) =>
              c.id === cid
                ? { ...c, messages: [...(c.messages ?? []), placeholder] }
                : c
            ),
      };
    }

    case "STREAM_TEXT_DELTA":
      return updateStreamBlocks(state, action.payload.conversationId, (blocks) =>
        appendTextDelta(blocks, action.payload.delta, action.payload.ts),
      );

    case "STREAM_REASONING_DELTA":
      return updateStreamBlocks(state, action.payload.conversationId, (blocks) =>
        appendReasoningDelta(blocks, action.payload.delta, action.payload.ts),
      );

    case "STREAM_TOOL_CALL_DELTA":
      return updateStreamBlocks(state, action.payload.conversationId, (blocks) =>
        appendToolCallDelta(blocks, action.payload),
      );

    case "STREAM_TOOL_USE_START":
      return updateStreamBlocks(state, action.payload.conversationId, (blocks) =>
        appendToolStart(blocks, action.payload.tool),
      );

    case "STREAM_TOOL_RESULT":
      return updateStreamBlocks(state, action.payload.conversationId, (blocks) =>
        updateToolResult(blocks, action.payload.id, action.payload.output),
      );

    case "STREAM_SUBAGENT_TEXT_DELTA":
      return updateStreamBlocks(state, action.payload.conversationId, (blocks) =>
        findAndUpdateSubagent(blocks, action.payload.task_id, (inner) =>
          subAppendText(inner, action.payload.delta),
        ),
      );

    case "STREAM_SUBAGENT_REASONING_DELTA":
      return updateStreamBlocks(state, action.payload.conversationId, (blocks) =>
        findAndUpdateSubagent(blocks, action.payload.task_id, (inner) =>
          subAppendReasoning(inner, action.payload.delta),
        ),
      );

    case "STREAM_SUBAGENT_TOOL_CALL_DELTA":
      return updateStreamBlocks(state, action.payload.conversationId, (blocks) =>
        findAndUpdateSubagent(blocks, action.payload.task_id, (inner) =>
          subAppendToolCallDelta(inner, action.payload),
        ),
      );

    case "STREAM_SUBAGENT_TOOL_START":
      return updateStreamBlocks(state, action.payload.conversationId, (blocks) =>
        findAndUpdateSubagent(blocks, action.payload.task_id, (inner) =>
          subAppendTool(inner, {
            id: action.payload.id,
            name: action.payload.name,
            input: action.payload.input,
          }),
        ),
      );

    case "STREAM_SUBAGENT_TOOL_RESULT":
      return updateStreamBlocks(state, action.payload.conversationId, (blocks) =>
        findAndUpdateSubagent(blocks, action.payload.task_id, (inner) =>
          subUpdateToolResult(inner, action.payload.id, action.payload.output),
        ),
      );

    case "STREAM_END": {
      const { conversationId: endCid, messageId: endMsgId } = action.payload;
      const entry = state.streamingByConversation[endCid];
      const finalBlocks = entry ? finalizeThinking(entry.blocks) : [];
      const finalContent = blocksToContent(finalBlocks);
      const { [endCid]: _, ...restStreaming } = state.streamingByConversation;
      return {
        ...state,
        isRequestPending: false,
        streamingByConversation: restStreaming,
        conversations: state.conversations.map((c) =>
          c.id === endCid
            ? {
                ...c,
                messages: (c.messages ?? []).map((m) =>
                  m.id === endMsgId
                    ? { ...m, content: finalContent, blocks: finalBlocks.length > 0 ? finalBlocks : undefined }
                    : m
                ),
                updated_at: new Date().toISOString(),
              }
            : c
        ),
      };
    }

    case "STREAM_ERROR": {
      const { conversationId: errCid, error } = action.payload;
      // Append error to the conversation's streaming blocks, then remove from map
      const errEntry = state.streamingByConversation[errCid];
      const errorBlocks = errEntry
        ? appendTextDelta(errEntry.blocks, `\n\n**Error:** ${error}`)
        : [];
      const errFinalContent = blocksToContent(errorBlocks);
      const { [errCid]: __, ...restStreamingErr } = state.streamingByConversation;
      return {
        ...state,
        isRequestPending: false,
        streamingByConversation: restStreamingErr,
        // Persist the error blocks into the message so user can see them
        conversations: errEntry
          ? state.conversations.map((c) =>
              c.id === errCid
                ? {
                    ...c,
                    messages: (c.messages ?? []).map((m) =>
                      m.id === errEntry.messageId
                        ? { ...m, content: errFinalContent, blocks: errorBlocks.length > 0 ? errorBlocks : undefined }
                        : m
                    ),
                  }
                : c
            )
          : state.conversations,
      };
    }

    case "TOGGLE_SIDEBAR":
      return { ...state, sidebarCollapsed: !state.sidebarCollapsed };

    case "SET_SIDEBAR_COLLAPSED":
      return { ...state, sidebarCollapsed: action.payload };

    case "SET_RIGHT_PANEL": {
      const convId = state.activeConversationId;
      if (!convId) return state;
      return {
        ...state,
        rightPanelByConversation: { ...state.rightPanelByConversation, [convId]: action.payload },
      };
    }

    case "AUTO_SHOW_RIGHT_PANEL": {
      const convId = action.payload;
      if (state.rightPanelAutoShowed[convId]) return state;
      return {
        ...state,
        rightPanelByConversation: { ...state.rightPanelByConversation, [convId]: true },
        rightPanelAutoShowed: { ...state.rightPanelAutoShowed, [convId]: true },
      };
    }

    case "UPDATE_CONVERSATION_TITLE":
      return {
        ...state,
        conversations: state.conversations.map((c) =>
          c.id === action.payload.id ? { ...c, title: action.payload.title } : c
        ),
      };

    case "SET_SERVER_CONFIG": {
      const cfg = action.payload;
      const defaultModelId = cfg.models[0]?.id ?? "";
      return {
        ...state,
        serverConfig: cfg,
        selectedModelId: state.selectedModelId || defaultModelId,
      };
    }

    case "SET_VM_STATUS":
      return { ...state, vmStatus: action.payload };

    case "SET_SELECTED_MODEL": {
      const nextState = { ...state, selectedModelId: action.payload };
      if (state.activeConversationId) {
        nextState.conversations = state.conversations.map((c) =>
          c.id === state.activeConversationId ? { ...c, model_id: action.payload } : c
        );
      }
      return nextState;
    }

    case "SET_SELECTED_MODE": {
      const newMode = action.payload;
      if (newMode === state.selectedMode) return state;
      // Save current state for the mode we're leaving
      const savedLast = {
        ...state.lastActiveByMode,
        [state.selectedMode]: state.activeConversationId,
      };
      // Restore the remembered state for the target mode
      const remembered = savedLast[newMode];
      // Validate it still exists (conversation may have been deleted)
      const stillExists = remembered === null || state.conversations.some((c) => c.id === remembered);
      const newActiveId = stillExists ? remembered : null;
      // Clear warm session when switching modes (different session type needed).
      // Preserve file preview & right panel state — UI gates rendering by conversationId.
      return {
        ...state,
        selectedMode: newMode,
        activeConversationId: newActiveId,
        lastActiveByMode: savedLast,
        warmSessionId: null,
      };
    }

    case "SHOW_NOTIFICATION": {
      const note: Notification = {
        id: crypto.randomUUID(),
        message: action.payload.message,
        type: action.payload.type,
      };
      return { ...state, notifications: [...state.notifications, note] };
    }

    case "DISMISS_NOTIFICATION":
      return {
        ...state,
        notifications: state.notifications.filter((n) => n.id !== action.payload),
      };

    case "SHOW_RESTART_REQUIRED_MODAL":
      return {
        ...state,
        restartRequiredModal: {
          open: true,
          message: action.payload.message,
        },
      };

    case "HIDE_RESTART_REQUIRED_MODAL":
      return {
        ...state,
        restartRequiredModal: {
          open: false,
          message: "",
        },
      };

    case "SET_FILE_PREVIEW": {
      const rpConvId = state.activeConversationId;
      const currentPanelVisible = rpConvId ? (state.rightPanelByConversation[rpConvId] ?? false) : false;
      if (action.payload) {
        return {
          ...state,
          filePreview: action.payload,
          filePreviewVisible: true,
          rightPanelBeforePreview: state.rightPanelBeforePreview ?? currentPanelVisible,
          rightPanelByConversation: rpConvId
            ? { ...state.rightPanelByConversation, [rpConvId]: false }
            : state.rightPanelByConversation,
        };
      }
      return {
        ...state,
        filePreview: null,
        filePreviewVisible: false,
        rightPanelByConversation: rpConvId && state.rightPanelBeforePreview === true
          ? { ...state.rightPanelByConversation, [rpConvId]: true }
          : state.rightPanelByConversation,
        rightPanelBeforePreview: null,
      };
    }

    case "SET_FILE_PREVIEW_VISIBLE": {
      const fpvConvId = state.activeConversationId;
      const fpvCurrentPanel = fpvConvId ? (state.rightPanelByConversation[fpvConvId] ?? false) : false;
      if (action.payload) {
        return {
          ...state,
          filePreviewVisible: true,
          rightPanelBeforePreview: state.rightPanelBeforePreview ?? fpvCurrentPanel,
          rightPanelByConversation: fpvConvId
            ? { ...state.rightPanelByConversation, [fpvConvId]: false }
            : state.rightPanelByConversation,
        };
      }
      return {
        ...state,
        filePreviewVisible: false,
        rightPanelByConversation: fpvConvId && state.rightPanelBeforePreview === true
          ? { ...state.rightPanelByConversation, [fpvConvId]: true }
          : state.rightPanelByConversation,
        rightPanelBeforePreview: null,
      };
    }

    default:
      return state;
  }
}

export interface AppContextType {
  state: AppState;
  dispatch: React.Dispatch<Action>;
}

export const AppContext = createContext<AppContextType>({
  state: initialState,
  dispatch: () => {},
});

export function useAppContext() {
  return useContext(AppContext);
}
