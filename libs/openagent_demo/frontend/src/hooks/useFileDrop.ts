import { useState, useCallback, useRef } from "react";

/**
 * Hook for drag-and-drop file upload on a container element.
 *
 * Returns `dragOver` state and four event handlers to spread onto the
 * drop target. When files are dropped, `onDrop` is called with them.
 */
export function useFileDrop(onDrop: (files: File[]) => void) {
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
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      onDrop(Array.from(files));
    }
  }, [onDrop]);

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
