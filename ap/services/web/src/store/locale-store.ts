/**
 * UI locale store.
 *
 * Zustand store + localStorage persistence for the user-selected UI language.
 * Civatas-TW: Traditional Chinese (zh-TW) is the default and source of truth;
 * English is available as a secondary locale via the StatusBar language button.
 * Missing translations fall back through the lookup table in `lib/i18n.ts`.
 *
 * Usage:
 *   const { locale, setLocale } = useLocaleStore();
 *   const t = useTr();   // preferred — see lib/i18n.ts
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

// All known UI locales. Add `"ja"` / `"ko"` here when those translations land.
export type UiLocale = "zh-TW" | "en";

// Cycle order for the StatusBar toggle button (zh-TW first — the default).
const LOCALE_CYCLE: UiLocale[] = ["zh-TW", "en"];

interface LocaleState {
  locale: UiLocale;
  setLocale: (l: UiLocale) => void;
  toggle: () => void;
}

export const useLocaleStore = create<LocaleState>()(
  persist(
    (set, get) => ({
      locale: "zh-TW", // 繁體中文為 Civatas-TW 的預設語言
      setLocale: (locale) => set({ locale }),
      toggle: () => {
        const cur = get().locale;
        const idx = LOCALE_CYCLE.indexOf(cur);
        const next = LOCALE_CYCLE[(idx + 1) % LOCALE_CYCLE.length];
        set({ locale: next });
      },
    }),
    {
      name: "civatas-locale",
      storage: {
        getItem: (name) => {
          if (typeof window === "undefined") return null;
          const str = localStorage.getItem(name);
          return str ? JSON.parse(str) : null;
        },
        setItem: (name, value) => {
          if (typeof window === "undefined") return;
          localStorage.setItem(name, JSON.stringify(value));
        },
        removeItem: (name) => {
          if (typeof window === "undefined") return;
          localStorage.removeItem(name);
        },
      },
    }
  )
);

/** Display label for each locale (used in the StatusBar toggle button). */
const LOCALE_LABEL: Record<UiLocale, string> = {
  "zh-TW": "中文",
  "en":    "EN",
};

/** Convenience helper: short label of the *next* locale in the cycle. */
export function nextLocaleLabel(current: UiLocale): string {
  const idx = LOCALE_CYCLE.indexOf(current);
  const next = LOCALE_CYCLE[(idx + 1) % LOCALE_CYCLE.length];
  return LOCALE_LABEL[next];
}
