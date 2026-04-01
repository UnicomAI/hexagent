import { useState, useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import brandLogo from "../assets/brand-logo.png";
import { Plus, Search, MoreHorizontal, Trash2, Pencil, Settings, PanelLeft, LogOut } from "lucide-react";
import { useAppContext } from "../store";
import { deleteConversation } from "../api";
import ScrollableText from "./ScrollableText";

const isMac = navigator.platform.toUpperCase().includes("MAC");

interface SidebarProps {
  onNewConversation: () => void;
  onOpenSettings: () => void;
  onOpenSearch: () => void;
  userName: string;
  onLogout: () => void;
}

interface ContextMenuState {
  visible: boolean;
  conversationId: string | null;
  anchorTop: number;
}

function getInitial(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "U";
  const SegmenterCtor = (Intl as Record<string, unknown>).Segmenter as
    | (new () => { segment(s: string): Iterable<{ segment: string }> })
    | undefined;
  if (SegmenterCtor) {
    const segments = [...new SegmenterCtor().segment(trimmed)];
    if (segments.length > 0) return segments[0].segment;
  }
  return trimmed.charAt(0);
}

export default function Sidebar({ onNewConversation, onOpenSettings, onOpenSearch, userName, onLogout }: SidebarProps) {
  const { t } = useTranslation("sidebar");
  const { state, dispatch } = useAppContext();
  const conversationsRef = useRef<HTMLDivElement>(null);
  const clipRef = useRef<HTMLDivElement>(null);
  const prevCollapsed = useRef(state.sidebarCollapsed);
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    conversationId: null,
    anchorTop: 0,
  });
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const toggleSidebar = useCallback(() => {
    dispatch({ type: "TOGGLE_SIDEBAR" });
  }, [dispatch]);

  const handleSelectConversation = useCallback(
    (id: string) => {
      dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: id });
      if (!state.sidebarCollapsed) toggleSidebar();
    },
    [dispatch, state.sidebarCollapsed, toggleSidebar]
  );

  const handleMenuClick = useCallback(
    (e: React.MouseEvent, conversationId: string) => {
      e.stopPropagation();
      const btn = e.currentTarget as HTMLElement;
      const container = conversationsRef.current;
      if (!container) return;
      const containerRect = container.getBoundingClientRect();
      const btnRect = btn.getBoundingClientRect();
      setContextMenu({
        visible: true,
        conversationId,
        anchorTop: btnRect.bottom - containerRect.top + container.scrollTop + 4,
      });
    },
    []
  );

  const handleDeleteConversation = useCallback(async () => {
    if (!contextMenu.conversationId) return;
    const id = contextMenu.conversationId;
    setContextMenu((prev) => ({ ...prev, visible: false }));
    try {
      await deleteConversation(id);
    } catch {
      /* continue */
    }
    dispatch({ type: "DELETE_CONVERSATION", payload: id });
  }, [contextMenu.conversationId, dispatch]);

  const handleRenameConversation = useCallback(() => {
    if (!contextMenu.conversationId) return;
    setRenamingId(contextMenu.conversationId);
    setContextMenu((prev) => ({ ...prev, visible: false }));
  }, [contextMenu.conversationId]);

  useEffect(() => {
    if (renamingId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingId]);

  const handleRenameSubmit = useCallback(
    (id: string, title: string) => {
      dispatch({ type: "UPDATE_CONVERSATION_TITLE", payload: { id, title: title || t("untitledConversation") } });
      setRenamingId(null);
    },
    [dispatch]
  );

  const closeContextMenu = useCallback(() => {
    setContextMenu((prev) => ({ ...prev, visible: false }));
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const mod = isMac ? e.metaKey : e.ctrlKey;
      if (mod && e.shiftKey && e.key.toLowerCase() === "o") {
        e.preventDefault();
        onNewConversation();
        if (!state.sidebarCollapsed) toggleSidebar();
      }
      if (mod && e.shiftKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onNewConversation, state.sidebarCollapsed, toggleSidebar]);

  // Close user menu on click outside
  useEffect(() => {
    if (!userMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [userMenuOpen]);

  useEffect(() => {
    if (prevCollapsed.current !== state.sidebarCollapsed) {
      clipRef.current?.classList.add("animating");
      prevCollapsed.current = state.sidebarCollapsed;
    }
  }, [state.sidebarCollapsed]);

  return (
    <div
      ref={clipRef}
      className={`sidebar-clip ${state.sidebarCollapsed ? "collapsed" : ""}`}
      onTransitionEnd={(e) => {
        if (e.target === e.currentTarget) e.currentTarget.classList.remove("animating");
      }}
    >
        {/* Header: always visible. On narrow screens it's fixed at top-left
          (outside the sliding aside). On wide screens it's static inside the clip. */}
      <div className="sidebar-header">
        <div className="sidebar-brand sidebar-fadeable">
          <img className="sidebar-brand-logo" width="25" height="25" src={brandLogo} alt={t("brand")} />
          <span className="sidebar-brand-text">{t("brand")}</span>
        </div>
        <button
          className="sidebar-icon-wrap sidebar-toggle custom-tooltip-trigger"
          onClick={(e) => {
            e.currentTarget.classList.add("tooltip-hidden");
            toggleSidebar();
          }}
          onMouseEnter={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const tip = e.currentTarget.querySelector(".custom-tooltip") as HTMLElement | null;
            if (tip) {
              tip.style.position = "fixed";
              tip.style.left = `${rect.right + 8}px`;
              tip.style.top = `${rect.top + rect.height / 2}px`;
            }
          }}
          onMouseLeave={(e) => e.currentTarget.classList.remove("tooltip-hidden")}
        >
          <PanelLeft />
          <span className="custom-tooltip">
            {state.sidebarCollapsed ? t("openSidebar") : t("closeSidebar")}
            <span className="custom-tooltip-shortcut">{isMac ? "Cmd+Shift+S" : "Ctrl+Shift+S"}</span>
          </span>
        </button>
      </div>

      <aside className={`sidebar ${state.sidebarCollapsed ? "collapsed" : ""}`}>
        {/* Actions: [icon shrink:0] [label flex:1]
            Icons stay in place, labels shrink away */}
        <nav className="sidebar-actions">
          <button
            className="sidebar-action-btn"
            onClick={() => {
              onNewConversation();
              if (!state.sidebarCollapsed) toggleSidebar();
            }}
          >
            <span className="sidebar-icon-wrap"><Plus /></span>
            <span className="sidebar-action-label sidebar-fadeable">{state.selectedMode === "chat" ? t("newChat") : t("newTask")}</span>
            <kbd className="sidebar-shortcut">{isMac ? "Cmd+Shift+O" : "Ctrl+Shift+O"}</kbd>
          </button>
          <button className="sidebar-action-btn" onClick={onOpenSearch}>
            <span className="sidebar-icon-wrap"><Search /></span>
            <span className="sidebar-action-label sidebar-fadeable">{t("search")}</span>
            <kbd className="sidebar-shortcut">{isMac ? "Cmd+K" : "Ctrl+K"}</kbd>
          </button>
        </nav>

        <div className="sidebar-divider sidebar-fadeable" />
        <div className="sidebar-section-label sidebar-fadeable">{t("recents")}</div>

        <div className="sidebar-conversations sidebar-fadeable" ref={conversationsRef}>
          {state.conversations.filter((c) => (c.mode || "chat") === state.selectedMode).map((conv) => (
            <div
              key={conv.id}
              className={`conversation-item ${conv.id === state.activeConversationId ? "active" : ""}`}
              onClick={() => handleSelectConversation(conv.id)}
            >
              {renamingId === conv.id ? (
                <input
                  ref={renameInputRef}
                  className="conversation-rename-input"
                  defaultValue={conv.title || ""}
                  onClick={(e) => e.stopPropagation()}
                  onBlur={(e) => handleRenameSubmit(conv.id, e.currentTarget.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleRenameSubmit(conv.id, e.currentTarget.value);
                    if (e.key === "Escape") setRenamingId(null);
                  }}
                />
              ) : (
                <ScrollableText className="conversation-item-title">
                  {conv.title || t("untitledConversation")}
                </ScrollableText>
              )}
              <button
                className={`conversation-item-menu ${contextMenu.visible && contextMenu.conversationId === conv.id ? "visible" : ""}`}
                onClick={(e) => handleMenuClick(e, conv.id)}
              >
                <MoreHorizontal />
              </button>
            </div>
          ))}

          {contextMenu.visible && (
            <>
              <div className="context-menu-overlay-inline" onClick={closeContextMenu} />
              <div className="context-menu-inline" style={{ top: contextMenu.anchorTop }}>
                <button className="context-menu-item" onClick={handleRenameConversation}>
                  <Pencil />
                  <span>{t("rename")}</span>
                </button>
                <div className="context-menu-divider" />
                <button className="context-menu-item danger" onClick={handleDeleteConversation}>
                  <Trash2 />
                  <span>{t("delete")}</span>
                </button>
              </div>
            </>
          )}

          {state.conversations.filter((c) => (c.mode || "chat") === state.selectedMode).length === 0 && (
            <div style={{ padding: "16px 12px", fontSize: "13px", color: "var(--text-muted)", textAlign: "center" }}>
              {state.selectedMode === "chat" ? t("noChats") : t("noTasks")}
            </div>
          )}
        </div>

        {/* Bottom: same layout as actions */}
        <div className="sidebar-bottom">
          <button className="sidebar-action-btn" onClick={onOpenSettings}>
            <span className="sidebar-icon-wrap"><Settings /></span>
            <span className="sidebar-action-label sidebar-fadeable">{t("settings")}</span>
            <kbd className="sidebar-shortcut">{isMac ? "Cmd+Shift+," : "Ctrl+Shift+,"}</kbd>
          </button>
          <div className="sidebar-user-row-wrap" ref={userMenuRef}>
            <div
              className="sidebar-action-btn sidebar-user-row"
              onClick={() => setUserMenuOpen((v) => !v)}
            >
              <span className="sidebar-icon-wrap">
                <span className="sidebar-avatar">{getInitial(userName)}</span>
              </span>
              <span className="sidebar-action-label sidebar-fadeable">{userName || t("user")}</span>
            </div>
            {userMenuOpen && (
              <div className="sidebar-user-menu">
                <button
                  className="sidebar-user-menu-item"
                  onClick={() => { setUserMenuOpen(false); onLogout(); }}
                >
                  <LogOut size={16} />
                  <span>{t("logout")}</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}
