export type ConversationMode = "chat" | "cowork";

export interface Conversation {
  id: string;
  title: string;
  model_id?: string;
  mode?: ConversationMode;
  session_name?: string;
  working_dir?: string;
  messages: Message[];
  created_at: string;
  updated_at: string;
}

export interface Attachment {
  filename: string;
  path: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  blocks?: ContentBlock[];
  attachments?: Attachment[];
  created_at: string;
}

export type ContentBlock =
  | { type: "text"; text: string }
  | { type: "thinking"; text: string; startedAt?: number; endedAt?: number }
  | { type: "tool_call"; tool: ToolCall }
  | { type: "subagent"; subagent: SubagentState };

export interface ToolCall {
  id: string;
  /** Real run_id from tool execution (may differ from id used for React key). */
  runId?: string;
  name: string;
  input: Record<string, unknown>;
  output?: string;
  /** True while the LLM is still streaming tool call arguments. */
  streaming?: boolean;
  /** Raw accumulated JSON string of args (during streaming). */
  argsText?: string;
  /** Tool call index within the LLM response (for multi-tool streaming). */
  streamIndex?: number;
}

export interface SubagentState {
  task_id: string;
  /** Tool call info from the parent Agent tool */
  parent_tool: ToolCall;
  /** Ordered content blocks within the subagent */
  blocks: SubagentContentBlock[];
}

export type SubagentContentBlock =
  | { type: "text"; text: string }
  | { type: "thinking"; text: string; startedAt?: number; endedAt?: number }
  | { type: "tool_call"; tool: ToolCall };
