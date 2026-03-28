import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAppContext } from "../store";
import type { Conversation } from "../types";

interface SearchModalProps {
  open: boolean;
  onClose: () => void;
}

/** Extract a short preview from the first user message. */
function messagePreview(conv: Conversation): string {
  const first = conv.messages?.find((m) => m.role === "user");
  if (!first) return "";
  const text = first.content.slice(0, 120);
  return text.length < first.content.length ? text + "..." : text;
}

/** Format a relative time string. */
function relativeTime(dateStr: string, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return t("time.justNow");
  if (mins < 60) return t("time.minutesAgo", { count: mins });
  const hours = Math.floor(mins / 60);
  if (hours < 24) return t("time.hoursAgo", { count: hours });
  const days = Math.floor(hours / 24);
  if (days < 30) return t("time.daysAgo", { count: days });
  return new Date(dateStr).toLocaleDateString();
}

export default function SearchModal({ open, onClose }: SearchModalProps) {
  const { t } = useTranslation("search");
  const { state, dispatch } = useAppContext();
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const keyboardActiveRef = useRef(false);

  // Reset state when opening
  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      keyboardActiveRef.current = false;
      // Focus input after render
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Filter conversations globally (both chat and cowork)
  const results = useMemo(() => {
    const all = state.conversations;
    if (!query.trim()) return all;
    const q = query.toLowerCase();
    return all.filter((conv) => {
      if (conv.title?.toLowerCase().includes(q)) return true;
      // Search message content
      return conv.messages?.some((m) => m.content.toLowerCase().includes(q));
    });
  }, [query, state.conversations]);

  // Clamp selected index
  useEffect(() => {
    setSelectedIndex((prev) => Math.min(prev, Math.max(0, results.length - 1)));
  }, [results.length]);

  const selectConversation = useCallback(
    (conv: Conversation) => {
      const mode = conv.mode || "chat";
      if (mode !== state.selectedMode) {
        dispatch({ type: "SET_SELECTED_MODE", payload: mode });
      }
      dispatch({ type: "SET_ACTIVE_CONVERSATION", payload: conv.id });
      onClose();
    },
    [dispatch, state.selectedMode, onClose]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        keyboardActiveRef.current = true;
        setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        keyboardActiveRef.current = true;
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (results[selectedIndex]) {
          selectConversation(results[selectedIndex]);
        }
      }
    },
    [results, selectedIndex, selectConversation]
  );

  // Smoothly keep selected item visible (keyboard only)
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!keyboardActiveRef.current) return;
    const list = listRef.current;
    if (!list) return;
    const item = list.children[selectedIndex] as HTMLElement | undefined;
    if (!item) return;
    const pad = 6;
    const listRect = list.getBoundingClientRect();
    const itemRect = item.getBoundingClientRect();
    if (itemRect.top < listRect.top + pad) {
      list.scrollTo({ top: list.scrollTop + (itemRect.top - listRect.top) - pad, behavior: "smooth" });
    } else if (itemRect.bottom > listRect.bottom - pad) {
      list.scrollTo({ top: list.scrollTop + (itemRect.bottom - listRect.bottom) + pad, behavior: "smooth" });
    }
  }, [selectedIndex]);

  if (!open) return null;

  return (
    <div className="search-overlay" onClick={onClose}>
      <div className="search-modal" onClick={(e) => e.stopPropagation()}>
        <div className="search-header">
          <Search size={18} className="search-header-icon" />
          <input
            ref={inputRef}
            className="search-input"
            placeholder={t("placeholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button className="search-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="search-results" ref={listRef}>
          {results.length === 0 && (
            <div className="search-empty">
              {query.trim() ? t("noMatches") : t("noConversations")}
            </div>
          )}
          {results.map((conv, i) => {
            const mode = conv.mode || "chat";
            return (
              <button
                key={conv.id}
                className={`search-result-item ${i === selectedIndex ? "search-result-item--selected" : ""}`}
                onClick={() => selectConversation(conv)}
                onMouseMove={() => {
                  if (keyboardActiveRef.current) {
                    keyboardActiveRef.current = false;
                    return;
                  }
                  setSelectedIndex(i);
                }}
              >
                <span className={`search-result-badge search-result-badge--${mode}`}>
                  {t("chat:mode." + mode)}
                </span>
                <div className="search-result-content">
                  <span className="search-result-title">
                    {conv.title || t("sidebar:untitledConversation")}
                  </span>
                  {messagePreview(conv) && (
                    <span className="search-result-preview">{messagePreview(conv)}</span>
                  )}
                </div>
                <span className="search-result-time">{relativeTime(conv.updated_at, t)}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
