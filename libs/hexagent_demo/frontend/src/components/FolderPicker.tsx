import { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { FolderOpen, FolderPlus, ChevronDown, Check, ShieldAlert } from "lucide-react";
import { browseFolder } from "../api";
import { loadRecentFolders, saveRecentFolders, shortenPath } from "../recentFolders";
import type { RecentFolder } from "../recentFolders";

interface FolderPickerProps {
  value: string;
  onChange: (folder: string) => void;
  disabled?: boolean;
  onDisabledClick?: () => void;
}

export default function FolderPicker({ value, onChange, disabled, onDisabledClick }: FolderPickerProps) {
  const [open, setOpen] = useState(false);
  const [recentFolders, setRecentFolders] = useState<RecentFolder[]>(loadRecentFolders);
  const [pendingFolder, setPendingFolder] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const upsertRecent = useCallback(
    (path: string, alwaysAllowed: boolean) => {
      const updated = [
        { path, alwaysAllowed },
        ...recentFolders.filter((f) => f.path !== path),
      ].slice(0, 8);
      setRecentFolders(updated);
      saveRecentFolders(updated);
    },
    [recentFolders]
  );

  const isAlwaysAllowed = useCallback(
    (path: string) => recentFolders.some((f) => f.path === path && f.alwaysAllowed),
    [recentFolders]
  );

  const confirmFolder = useCallback(
    (path: string, alwaysAllowed: boolean) => {
      upsertRecent(path, alwaysAllowed);
      onChange(path);
      setPendingFolder(null);
      setOpen(false);
    },
    [onChange, upsertRecent]
  );

  const requestAccess = useCallback(
    (path: string) => {
      if (isAlwaysAllowed(path)) {
        // Already trusted — skip the dialog
        confirmFolder(path, true);
      } else {
        setPendingFolder(path);
      }
    },
    [isAlwaysAllowed, confirmFolder]
  );

  const handleBrowse = useCallback(async () => {
    const path = await browseFolder();
    if (path) {
      requestAccess(path);
    }
  }, [requestAccess]);

  const handleButtonClick = useCallback(() => {
    if (disabled) { onDisabledClick?.(); return; }
    if (!value && recentFolders.length === 0) {
      // No selection and no recents — go straight to native picker
      handleBrowse();
    } else {
      setOpen(!open);
    }
  }, [value, open, handleBrowse, recentFolders.length, disabled, onDisabledClick]);

  const selectRecent = useCallback(
    (folder: RecentFolder) => {
      if (folder.path === value) {
        // Toggle off
        onChange("");
        setOpen(false);
      } else {
        requestAccess(folder.path);
      }
    },
    [onChange, requestAccess, value]
  );

  const label = value ? value.split("/").pop() || value : "Work in a folder";

  return (
    <>
      <div className="fp" ref={ref}>
        <button
          className="input-tool-btn input-folder-btn"
          onClick={handleButtonClick}
          type="button"
          title={value || "Work in a folder"}
        >
          <FolderOpen size={16} />
          <span>{label}</span>
          <ChevronDown size={14} className={`fp-chevron ${open ? "fp-chevron--open" : ""}`} />
        </button>
        {open && (
          <div className="dd-panel fp-dropdown">
            <button className="dd-item fp-browse" onClick={handleBrowse}>
              <FolderPlus size={14} className="fp-option-icon" />
              <span className="dd-item-label">Choose a new folder</span>
            </button>
            {recentFolders.length > 0 && (
              <>
                <div className="dd-divider" />
                <div className="fp-section-label">Recent</div>
                {recentFolders.map((folder) => (
                  <button
                    key={folder.path}
                    className={`dd-item ${folder.path === value ? "dd-item--active" : ""}`}
                    onClick={() => selectRecent(folder)}
                  >
                    <FolderOpen size={14} className="fp-option-icon" />
                    <span className="dd-item-label" title={folder.path}>{shortenPath(folder.path, 45)}</span>
                    {folder.path === value && (
                      <span className="dd-item-check">
                        <Check size={14} strokeWidth={2.5} />
                      </span>
                    )}
                  </button>
                ))}
              </>
            )}
          </div>
        )}
      </div>

      {pendingFolder && createPortal(
        <div className="fp-permission-overlay" onClick={() => setPendingFolder(null)}>
          <div className="fp-permission-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="fp-permission-icon">
              <ShieldAlert size={28} />
            </div>
            <h3 className="fp-permission-title">
              Allow HexAgent to access files in "{pendingFolder}"?
            </h3>
            <p className="fp-permission-body">
              This grants access to all files and subfolders. HexAgent will be able to read, edit, and delete files in this directory. File contents may be shared with connected AI models and tools. Avoid selecting folders containing sensitive or private data.
            </p>
            <div className="fp-permission-actions">
              <button
                className="fp-permission-btn fp-permission-btn--cancel"
                onClick={() => setPendingFolder(null)}
              >
                Cancel
              </button>
              <button
                className="fp-permission-btn fp-permission-btn--always"
                onClick={() => confirmFolder(pendingFolder, true)}
              >
                Always Allow
              </button>
              <button
                className="fp-permission-btn fp-permission-btn--allow"
                onClick={() => confirmFolder(pendingFolder, false)}
              >
                Allow
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
