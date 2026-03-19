import type { Conversation } from "./types";

const API_BASE = "";

export async function listConversations(): Promise<Conversation[]> {
  const res = await fetch(`${API_BASE}/api/conversations`);
  if (!res.ok) throw new Error(`Failed to list conversations: ${res.statusText}`);
  return res.json();
}

export async function createConversation(
  modelId?: string, mode?: string, workingDir?: string, sessionId?: string,
): Promise<Conversation> {
  const res = await fetch(`${API_BASE}/api/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_id: modelId, mode, working_dir: workingDir, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(`Failed to create conversation: ${res.statusText}`);
  return res.json();
}

export async function getConversation(id: string): Promise<Conversation> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`);
  if (!res.ok) throw new Error(`Failed to get conversation: ${res.statusText}`);
  return res.json();
}

// ── Warm session (pre-conversation) ──

export interface WarmSessionResponse {
  session_id: string;
  mode: string;
  session_name: string | null;
  working_dir: string | null;
}

export async function createWarmSession(mode: string, modelId?: string, workingDir?: string): Promise<WarmSessionResponse> {
  const res = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, model_id: modelId || undefined, working_dir: workingDir || undefined }),
  });
  if (!res.ok) throw new Error(`Failed to create session: ${res.statusText}`);
  return res.json();
}

export async function updateWarmSession(sessionId: string, updates: { working_dir?: string }): Promise<WarmSessionResponse> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`Failed to update session: ${res.statusText}`);
  return res.json();
}

export async function uploadSessionFile(sessionId: string, file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Upload failed: ${res.statusText}`);
  }
  return res.json();
}

export async function deleteSessionFile(sessionId: string, filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/upload/${encodeURIComponent(filename)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Delete failed: ${res.statusText}`);
  }
}

export async function updateConversation(id: string, updates: { title?: string; model_id?: string; working_dir?: string }): Promise<void> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`Failed to update conversation: ${res.statusText}`);
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete conversation: ${res.statusText}`);
}

export interface StreamCallbacks {
  onMessageStart: (id: string) => void;
  onTextDelta: (delta: string) => void;
  onReasoningDelta: (delta: string) => void;
  onToolCallDelta: (data: { index: number; name?: string; id?: string; args?: string }) => void;
  onToolUseStart: (tool: { id: string; name: string; input: Record<string, unknown> }) => void;
  onToolResult: (result: { id: string; output: string }) => void;
  onSubagentTextDelta: (data: { task_id: string; delta: string }) => void;
  onSubagentReasoningDelta: (data: { task_id: string; delta: string }) => void;
  onSubagentToolCallDelta: (data: { task_id: string; index: number; name?: string; id?: string; args?: string }) => void;
  onSubagentToolStart: (data: { task_id: string; id: string; name: string; input: Record<string, unknown> }) => void;
  onSubagentToolResult: (data: { task_id: string; id: string; output: string }) => void;
  onMessageEnd: (id: string) => void;
  onError: (error: string) => void;
}

export function sendMessage(
  conversationId: string,
  content: string,
  callbacks: StreamCallbacks,
  modelId?: string,
  attachments?: { filename: string; path: string }[],
): AbortController {
  const controller = new AbortController();

  fetch(`${API_BASE}/api/chat/${conversationId}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      model_id: modelId,
      attachments: attachments && attachments.length > 0 ? attachments : undefined,
    }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        callbacks.onError(detail?.detail || `HTTP ${response.status}: ${response.statusText}`);
        return;
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ") && currentEvent) {
            try {
              const data = JSON.parse(line.slice(6));
              switch (currentEvent) {
                case "message_start":
                  callbacks.onMessageStart(data.id);
                  break;
                case "text_delta":
                  callbacks.onTextDelta(data.delta);
                  break;
                case "reasoning_delta":
                  callbacks.onReasoningDelta(data.delta);
                  break;
                case "tool_call_delta":
                  callbacks.onToolCallDelta(data);
                  break;
                case "tool_use_start":
                  callbacks.onToolUseStart(data);
                  break;
                case "tool_result":
                  callbacks.onToolResult(data);
                  break;
                case "subagent_text_delta":
                  callbacks.onSubagentTextDelta(data);
                  break;
                case "subagent_reasoning_delta":
                  callbacks.onSubagentReasoningDelta(data);
                  break;
                case "subagent_tool_call_delta":
                  callbacks.onSubagentToolCallDelta(data);
                  break;
                case "subagent_tool_start":
                  callbacks.onSubagentToolStart(data);
                  break;
                case "subagent_tool_result":
                  callbacks.onSubagentToolResult(data);
                  break;
                case "message_end":
                  callbacks.onMessageEnd(data.id);
                  break;
                case "error":
                  callbacks.onError(data.message);
                  break;
              }
            } catch {
              // skip malformed JSON
            }
            currentEvent = "";
          }
        }
      }
    })
    .catch((err: Error) => {
      if (err.name !== "AbortError") {
        callbacks.onError(err.message);
      }
    });

  return controller;
}

