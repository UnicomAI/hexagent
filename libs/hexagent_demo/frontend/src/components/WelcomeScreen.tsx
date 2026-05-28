import { useState, useCallback, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Paperclip, ArrowUp, X, FileText, Loader2, CircleAlert } from "lucide-react";
import { useAppContext } from "../store";
import { uploadSessionFile, deleteSessionFile, updateWarmSession } from "../api";
import { useFileDrop } from "../hooks/useFileDrop";
import ModelPicker from "./ModelPicker";
import FolderPicker from "./FolderPicker";
import InputSettingsMenu from "./InputSettingsMenu";
import type { Attachment, ConversationMode } from "../types";

interface PendingFile {
  id: string;
  name: string;
  status: "uploading" | "done" | "failed";
  result?: Attachment;
  error?: string;
}

interface WelcomeScreenProps {
  onSubmit: (content: string, options?: { workingDir?: string; attachments?: Attachment[] }) => void;
  mode: ConversationMode;
  onOpenSettings: (tab?: string) => void;
}

export default function WelcomeScreen({ onSubmit, mode, onOpenSettings }: WelcomeScreenProps) {
  const { t } = useTranslation("welcome");
  const { state, dispatch } = useAppContext();
  const warmSessionId = state.warmSessionId;
  const isPreparingRequest = state.isRequestPending;
  const isCowork = mode === "cowork";
  const noModels = !state.serverConfig?.models?.length;
  const missingE2bKey = !isCowork && !state.serverConfig?.sandbox?.e2b_api_key;
  const vmNotReady = isCowork && !state.vmStatus?.vm_ready;
  const sandboxBlocked = missingE2bKey || vmNotReady;
  const [e2bHintFlash, setE2bHintFlash] = useState(false);
  const e2bHintTimer = useRef<ReturnType<typeof setTimeout>>(null);

  const placeholders = t(isCowork ? "placeholders.cowork" : "placeholders.chat", { returnObjects: true }) as string[];

  const [value, setValue] = useState("");
  const [current, setCurrent] = useState(0);
  const [prev, setPrev] = useState<number | null>(null);
  const [selectedFolder, setSelectedFolder] = useState("");
  const [mountingFolder, setMountingFolder] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Reset placeholder index when mode changes
  useEffect(() => {
    setCurrent(0);
    setPrev(null);
  }, [mode]);

  useEffect(() => {
    if (value) return;
    const timer = setInterval(() => {
      setCurrent((c) => {
        setPrev(c);
        return (c + 1) % placeholders.length;
      });
    }, 7000);
    return () => clearInterval(timer);
  }, [value, placeholders.length]);

  useEffect(() => {
    if (prev === null) return;
    const timer = setTimeout(() => setPrev(null), 400);
    return () => clearTimeout(timer);
  }, [prev]);

  // Auto-focus on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  // Focus textarea when user starts typing anywhere on the page
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key.length !== 1) return;
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
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const flashE2bHint = useCallback(() => {
    setE2bHintFlash(true);
    if (e2bHintTimer.current) clearTimeout(e2bHintTimer.current);
    e2bHintTimer.current = setTimeout(() => setE2bHintFlash(false), 3000);
  }, []);

  useEffect(() => () => { if (e2bHintTimer.current) clearTimeout(e2bHintTimer.current); }, []);

  const doneFiles = pendingFiles.filter((f) => f.status === "done");
  const anyUploading = pendingFiles.some((f) => f.status === "uploading");
  const sendDisabled = (!value.trim() && doneFiles.length === 0) || anyUploading || mountingFolder || isPreparingRequest || noModels || sandboxBlocked;
  const sendTitle = noModels
    ? t("configureModel")
    : mountingFolder
      ? t("mountingFolder")
      : isPreparingRequest
        ? t("preparingRequest")
      : sandboxBlocked
        ? t("sandboxRequired")
        : t("sendMessage");

  const handleSubmit = useCallback(() => {
    if (sandboxBlocked) { flashE2bHint(); return; }
    const trimmed = value.trim();
    const hasContent = trimmed || doneFiles.length > 0;
    if (!hasContent || anyUploading || mountingFolder || isPreparingRequest) return;
    const opts: { workingDir?: string; attachments?: Attachment[] } = {};
    if (selectedFolder) opts.workingDir = selectedFolder;
    if (doneFiles.length > 0) {
      opts.attachments = doneFiles.map((f) => f.result!);
    }
    onSubmit(trimmed, Object.keys(opts).length > 0 ? opts : undefined);
    setValue("");
    setPendingFiles([]);
  }, [value, onSubmit, selectedFolder, doneFiles, anyUploading, mountingFolder, isPreparingRequest, sandboxBlocked, flashE2bHint]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  const handleInput = useCallback(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.max(el.scrollHeight, 60) + "px";
    }
  }, []);

  const pendingFilesRef = useRef<PendingFile[]>([]);
  pendingFilesRef.current = pendingFiles;

  const startUpload = useCallback((file: File) => {
    if (sandboxBlocked) { flashE2bHint(); return; }
    if (!warmSessionId) return;
    const id = crypto.randomUUID();

    // Check for name collision
    const collision = pendingFilesRef.current.some((f) => f.name === file.name && f.status !== "failed");
    if (collision) {
      const error = t("chat:alreadyAttached", { filename: file.name });
      setPendingFiles((prev) => [...prev, { id, name: file.name, status: "failed" as const, error }]);
      dispatch({ type: "SHOW_NOTIFICATION", payload: { message: error, type: "error" } });
      return;
    }

    setPendingFiles((prev) => [...prev, { id, name: file.name, status: "uploading" }]);

    uploadSessionFile(warmSessionId, file)
      .then((result) => {
        setPendingFiles((prev) =>
          prev.map((f) => f.id === id ? { ...f, status: "done" as const, result: { filename: result.filename, path: result.path } } : f)
        );
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : t("chat:uploadFailed");
        setPendingFiles((prev) =>
          prev.map((f) => f.id === id ? { ...f, status: "failed" as const, error: message } : f)
        );
        dispatch({
          type: "SHOW_NOTIFICATION",
          payload: { message: t("chat:failedToUpload", { filename: file.name, message }), type: "error" },
        });
      });
  }, [warmSessionId, dispatch, sandboxBlocked, flashE2bHint]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files) {
      Array.from(files).forEach(startUpload);
    }
    if (fileRef.current) fileRef.current.value = "";
    textareaRef.current?.focus();
  }, [startUpload]);

  const handleFolderChange = useCallback((folder: string) => {
    if (vmNotReady) { flashE2bHint(); return; }
    setSelectedFolder(folder);
    if (warmSessionId && folder) {
      // Mount the folder in the warm session
      setMountingFolder(true);
      updateWarmSession(warmSessionId, { working_dir: folder })
        .catch((err: unknown) => {
          const msg = err instanceof Error ? err.message : String(err);
          // Benign race: warm session may be claimed by conversation creation.
          if (msg.includes("(404)") && msg.includes("Session was claimed")) return;
          dispatch({ type: "SHOW_NOTIFICATION", payload: { message: t("misc:failedToMountFolder"), type: "error" } });
        })
        .finally(() => setMountingFolder(false));
    }
    // If warmSessionId isn't ready yet, the effect below will flush when it arrives
  }, [warmSessionId, dispatch, vmNotReady, flashE2bHint]);

  // Flush pending folder mount when warm session becomes available
  useEffect(() => {
    if (warmSessionId && selectedFolder) {
      setMountingFolder(true);
      updateWarmSession(warmSessionId, { working_dir: selectedFolder })
        .catch((err: unknown) => {
          const msg = err instanceof Error ? err.message : String(err);
          if (msg.includes("(404)") && msg.includes("Session was claimed")) return;
          dispatch({ type: "SHOW_NOTIFICATION", payload: { message: t("misc:failedToMountFolder"), type: "error" } });
        })
        .finally(() => setMountingFolder(false));
    }
    // Only trigger when warmSessionId changes (not on every folder change —
    // handleFolderChange already handles that when the session is ready)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warmSessionId]);

  const removePendingFile = useCallback((id: string) => {
    const file = pendingFilesRef.current.find((f) => f.id === id);
    if (file?.status === "done" && file.result && warmSessionId) {
      deleteSessionFile(warmSessionId, file.result.filename).catch(() => {});
    }
    setPendingFiles((prev) => prev.filter((f) => f.id !== id));
  }, [warmSessionId]);

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const files = e.clipboardData?.files;
    if (!files || files.length === 0) return;
    e.preventDefault();
    Array.from(files).forEach((file) => {
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

  const headingWords = t(isCowork ? "heading.coworkWords" : "heading.chatWords", { returnObjects: true }) as string[];

  return (
    <div className="welcome-screen" key={mode}>
      <h1 className={`welcome-heading ${isCowork ? "welcome-heading--cowork" : ""}`}>
        {headingWords.map((word, i, arr) => {
          if (isCowork) {
            return (
              <span key={i} style={{ animationDelay: `${i * 80}ms` }}>
                {word}{i < arr.length - 1 ? "\u00A0" : ""}
              </span>
            );
          }
          const isFirst = i === 0;
          const delay = isFirst ? 0 : 700 + (i - 1) * 80;
          return (
            <span key={i} className={isFirst ? "wh-first" : "wh-word"} style={{ animationDelay: `${delay}ms` }}>
              {word}{i < arr.length - 1 ? "\u00A0" : ""}
            </span>
          );
        })}
      </h1>
      <div className="welcome-input-wrapper">
        <div
          className={`input-bar ${dragOver ? "drag-over" : ""}`}
          {...dragProps}
        >
          <div className="input-textarea-wrapper">
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
              placeholder=""
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={handleKeyDown}
              onInput={handleInput}
              onPaste={handlePaste}
              rows={2}
            />
            {!value && pendingFiles.length === 0 && prev !== null && (
              <div className="rolling-placeholder rolling-out" key={`out-${prev}`}>
                {placeholders[prev]}
              </div>
            )}
            {!value && pendingFiles.length === 0 && (
              <div className="rolling-placeholder rolling-in" key={`in-${current}`}>
                {placeholders[current]}
              </div>
            )}
          </div>
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
                title={t("attachFile")}
                onClick={() => { if (sandboxBlocked || !warmSessionId) { flashE2bHint(); return; } fileRef.current?.click(); }}
              >
                <Paperclip />
              </button>
              <InputSettingsMenu onOpenSettings={onOpenSettings} />
              {isCowork && (
                <FolderPicker
                  value={selectedFolder}
                  onChange={handleFolderChange}
                  disabled={vmNotReady}
                  onDisabledClick={flashE2bHint}
                />
              )}
            </div>
            <div className="input-toolbar-right">
              <ModelPicker />
              <div className="input-send-wrapper">
                <button
                  className="input-send"
                  onClick={handleSubmit}
                  disabled={sendDisabled}
                  title={sendTitle}
                >
                  {mountingFolder || isPreparingRequest ? <Loader2 className="model-save-spinner" /> : <ArrowUp />}
                </button>
                {mountingFolder && (
                  <div className="mount-hint mount-hint-visible">
                    <Loader2 size={12} className="model-save-spinner" />
                    <span>{t("mountingDirectory")}</span>
                  </div>
                )}
                {!mountingFolder && isPreparingRequest && (
                  <div className="mount-hint mount-hint-visible">
                    <Loader2 size={12} className="model-save-spinner" />
                    <span>{t("preparingRequest")}</span>
                  </div>
                )}
                {sandboxBlocked && (
                  <div className={`e2b-hint${value.trim() || e2bHintFlash ? " e2b-hint-visible" : ""}`}>
                    {missingE2bKey ? t("e2bKeyRequired") : t("vmSetupRequired")}{" "}
                    <button className="e2b-hint-link" onClick={() => onOpenSettings("sandbox")}>
                      {t("setupInSettings")}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
