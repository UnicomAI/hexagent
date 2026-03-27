import { useState, useCallback, useRef, useEffect } from "react";
import { Paperclip, ArrowUp, ArrowDown, X, FileText, Loader2, CircleAlert } from "lucide-react";
import { useAppContext } from "../store";
import { uploadChatFile, deleteChatFile } from "../api";
import { useFileDrop } from "../hooks/useFileDrop";
import ModelPicker from "./ModelPicker";
import InputSettingsMenu from "./InputSettingsMenu";
import type { Attachment } from "../types";

interface PendingFile {
  id: string;
  name: string;
  status: "uploading" | "done" | "failed";
  result?: Attachment;
  error?: string;
}

interface ChatInputProps {
  conversationId: string;
  onSend: (content: string, options?: { attachments?: Attachment[] }) => void;
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  onOpenSettings: (tab?: string) => void;
}

/** Show button when the bottom of the last message is not visible in the reading area
 *  (between the scroll container top and the input bar top). */
function shouldShowScrollButton(container: HTMLElement, inputContainer: HTMLElement | null): boolean {
  if (!inputContainer) return false;
  const messageRows = container.querySelectorAll(".message-row");
  if (messageRows.length === 0) return false;
  const lastRow = messageRows[messageRows.length - 1];
  const lastRowBottom = lastRow.getBoundingClientRect().bottom;
  const visibleTop = container.getBoundingClientRect().top;
  const visibleBottom = inputContainer.getBoundingClientRect().top;
  // Show only when a significant amount of content is scrolled past (200px threshold)
  return lastRowBottom < visibleTop - 200 || lastRowBottom > visibleBottom + 200;
}

