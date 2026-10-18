// Mirrors backend/src/tristhana/domain/locale.py; both are tested against
// data/i18n/locale_cases.json. Russian is widely used in these countries (decision 2026-10-18).
export const LOCALES = ["en", "ru"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";

const RUSSIAN_SPEAKING = new Set(["ru", "be", "kk", "ky"]);

export function negotiateLocale(languageCode: string | null | undefined): Locale {
  if (!languageCode) return DEFAULT_LOCALE;
  const primary = languageCode.trim().toLowerCase().replace("_", "-").split("-")[0] ?? "";
  return RUSSIAN_SPEAKING.has(primary) ? "ru" : DEFAULT_LOCALE;
}
