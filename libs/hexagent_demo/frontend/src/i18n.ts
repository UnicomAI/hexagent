/**
 * i18n initialization for HexAgent frontend.
 *
 * ## Adding a new language
 * 1. Create a new folder under `src/locales/{locale}/` (e.g. `ja/`)
 * 2. Copy all JSON files from `src/locales/en/` and translate the values
 * 3. Import the JSON files below and add them to the `resources` object
 * 4. Add the language to the `LANGUAGES` array in `SettingsModal.tsx`
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

// English
import enCommon from "./locales/en/common.json";
import enSettings from "./locales/en/settings.json";
import enSidebar from "./locales/en/sidebar.json";
import enWelcome from "./locales/en/welcome.json";
import enChat from "./locales/en/chat.json";
import enSearch from "./locales/en/search.json";
import enMisc from "./locales/en/misc.json";
import enOnboarding from "./locales/en/onboarding.json";

// Simplified Chinese
import zhCNCommon from "./locales/zh-CN/common.json";
import zhCNSettings from "./locales/zh-CN/settings.json";
import zhCNSidebar from "./locales/zh-CN/sidebar.json";
import zhCNWelcome from "./locales/zh-CN/welcome.json";
import zhCNChat from "./locales/zh-CN/chat.json";
import zhCNSearch from "./locales/zh-CN/search.json";
import zhCNMisc from "./locales/zh-CN/misc.json";
import zhCNOnboarding from "./locales/zh-CN/onboarding.json";

// Read initial language from localStorage to avoid flash of wrong language
function getInitialLanguage(): string {
  try {
    const raw = localStorage.getItem("hexagent-settings");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.language) return parsed.language;
    }
  } catch {
    // ignore
  }
  return "en";
}

i18n.use(initReactI18next).init({
  resources: {
    en: {
      common: enCommon,
      settings: enSettings,
      sidebar: enSidebar,
      welcome: enWelcome,
      chat: enChat,
      search: enSearch,
      misc: enMisc,
      onboarding: enOnboarding,
    },
    "zh-CN": {
      common: zhCNCommon,
      settings: zhCNSettings,
      sidebar: zhCNSidebar,
      welcome: zhCNWelcome,
      chat: zhCNChat,
      search: zhCNSearch,
      misc: zhCNMisc,
      onboarding: zhCNOnboarding,
    },
  },
  lng: getInitialLanguage(),
  fallbackLng: "en",
  ns: ["common", "settings", "sidebar", "welcome", "chat", "search", "misc", "onboarding"],
  defaultNS: "common",
  interpolation: {
    escapeValue: false, // React already escapes
  },
});

export default i18n;
