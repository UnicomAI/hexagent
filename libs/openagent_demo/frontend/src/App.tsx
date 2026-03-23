import { useReducer, useEffect, useCallback, useRef, useState } from "react";
import { AppContext, initialState, reducer } from "./store";
import { listConversations, createConversation, createWarmSession, deleteWarmSession, sendMessage, getServerConfig, getVMStatus } from "./api";
import { useSettings } from "./hooks/useSettings";
import Sidebar from "./components/Sidebar";
import ChatArea from "./components/ChatArea";
import RightPanel from "./components/RightPanel";
import SettingsModal from "./components/SettingsModal";
import type { Tab as SettingsTab } from "./components/SettingsModal";
import OnboardingWizard from "./components/OnboardingWizard";
import SearchModal from "./components/SearchModal";
import Toast from "./components/Toast";
import type { Attachment, ConversationMode, Message } from "./types";
import "./App.css";

function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const abortRef = useRef<AbortController | null>(null);
  const { settings, setSettings } = useSettings();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<SettingsTab | undefined>(undefined);
  const [searchOpen, setSearchOpen] = useState(false);
  const [setupNeeded, setSetupNeeded] = useState(false);

  const openSettings = useCallback((tab?: string) => {
    setSettingsTab(tab as SettingsTab | undefined);
    setSettingsOpen(true);
  }, []);

  // Cmd+Shift+, opens settings (SettingsModal handles close when open)
  useEffect(() => {
    if (settingsOpen) return; // SettingsModal owns the shortcut when open
    const isMac = navigator.platform.toUpperCase().includes("MAC");
    const handleKeyDown = (e: KeyboardEvent) => {
      const mod = isMac ? e.metaKey : e.ctrlKey;
      if (mod && e.shiftKey && (e.key === "," || e.key === "<" || e.code === "Comma")) {
        e.preventDefault();
        setSettingsOpen(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [settingsOpen]);

  // Cmd+K toggles search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const mod = navigator.platform.toUpperCase().includes("MAC") ? e.metaKey : e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const [initialLoadDone, setInitialLoadDone] = useState(false);

  useEffect(() => {
    // Parse conversation ID from URL (e.g. /chat/{id} or /cowork/{id}).
    // Mode is already set synchronously in initialState from the URL.
    const m = window.location.pathname.match(/^\/(chat|cowork)(?:\/(.+))?/);
    const urlConvId = m?.[2] ?? null;

    // Wait for both conversations and config to load before marking
    // initialLoadDone.  This prevents the warm-session effect from
    // firing before we know whether onboarding is still needed.
    const convP = listConversations()
      .then((conversations) => {
        dispatch({ type: "SET_CONVERSATIONS", payload: conversations });
        // Restore active conversation from URL
        if (urlConvId && conversations.some((c) => c.id === urlConvId)) {
          dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: urlConvId });
        }
      })
      .catch(() => {});
    const cfgP = getServerConfig()
      .then((cfg) => {
        dispatch({ type: "SET_SERVER_CONFIG", payload: cfg });
        if (cfg.models.length === 0) setSetupNeeded(true);
      })
      .catch(() => {});
    Promise.all([convP, cfgP]).then(() => setInitialLoadDone(true));
    getVMStatus()
      .then((vs) => dispatch({ type: "SET_VM_STATUS", payload: vs }))
      .catch(() => {});
  }, []);

  // Track whether sidebar collapse was triggered by breakpoint (skip animation)
  const breakpointCollapseRef = useRef(false);

  // Auto-collapse sidebar when viewport shrinks below the side-by-side breakpoint
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1000px)");
    const handler = (e: MediaQueryListEvent) => {
      if (!e.matches && !state.sidebarCollapsed) {
        breakpointCollapseRef.current = true;
        dispatch({ type: "SET_SIDEBAR_COLLAPSED", payload: true });
      }
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [state.sidebarCollapsed]);

  // Animate sidebar only on user-initiated toggles (not breakpoint changes)
  useEffect(() => {
    if (breakpointCollapseRef.current) {
      breakpointCollapseRef.current = false;
      return;
    }
    const sidebar = document.querySelector(".sidebar") as HTMLElement | null;
    if (!sidebar) return;
    sidebar.classList.add("sidebar-animating");
    const timer = setTimeout(() => sidebar.classList.remove("sidebar-animating"), 300);
    return () => clearTimeout(timer);
  }, [state.sidebarCollapsed]);

  // Sync URL when active conversation changes (skip until initial load completes
  // to avoid overwriting the URL-derived mode with the default "chat")
  useEffect(() => {
    if (!initialLoadDone) return;
    if (state.activeConversationId) {
      const conv = state.conversations.find((c) => c.id === state.activeConversationId);
      const mode = conv?.mode || state.selectedMode;
      const target = `/${mode}/${state.activeConversationId}`;
      if (window.location.pathname !== target) {
        window.history.pushState(null, "", target);
      }
    } else {
      const target = `/${state.selectedMode}`;
      if (window.location.pathname !== target) {
        window.history.pushState(null, "", target);
      }
    }
  }, [state.activeConversationId, state.conversations, state.selectedMode]);

  // Handle browser back/forward navigation
  useEffect(() => {
    const handler = () => {
      const m = window.location.pathname.match(/^\/(chat|cowork)(?:\/(.+))?/);
      if (m) {
        dispatch({ type: "SET_SELECTED_MODE", payload: m[1] as ConversationMode });
        dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: m[2] ?? null });
      } else {
        dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: null });
      }
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);

  // Eagerly create a warm session when user lands on the welcome screen
  const warmingRef = useRef(false);
  const warmSessionPromiseRef = useRef<Promise<string> | null>(null);
  // Track previous warmSessionId for teardown on mode switch
  const prevWarmSessionIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (state.activeConversationId) {
      warmingRef.current = false;
      warmSessionPromiseRef.current = null;
      return;
    }
    if (!initialLoadDone) return;
    if (setupNeeded) return; // onboarding not complete yet
    if (warmingRef.current) return;
    if (state.warmSessionId) return; // already have one

    const mode = state.selectedMode;

    // Skip warm session for cowork mode when VM is not ready — avoids
    // hitting the backend and getting a guaranteed failure.
    // Also skip when vmStatus hasn't been fetched yet (null).
    if (mode === "cowork" && (!state.vmStatus || !state.vmStatus.vm_ready)) return;

    warmingRef.current = true;
    const modelId = state.selectedModelId || undefined;
    const p = createWarmSession(mode, modelId)
      .then((session) => {
        dispatch({ type: "SET_WARM_SESSION", payload: session.session_id });
        return session.session_id;
      });
    warmSessionPromiseRef.current = p;
    p.catch(() => {
        dispatch({ type: "SHOW_NOTIFICATION", payload: {
          message: "Session setup failed. You can still send messages.",
          type: "info",
        }});
      })
      .finally(() => { warmingRef.current = false; });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.activeConversationId, state.warmSessionId, state.selectedMode, state.vmStatus, initialLoadDone, setupNeeded]);

  // Tear down backend warm session when it's cleared by mode switch
  useEffect(() => {
    const prev = prevWarmSessionIdRef.current;
    prevWarmSessionIdRef.current = state.warmSessionId;
    // If warmSessionId went from a value to null and there's no active conversation
    // (conversation creation claims the session server-side, no need to delete)
    if (prev && !state.warmSessionId && !state.activeConversationId) {
      deleteWarmSession(prev).catch(() => {});
    }
  }, [state.warmSessionId, state.activeConversationId]);

  // Reference for doSendMessage to access latest conversations
  const conversationsRef = useRef(state.conversations);
  conversationsRef.current = state.conversations;

  const doSendMessage = useCallback(
    async (conversationId: string, content: string, attachments?: Attachment[]) => {
      const allAttachments = attachments ?? [];

      // Build message content — append file references if any
      let fullContent = content;
      if (allAttachments.length > 0) {
        const refs = allAttachments.map((a) => `[Attached file: ${a.path}]`).join("\n");
        fullContent = fullContent ? `${fullContent}\n\n${refs}` : refs;
      }

      if (!fullContent) return;

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: fullContent,
        attachments: allAttachments.length > 0 ? allAttachments : undefined,
        created_at: new Date().toISOString(),
      };

      dispatch({
        type: "ADD_USER_MESSAGE",
        payload: { conversationId, message: userMessage },
      });

      // Update title if it's the first message
      const activeConv = state.conversations.find((c) => c.id === conversationId);
      if (activeConv && (!activeConv.messages || activeConv.messages.length === 0)) {
        const displayContent = content || allAttachments.map((a) => a.filename).join(", ");
        const title = displayContent.length > 40 ? displayContent.slice(0, 40) + "..." : displayContent;
        dispatch({
          type: "UPDATE_CONVERSATION_TITLE",
          payload: { id: conversationId, title },
        });
      }

      // Send model_id so backend uses the right model
      const conv = state.conversations.find((c) => c.id === conversationId);
      const modelId = conv?.model_id || state.selectedModelId || undefined;

      const controller = sendMessage(conversationId, fullContent, {
        onMessageStart: (id) => {
          dispatch({ type: "STREAM_START", payload: { messageId: id } });
        },
        onTextDelta: (delta) => {
          dispatch({ type: "STREAM_TEXT_DELTA", payload: delta });
        },
        onReasoningDelta: (delta) => {
          dispatch({ type: "STREAM_REASONING_DELTA", payload: delta });
        },
        onToolCallDelta: (data) => {
          dispatch({ type: "STREAM_TOOL_CALL_DELTA", payload: data });
        },
        onToolUseStart: (tool) => {
          dispatch({ type: "STREAM_TOOL_USE_START", payload: tool });
        },
        onToolResult: (result) => {
          dispatch({ type: "STREAM_TOOL_RESULT", payload: result });
        },
        onSubagentTextDelta: (data) => {
          dispatch({ type: "STREAM_SUBAGENT_TEXT_DELTA", payload: data });
        },
        onSubagentReasoningDelta: (data) => {
          dispatch({ type: "STREAM_SUBAGENT_REASONING_DELTA", payload: data });
        },
        onSubagentToolCallDelta: (data) => {
          dispatch({ type: "STREAM_SUBAGENT_TOOL_CALL_DELTA", payload: data });
        },
        onSubagentToolStart: (data) => {
          dispatch({ type: "STREAM_SUBAGENT_TOOL_START", payload: data });
        },
        onSubagentToolResult: (data) => {
          dispatch({ type: "STREAM_SUBAGENT_TOOL_RESULT", payload: data });
        },
        onMessageEnd: (id) => {
          dispatch({ type: "STREAM_END", payload: { messageId: id } });
        },
        onError: (error) => {
          if (state.isStreaming) {
            dispatch({ type: "STREAM_ERROR", payload: error });
          } else {
            dispatch({ type: "SHOW_NOTIFICATION", payload: { message: error, type: "error" } });
          }
        },
      }, modelId, allAttachments.length > 0 ? allAttachments : undefined);

      abortRef.current = controller;
    },
    [state.conversations, state.selectedModelId]
  );

  const handleNewConversation = useCallback(() => {
    dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: null });
    dispatch({ type: "SET_WARM_SESSION", payload: null });
  }, []);

  const handleSendMessage = useCallback(
    async (content: string, options?: { workingDir?: string; attachments?: Attachment[] }) => {
      if (state.isStreaming) return;

      // If we have an active conversation, send directly
      if (state.activeConversationId) {
        doSendMessage(state.activeConversationId, content, options?.attachments);
        return;
      }

      // Welcome screen: create conversation first, then send message
      const modelId = state.selectedModelId || undefined;
      const mode = state.selectedMode;
      const workingDir = options?.workingDir;
      // Wait for in-flight warm session if user sent before it resolved
      let sessionId = state.warmSessionId || undefined;
      if (!sessionId && warmSessionPromiseRef.current) {
        try { sessionId = await warmSessionPromiseRef.current; } catch { /* proceed without */ }
      }

      try {
        const conv = await createConversation(modelId, mode, workingDir, sessionId);
        dispatch({ type: "ADD_CONVERSATION", payload: conv });
        dispatch({ type: "SET_WARM_SESSION", payload: null });
        // Set title from first message content
        const displayContent = content || (options?.attachments ?? []).map((a) => a.filename).join(", ");
        if (displayContent) {
          const title = displayContent.length > 40 ? displayContent.slice(0, 40) + "..." : displayContent;
          dispatch({ type: "UPDATE_CONVERSATION_TITLE", payload: { id: conv.id, title } });
        }
        // Now send the message to the newly created conversation
        doSendMessage(conv.id, content, options?.attachments);
      } catch {
        dispatch({ type: "SHOW_NOTIFICATION", payload: { message: "Failed to create conversation", type: "error" } });
      }
    },
    [state.activeConversationId, state.isStreaming, state.selectedModelId, state.selectedMode, state.warmSessionId, doSendMessage]
  );

  const activeConversation = state.conversations.find(
    (c) => c.id === state.activeConversationId
  );

  // Per-conversation right panel visibility
  const rightPanelVisible = state.activeConversationId
    ? (state.rightPanelByConversation[state.activeConversationId] ?? false)
    : false;

  // Only pass streaming blocks when viewing the conversation that owns the stream
  const activeStreamingBlocks =
    state.isStreaming && state.streamingConversationId === state.activeConversationId
      ? state.streamingBlocks
      : undefined;

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      <div className="app">
        <Sidebar
          onNewConversation={handleNewConversation}
          onOpenSettings={() => openSettings()}
          onOpenSearch={() => setSearchOpen(true)}
          userName={settings.fullName}
        />
        <div
          className={`sidebar-backdrop ${state.sidebarCollapsed ? "hidden" : ""}`}
          onClick={() => dispatch({ type: "TOGGLE_SIDEBAR" })}
        />
        <ChatArea
          conversation={activeConversation ?? null}
          onSendMessage={handleSendMessage}
          onOpenSettings={openSettings}
          rightPanel={
            <RightPanel
              visible={rightPanelVisible}
              conversation={activeConversation ?? null}
              streamingBlocks={activeStreamingBlocks}
            />
          }
        />
      </div>
      <OnboardingWizard
        open={setupNeeded}
        onComplete={() => setSetupNeeded(false)}
        settings={settings}
        onSettingsChange={setSettings}
      />
      <SettingsModal
        open={settingsOpen}
        onClose={() => { setSettingsOpen(false); setSettingsTab(undefined); }}
        settings={settings}
        onSettingsChange={setSettings}
        initialTab={settingsTab}
      />
      <SearchModal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
      />
      <Toast
        notifications={state.notifications}
        onDismiss={(id) => dispatch({ type: "DISMISS_NOTIFICATION", payload: id })}
      />
    </AppContext.Provider>
  );
}

export default App;
