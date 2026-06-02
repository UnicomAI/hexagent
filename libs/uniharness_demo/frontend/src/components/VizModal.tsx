import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

type ModalState = "closed" | "open" | "closing";

/**
 * Shared modal state machine with Esc-to-close and scroll lock.
 * Used by MermaidBlock and EChartsBlock.
 */
export function useVizModal() {
  const [state, setState] = useState<ModalState>("closed");
  const expanded = state !== "closed";

  const open = useCallback(() => setState("open"), []);
  const close = useCallback(() => setState("closing"), []);
  const onExitDone = useCallback(() => setState("closed"), []);

  useEffect(() => {
    if (!expanded) return;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setState("closing");
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey);
    };
  }, [expanded]);

  return { state, expanded, open, close, onExitDone };
}

interface VizModalProps {
  state: ModalState;
  onClose: () => void;
  onExitDone: () => void;
  /** Extra action buttons rendered before the close button (e.g. zoom +/−) */
  actions?: React.ReactNode;
  children: React.ReactNode;
}

/**
 * Shared fullscreen modal with blur backdrop, enter/exit animations,
 * and action buttons.  Content is rendered inside a full-size body area.
 */
export default function VizModal({ state, onClose, onExitDone, actions, children }: VizModalProps) {
  if (state === "closed") return null;
  const closing = state === "closing";
  return createPortal(
    <div
      className={`viz-overlay ${closing ? "viz-overlay-exit" : ""}`}
      onClick={onClose}
      onAnimationEnd={closing ? onExitDone : undefined}
    >
      <div
        className={`viz-modal ${closing ? "viz-modal-exit" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="viz-modal-inner">
          <div className="viz-modal-actions">
            {actions}
            <button className="viz-action-btn" onClick={onClose} aria-label="Close">
              <X />
            </button>
          </div>
          <div className="viz-modal-body">
            {children}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
