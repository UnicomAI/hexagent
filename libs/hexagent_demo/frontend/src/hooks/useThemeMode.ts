import { useSyncExternalStore } from "react";

function getSnapshot(): "light" | "dark" {
  return document.documentElement.getAttribute("data-theme") === "light"
    ? "light"
    : "dark";
}

function subscribe(onStoreChange: () => void): () => void {
  const observer = new MutationObserver(() => onStoreChange());
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}

/**
 * Reactive hook that returns "light" | "dark" based on the document's
 * `data-theme` attribute.  Re-renders when the theme changes.
 */
export function useThemeMode(): "light" | "dark" {
  return useSyncExternalStore(subscribe, getSnapshot, () => "dark");
}
