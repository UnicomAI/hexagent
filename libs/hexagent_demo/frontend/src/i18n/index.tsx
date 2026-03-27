import { createContext, useContext, useMemo } from "react";
import en from "./en";
import zhCN from "./zh-CN";
import type { TranslationKeys, Translations } from "./en";
import type { Locale } from "./types";

export type { TranslationKeys, Translations };
export type { Locale, LanguageSetting } from "./types";
export { resolveLocale } from "./useLocale";

const translationMap: Record<Locale, Translations> = {
  en,
  "zh-CN": zhCN,
};

export const LANGUAGES: { code: Locale; nativeLabel: string }[] = [
  { code: "en", nativeLabel: "English" },
  { code: "zh-CN", nativeLabel: "简体中文" },
];

const I18nContext = createContext<Translations>(en);

export function I18nProvider({
  locale,
  children,
}: {
  locale: Locale;
  children: React.ReactNode;
}) {
  const translations = useMemo(() => translationMap[locale] ?? en, [locale]);
  return <I18nContext.Provider value={translations}>{children}</I18nContext.Provider>;
}

export function useTranslation() {
  const translations = useContext(I18nContext);

  const t = useMemo(() => {
    return (key: TranslationKeys, params?: Record<string, string | number>): string => {
      let value: string = translations[key] ?? key;
      if (params) {
        for (const [k, v] of Object.entries(params)) {
          value = value.replace(new RegExp(`\\{\\{${k}\\}\\}`, "g"), String(v));
        }
      }
      return value;
    };
  }, [translations]);

  return { t };
}