export default function ChatInput({ conversationId, onSend, scrollContainerRef, onOpenSettings }: ChatInputProps) {
  const { state, dispatch } = useAppContext();
  const noModels = !state.serverConfig?.models?.length;
  const missingE2bKey = state.selectedMode === "chat" && !state.serverConfig?.sandbox?.e2b_api_key;
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [e2bHintFlash, setE2bHintFlash] = useState(false);
  const e2bHintTimer = useRef<ReturnType<typeof setTimeout>>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputContainerRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  /** Flash the E2B hint briefly (for button clicks). */
  const flashE2bHint = useCallback(() => {
    setE2bHintFlash(true);
    if (e2bHintTimer.current) clearTimeout(e2bHintTimer.current);
    e2bHintTimer.current = setTimeout(() => setE2bHintFlash(false), 3000);
  }, []);

  // Cleanup timer on unmount
  useEffect(() => () => { if (e2bHintTimer.current) clearTimeout(e2bHintTimer.current); }, []);

  const checkScrollBtn = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    setShowScrollBtn(shouldShowScrollButton(container, inputContainerRef.current));
  }, [scrollContainerRef]);

  // React to user scroll
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const handleScroll = () => checkScrollBtn();
    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => container.removeEventListener("scroll", handleScroll);
  }, [scrollContainerRef, checkScrollBtn]);

  // React to content growth during streaming
  const streamingEntry = state.streamingByConversation[conversationId];
  useEffect(() => {
    checkScrollBtn();
  }, [streamingEntry?.blocks, checkScrollBtn]);

  const scrollToBottom = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  }, [scrollContainerRef]);

  const doneFiles = pendingFiles.filter((f) => f.status === "done");
  const anyUploading = pendingFiles.some((f) => f.status === "uploading");

  const handleSubmit = useCallback(() => {
    if (missingE2bKey) { flashE2bHint(); return; }
    const trimmed = value.trim();
    const hasContent = trimmed || doneFiles.length > 0;
    if (!hasContent || !!state.streamingByConversation[conversationId] || anyUploading) return;

    const attachments = doneFiles.map((f) => f.result!);
    onSend(trimmed, attachments.length > 0 ? { attachments } : undefined);
    setValue("");
    setPendingFiles([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, doneFiles, anyUploading, state.streamingByConversation, conversationId, onSend, missingE2bKey, flashE2bHint]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key.length !== 1) return;
      // Don't steal focus from any interactive element
      const active = document.activeElement;
      if (!active || active === document.body) {
        textareaRef.current?.focus();
        return;
      }
      const tag = active.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if ((active as HTMLElement).isContentEditable) return;
      textareaRef.current?.focus();
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, []);

  const handleInput = useCallback(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 200) + "px";
    }
  }, []);

  const pendingFilesRef = useRef<PendingFile[]>([]);
  pendingFilesRef.current = pendingFiles;

  const startUpload = useCallback((file: File) => {
    const id = crypto.randomUUID();

    // Check for name collision against existing pending files
    const collision = pendingFilesRef.current.some((f) => f.name === file.name && f.status !== "failed");
    if (collision) {
      const error = `"${file.name}" already attached. Rename the file and try again.`;
      setPendingFiles((prev) => [...prev, { id, name: file.name, status: "failed" as const, error }]);
      dispatch({ type: "SHOW_NOTIFICATION", payload: { message: error, type: "error" } });
      return;
    }

    setPendingFiles((prev) => [...prev, { id, name: file.name, status: "uploading" }]);

    uploadChatFile(conversationId, file)
      .then((result) => {
        setPendingFiles((prev) =>
          prev.map((f) => f.id === id ? { ...f, status: "done" as const, result: { filename: result.filename, path: result.path } } : f)
        );
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : "Upload failed";
        setPendingFiles((prev) =>
          prev.map((f) => f.id === id ? { ...f, status: "failed" as const, error: message } : f)
        );
        dispatch({
          type: "SHOW_NOTIFICATION",
          payload: { message: `Failed to upload ${file.name}: ${message}`, type: "error" },
        });
      });
  }, [conversationId, dispatch]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files) {
      Array.from(files).forEach(startUpload);
    }
    if (fileRef.current) fileRef.current.value = "";
    textareaRef.current?.focus();
  }, [startUpload]);

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const files = e.clipboardData?.files;
    if (!files || files.length === 0) return;
    e.preventDefault();
    Array.from(files).forEach((file) => {
      // Clipboard images often have a generic name like "image.png" —
      // give them a timestamped name to avoid collisions.
      if (file.type.startsWith("image/") && file.name === "image.png") {
        const ext = file.type.split("/")[1] || "png";
        const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
        const renamed = new File([file], `pasted-${ts}.${ext}`, { type: file.type });
        startUpload(renamed);
      } else {
        startUpload(file);
      }
    });
  }, [startUpload]);

  const { dragOver, dragProps } = useFileDrop(
    useCallback((files: File[]) => {
      files.forEach(startUpload);
      textareaRef.current?.focus();
    }, [startUpload]),
    useCallback((reason: string) => {
      dispatch({ type: "SHOW_NOTIFICATION", payload: { message: reason, type: "error" } });
    }, [dispatch]),
  );

  const removePendingFile = useCallback((id: string) => {
    setPendingFiles((prev) => {
      const file = prev.find((f) => f.id === id);
      // If the file was successfully uploaded, delete it from backend + computer
      if (file?.status === "done" && file.result) {
        deleteChatFile(conversationId, file.result.filename).catch(() => {
          // Best-effort cleanup — file may already be gone
        });
      }
      return prev.filter((f) => f.id !== id);
    });
  }, [conversationId]);

  return (
    <div className="input-container" ref={inputContainerRef}>
      <button
        aria-label="Scroll to bottom"
        className={`scroll-to-bottom ${showScrollBtn ? "" : "hidden"}`}
        onClick={scrollToBottom}
      >
        <ArrowDown />
      </button>
      <div
        className={`input-bar ${focused ? "focused" : ""} ${dragOver ? "drag-over" : ""}`}
        {...dragProps}
      >
        {/* Pending file chips */}
        {pendingFiles.length > 0 && (
          <div className="input-attachments">
            {pendingFiles.map((pf) => (
              <div
                key={pf.id}
                className={`input-attachment-chip ${pf.status === "uploading" ? "is-uploading" : ""} ${pf.status === "failed" ? "is-failed" : ""}`}
                title={pf.status === "failed" ? pf.error : undefined}
              >
                {pf.status === "uploading" && <Loader2 className="input-attachment-icon input-attachment-spinner" />}
                {pf.status === "done" && <FileText className="input-attachment-icon" />}
                {pf.status === "failed" && <CircleAlert className="input-attachment-icon" />}
                <span className="input-attachment-name">{pf.name}</span>
                {pf.status !== "uploading" && (
                  <button className="input-attachment-remove" onClick={() => removePendingFile(pf.id)}>
                    <X size={14} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
        <textarea
            ref={textareaRef}
            className="input-textarea"
            placeholder="Ask anything..."
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            onPaste={handlePaste}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            rows={1}
          />
          <div className="input-toolbar">
            <div className="input-toolbar-left">
              <input
                ref={fileRef}
                type="file"
                multiple
                onChange={handleFileInput}
                style={{ display: "none" }}
              />
              <button
                className="input-tool-btn"
                title="Attach file"
                onClick={() => { if (missingE2bKey) { flashE2bHint(); return; } fileRef.current?.click(); }}
              >
                <Paperclip />
              </button>
              <InputSettingsMenu onOpenSettings={onOpenSettings} dropUp />
            </div>
            <div className="input-toolbar-right">
              <ModelPicker dropUp />
              <div className="input-send-wrapper">
                <button
                  className="input-send"
                  onClick={handleSubmit}
                  disabled={(!value.trim() && doneFiles.length === 0) || !!state.streamingByConversation[conversationId] || anyUploading || noModels || missingE2bKey}
                  title={noModels ? "Configure a model in Settings first" : "Send message"}
                >
                  <ArrowUp />
                </button>
                {missingE2bKey && (
                  <div className={`e2b-hint${value.trim() || e2bHintFlash ? " e2b-hint-visible" : ""}`}>
                    E2B API key required —{" "}
                    <button className="e2b-hint-link" onClick={() => onOpenSettings("sandbox")}>
                      Set in Settings
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      <div className="input-disclaimer" role="note">
        AI responses may be inaccurate. Please double-check important information.
      </div>
    </div>
  );
}
