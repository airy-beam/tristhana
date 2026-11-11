import { bundleFor, format, messageIds } from "./bundles";
import { LOCALES } from "./negotiate";

// ST-06 (spec §2): the copy the Mini App needs, in both languages. The bot's side and the
// sentences that must be gone are pinned in backend/tests/infrastructure/test_i18n_teacher_view.py.

const KEYS = [
  "students-days-note",
  "students-week",
  "students-last-asana",
  "students-last-standing",
  "students-blank-note",
  "students-quiet",
  "students-mark",
  "students-day-blank",
  "students-more",
  "students-load-failed",
  "links-students",
  "link-students-open",
  "day-label",
];

const plain = (text: string) => text.replace(/[⁨⁩]/g, "");

describe("ST-06 copy", () => {
  it.each(LOCALES)("%s: has every message", (locale) => {
    const ids = messageIds(locale);
    expect(KEYS.filter((id) => !ids.has(id))).toEqual([]);
  });

  it.each(LOCALES)("%s: the day lines read like the bot's", (locale) => {
    const bundle = bundleFor(locale);
    const vars = { date: "D", state: "S", length: "L" };
    expect(format(bundle, "students-day", vars)).toBe("D: S");
    expect(format(bundle, "students-day-length", vars)).toBe("D: S, L");
    expect(format(bundle, "students-day-blank-mark", vars)).toBe("D: ·");
  });

  it("reads as written", () => {
    const en = bundleFor("en");
    const ru = bundleFor("ru");
    expect(format(en, "students-more")).toBe("Show more");
    expect(format(ru, "students-more")).toBe("Показать ещё");
    expect(format(en, "students-load-failed")).toBe(
      "Couldn't load your students. Try again in a moment.",
    );
    expect(format(ru, "students-load-failed")).toBe(
      "Не получилось загрузить учеников. Попробуй ещё раз чуть позже.",
    );
    expect(format(en, "students-quiet")).toBe("Nothing shared for a while");
    expect(format(ru, "students-quiet")).toBe("Какое-то время показать нечего");
    expect(plain(format(en, "students-day-blank", { date: "Nov 5" }))).toBe(
      "Nov 5: nothing to show",
    );
    expect(plain(format(ru, "students-day-blank", { date: "5 нояб." }))).toBe(
      "5 нояб.: показать нечего",
    );
    expect(plain(format(en, "links-students", { count: 12 }))).toBe("👥 My students (12)");
    expect(plain(format(ru, "links-students", { count: 12 }))).toBe("👥 Мои ученики (12)");
    expect(format(en, "link-students-open")).toBe("👥 My students");
    expect(format(ru, "link-students-open")).toBe("👥 Мои ученики");
  });

  it("the last asana line carries the series in both languages", () => {
    expect(
      plain(
        format(bundleFor("en"), "students-last-asana", {
          asana: "Kapotasana",
          series: "Intermediate",
        }),
      ),
    ).toBe("Last asana, as marked in their log: Kapotasana (Intermediate)");
    expect(
      plain(
        format(bundleFor("ru"), "students-last-asana", { asana: "Капотасана", series: "вторая" }),
      ),
    ).toBe("Последняя асана по отметкам в журнале: Капотасана (вторая серия)");
  });

  it("the mark has two states, and a rest mark is the default", () => {
    const en = bundleFor("en");
    expect(format(en, "students-mark", { state: "practiced" })).toBe("🧘");
    expect(format(en, "students-mark", { state: "rest" })).toBe("😌");
    expect(format(en, "students-mark", { state: "anything" })).toBe("😌");
  });

  it("day-label reads as the bot's", () => {
    const en = bundleFor("en");
    const ru = bundleFor("ru");
    expect(plain(format(en, "day-label", { rel: "today", date: "Sat, Nov 7" }))).toBe(
      "Today, Sat, Nov 7",
    );
    expect(plain(format(en, "day-label", { rel: "yesterday", date: "Fri, Nov 6" }))).toBe(
      "Yesterday, Fri, Nov 6",
    );
    expect(plain(format(en, "day-label", { rel: "other", date: "Thu, Nov 5" }))).toBe("Thu, Nov 5");
    expect(plain(format(ru, "day-label", { rel: "today", date: "сб, 7 нояб." }))).toBe(
      "Сегодня, сб, 7 нояб.",
    );
  });

  it("the privacy line names the quiet note and drops the choice that doesn't exist", () => {
    const en = format(bundleFor("en"), "settings-privacy-sharing");
    const ru = format(bundleFor("ru"), "settings-privacy-sharing");
    expect(en).toContain(
      "If nothing shows for a while, the teacher sees a short note saying just that.",
    );
    expect(ru).toContain(
      "Если какое-то время показать нечего, учитель увидит об этом короткую пометку.",
    );
    expect(en).toContain("All rest you log looks the same, whatever the reason.");
    expect(ru).toContain("Любой отмеченный отдых выглядит одинаково, какой бы ни была причина.");
    expect(en).not.toContain("unless you choose");
    expect(en).not.toContain("get their own screen");
    expect(ru).not.toContain("если ты не решишь");
    expect(ru).not.toContain("появится свой экран");
  });

  it("the private notes quote the word the teacher sees", () => {
    for (const locale of LOCALES) {
      const bundle = bundleFor(locale);
      const word = format(bundle, "status-rest").split(" ").slice(1).join(" ");
      expect(format(bundle, "today-private-note")).toContain(word);
      expect(format(bundle, "settings-privacy-ladies")).toContain(word);
    }
  });
});
