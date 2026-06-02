import { useState, useRef, useEffect, useCallback } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useAppContext } from "../store";
import { updateConversation } from "../api";


export default function ModelPicker({ dropUp }: { dropUp?: boolean }) {
  const { state, dispatch } = useAppContext();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const models = state.serverConfig?.models ?? [];
  const activeConv = state.conversations.find((c) => c.id === state.activeConversationId);
  const currentModelId = activeConv?.model_id || state.selectedModelId;
  const currentModel = models.find((m) => m.id === currentModelId);
  const label = currentModel?.display_name || currentModel?.model || "Select model";

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const scrollRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const updateFade = useCallback(() => {
    const el = scrollRef.current;
    const panel = dropdownRef.current;
    if (!el || !panel) return;
    const maxScroll = el.scrollHeight - el.clientHeight;
    if (maxScroll <= 0) {
      panel.style.setProperty("--fade-top", "0");
      panel.style.setProperty("--fade-bottom", "0");
      return;
    }
    // Quadratic ease: slow start, fast finish (y = x²)
    const ramp = 10;
    const t = Math.min(el.scrollTop / ramp, 1);
    const b = Math.min((maxScroll - el.scrollTop) / ramp, 1);
    panel.style.setProperty("--fade-top", String(t * t));
    panel.style.setProperty("--fade-bottom", String(b * b));
  }, []);

  useEffect(() => {
    if (!open) return;
    requestAnimationFrame(() => {
      // Scroll selected item into view only if not already fully visible
      const container = scrollRef.current;
      if (container) {
        const activeEl = container.querySelector(".dd-item--active") as HTMLElement | null;
        if (activeEl && activeEl.offsetTop + activeEl.offsetHeight > container.clientHeight) {
          // Scroll so the item before the selected one is fully visible at the top
          const prev = activeEl.previousElementSibling as HTMLElement | null;
          const top = prev ? prev.offsetTop : activeEl.offsetTop;
          container.scrollTop = Math.max(0, top);
        }
      }
      updateFade();
    });
  }, [open, updateFade]);

  if (models.length === 0) {
    return (
      <div className="mp">
        <span className="mp-trigger mp-trigger--empty">No model configured</span>
      </div>
    );
  }

  return (
    <div className="mp" ref={ref}>
      <button
        className="mp-trigger"
        onClick={() => setOpen(!open)}
        type="button"
      >
        <span className="mp-trigger-label">{label}</span>
        <ChevronDown size={14} className={`mp-trigger-chevron ${open ? "mp-trigger-chevron--open" : ""}`} />
      </button>
      {open && (
        <div ref={dropdownRef} className={`dd-panel mp-dropdown ${dropUp ? "mp-dropdown--up" : ""}`}>
          <div className="mp-scroll" ref={scrollRef} onScroll={updateFade}>
            {models.map((m) => {
              const active = m.id === currentModelId;
              return (
                <button
                  key={m.id}
                  className={`dd-item ${active ? "dd-item--active" : ""}`}
                  onClick={() => {
                    dispatch({ type: "SET_SELECTED_MODEL", payload: m.id });
                    if (state.activeConversationId) {
                      updateConversation(state.activeConversationId, { model_id: m.id }).catch(() => {});
                    }
                    setOpen(false);
                  }}
                >
                  <div className="mp-option-content">
                    <span className="dd-item-label">{m.display_name || m.model || "Untitled"}</span>
                    {m.model && <span className="mp-option-provider">{m.model}</span>}
                  </div>
                  <div className="dd-item-check">
                    {active && <Check size={16} strokeWidth={2.5} />}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
