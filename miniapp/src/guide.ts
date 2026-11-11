/** UI-05: the public guide site. English pages are at the root, Russian ones under /ru/. */
export const GUIDE_URL = "https://tristhana.app";

export function guideUrl(locale: string): string {
  return `${GUIDE_URL}${locale === "ru" ? "/ru/" : "/"}`;
}
