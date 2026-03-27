import type { Locale, LanguageSetting } from "./types";

const SUPPORTED_LOCALES: Locale[] = ["en", "zh-CN"];

function detectBrowserLocale(): Locale {
  const lang = navigator.language || "";
  // Map any Chinese variant to zh-CN
  if (lang.startsWith("zh")) return "zh-CN";
  // Check if the base language matches a supported locale
  const base = lang.split("-")[0];
  const match = SUPPORTED_LOCALES.find((l) => l === lang || l.startsWith(base));
  return match ?? "en";
}

export function resolveLocale(setting: LanguageSetting): Locale {
  if (setting === "system") return detectBrowserLocale();
  return setting;
}
