/** UI-05: the public guide site. English pages are at the root, Russian ones under /ru/. */
export const GUIDE_URL = "https://tristhana.app";

/** A guide page in the person's language: `page` is its path under the language root, e.g.
 * `staff/classes/` (UI-06 stage 6: each screen links to its own page). The bot's twin is
 * `guide_url` in `bots/telegram/screens.py`. */
export function guideUrl(locale: string, page = ""): string {
  return `${GUIDE_URL}${locale === "ru" ? "/ru/" : "/"}${page}`;
}

/** Each screen's own guide page (UI-06 stage 6, polish C11). */
export const GUIDE_PAGE = {
  settings: "students/settings/",
  classes: "staff/classes/",
  createShala: "staff/create-shala/",
  inviteStudents: "teachers/invite-students/",
} as const;
