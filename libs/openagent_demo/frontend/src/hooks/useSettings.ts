import { useState, useEffect, useCallback } from "react";

export interface Settings {
  fullName: string;
  theme: "light" | "dark" | "system";
}

const STORAGE_KEY = "openagent-settings";

const DEFAULT_SETTINGS: Settings = {
  fullName: "",
  theme: "dark",
};

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return { ...DEFAULT_SETTINGS, ...parsed };
    }
  } catch {
    // ignore
  }
  return DEFAULT_SETTINGS;
}

function saveSettings(settings: Settings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

function getEffectiveTheme(theme: "light" | "dark" | "system"): "light" | "dark" {
  if (theme === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return theme;
}

export function useSettings() {
  const [settings, setSettingsState] = useState<Settings>(loadSettings);

  const setSettings = useCallback((updater: Settings | ((prev: Settings) => Settings)) => {
    setSettingsState((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      saveSettings(next);
      return next;
    });
  }, []);

  // Apply theme to document
  useEffect(() => {
    const effective = getEffectiveTheme(settings.theme);
    document.documentElement.setAttribute("data-theme", effective);

    // Listen for system preference changes when using "system"
    if (settings.theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      const handler = (e: MediaQueryListEvent) => {
        document.documentElement.setAttribute("data-theme", e.matches ? "dark" : "light");
      };
      mq.addEventListener("change", handler);
      return () => mq.removeEventListener("change", handler);
    }
  }, [settings.theme]);

  return { settings, setSettings };
}
