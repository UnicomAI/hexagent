import { useState, useCallback, useRef } from "react";

/**
 * Hook for drag-and-drop file upload on a container element.
 *
 * Returns `dragOver` state and four event handlers to spread onto the
 * drop target. When files are dropped, `onDrop` is called with them.
 */
export function useFileDrop(onDrop: (files: File[]) => void, onReject?: (reason: string) => void) {
  const [dragOver, setDragOver] = useState(false);
  const dragCounter = useRef(0);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current++;
    if (e.dataTransfer.types.includes("Files")) {
      setDragOver(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current--;
    if (dragCounter.current === 0) {
      setDragOver(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current = 0;
    setDragOver(false);
    // Filter out directories — only accept actual files
    const items = Array.from(e.dataTransfer.items);
    const files: File[] = [];
    let folderCount = 0;
    for (const item of items) {
      const entry = item.webkitGetAsEntry?.();
      if (entry && entry.isDirectory) { folderCount++; continue; }
      const file = item.getAsFile();
      if (file) files.push(file);
    }
    if (folderCount > 0) {
      onReject?.("Folder upload is not supported. Please select individual files instead.");
    }
    if (files.length > 0) {
      onDrop(files);
    }
  }, [onDrop, onReject]);

  return {
    dragOver,
    dragProps: {
      onDragEnter: handleDragEnter,
      onDragLeave: handleDragLeave,
      onDragOver: handleDragOver,
      onDrop: handleDrop,
    },
  };
}