// ── File upload ──

export interface UploadResult {
  filename: string;
  path: string;
}

export async function uploadChatFile(conversationId: string, file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/chat/${conversationId}/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Upload failed: ${res.statusText}`);
  }
  return res.json();
}

export async function deleteChatFile(conversationId: string, filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat/${conversationId}/upload/${encodeURIComponent(filename)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Delete failed: ${res.statusText}`);
  }
}

// ── Folder picker ──

export async function browseFolder(): Promise<string | null> {
  const res = await fetch(`${API_BASE}/api/browse-folder`, { method: "POST" });
  if (!res.ok) return null;
  const data = await res.json();
  return data.path || null;
}

// ── Server config ──

export interface ModelConfig {
  id: string;
  display_name: string;
  api_key: string;
  base_url: string;
  model: string;
  provider: string;
  context_window: number;
  supported_modalities: string[];
}

export interface AgentConfig {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  tools: string[];
  model_id: string;
  enabled: boolean;
}

export interface ToolsConfig {
  search_provider: string;
  search_api_key: string;
  fetch_provider: string;
  fetch_api_key: string;
}

export interface SandboxConfig {
  e2b_api_key: string;
}

export interface McpServerEntry {
  id: string;
  name: string;
  type: string;
  url: string;
  command: string;
  args: string;
  env: string;
  headers: string;
  enabled: boolean;
}

export interface ServerConfig {
  models: ModelConfig[];
  main_model_id: string;
  fast_model_id: string;
  agents: AgentConfig[];
  tools: ToolsConfig;
  sandbox: SandboxConfig;
  mcp_servers: McpServerEntry[];
}

export async function getServerConfig(): Promise<ServerConfig> {
  const res = await fetch(`${API_BASE}/api/config`);
  if (!res.ok) throw new Error(`Failed to get config: ${res.statusText}`);
  const data = await res.json();
  return { agents: [], tools: { search_provider: "", search_api_key: "", fetch_provider: "jina", fetch_api_key: "" }, sandbox: { e2b_api_key: "" }, mcp_servers: [], ...data };
}

export async function updateServerConfig(config: ServerConfig): Promise<ServerConfig> {
  const res = await fetch(`${API_BASE}/api/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error(`Failed to update config: ${res.statusText}`);
  return res.json();
}

export async function testMcpConnection(server: McpServerEntry): Promise<{ ok: boolean; tools?: number; error?: string }> {
  const res = await fetch(`${API_BASE}/api/config/mcp-test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(server),
  });
  if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
  return res.json();
}

// ── Skills ──

export interface SkillsList {
  public: string[];
  user: string[];
  examples: string[];
  disabled: string[];
}

export async function listSkills(): Promise<SkillsList> {
  const res = await fetch(`${API_BASE}/api/skills`);
  if (!res.ok) throw new Error(`Failed to list skills: ${res.statusText}`);
  return res.json();
}

export async function uploadSkill(file: File): Promise<{ name: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/skills/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Upload failed: ${res.statusText}`);
  }
  return res.json();
}

export async function deleteSkill(name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/skills/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Failed to delete skill: ${res.statusText}`);
  }
}

export async function installSkill(name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/skills/${encodeURIComponent(name)}/install`, {
    method: "POST",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Failed to install skill: ${res.statusText}`);
  }
}

export async function toggleSkill(name: string, enabled: boolean): Promise<void> {
  const res = await fetch(`${API_BASE}/api/skills/${encodeURIComponent(name)}/toggle`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error(`Failed to toggle skill: ${res.statusText}`);
}
