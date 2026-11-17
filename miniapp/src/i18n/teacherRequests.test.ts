import enRequests from "../locales/en/requests.ftl?raw";
import ruRequests from "../locales/ru/requests.ftl?raw";
import { bundleFor, format, messageIds } from "./bundles";
import { addMessages } from "./lazyMessages";
import { LOCALES } from "./negotiate";

// ID-07 (spec §2, §8): the copy of the teacher's waiting block and the student's waiting line.
// It comes with the lazy screens (`requests.ftl`); here it is added as they add it. The bot's
// wording is pinned in backend/tests/infrastructure/test_i18n_teacher_requests.py.
const SOURCES = { en: enRequests, ru: ruRequests };
addMessages(SOURCES);

/** What the teacher reads. */
const TEACHER = [
  "request-waiting-open",
  "request-list-empty",
  "request-list-hint",
  "request-yes-mine",
  "request-not-mine",
  "request-declined",
  "request-undo",
  "request-gone",
  "request-list-full",
  "request-all",
  "request-all-ask",
  "request-all-yes",
  "request-all-done",
  "request-load-failed",
  "link-student-joined",
];
/** What the student reads: nothing here may tell a "no" from silence. */
const STUDENT = [
  "request-waiting-line",
  "request-withdraw",
  "request-withdraw-ask",
  "request-withdraw-yes",
];

/** The messages of a raw source, by id. */
function messages(source: string): Record<string, string> {
  const out: Record<string, string> = {};
  let current: string | null = null;
  for (const line of source.split("\n")) {
    const start = /^([a-z][a-z0-9-]*)\s*=(.*)$/.exec(line);
    if (start?.[1]) {
      current = start[1];
      out[current] = start[2] ?? "";
    } else if (current && /^\s/.test(line)) out[current] = `${out[current] ?? ""}\n${line}`;
    else current = null;
  }
  return out;
}

describe("ID-07 copy", () => {
  it.each(LOCALES)("%s: has every message, and no other", (locale) => {
    expect(Object.keys(messages(SOURCES[locale])).sort()).toEqual([...TEACHER, ...STUDENT].sort());
    const ids = messageIds(locale);
    expect([...TEACHER, ...STUDENT].filter((id) => ids.has(id))).toEqual([]); // not in app.ftl too
  });

  it("the answers read as the bot's buttons", () => {
    const en = bundleFor("en");
    const ru = bundleFor("ru");
    expect(format(en, "request-yes-mine")).toBe("✅ Yes, my student");
    expect(format(ru, "request-yes-mine")).toBe("✅ Да, мой ученик");
    expect(format(en, "request-not-mine")).toBe("Not my student");
    expect(format(ru, "request-not-mine")).toBe("Не мой ученик");
    expect(format(en, "request-undo")).toBe("↩️ Undo");
    expect(format(ru, "request-undo")).toBe("↩️ Отменить");
    expect(format(en, "request-all", { count: 3 })).toBe("✅ Confirm all (3)");
    expect(format(ru, "request-all", { count: 3 })).toBe("✅ Подтвердить всех (3)");
    expect(format(en, "request-withdraw-yes")).toBe("Withdraw");
    expect(format(ru, "request-withdraw-yes")).toBe("Отозвать");
  });

  it.each([
    [1, "Confirm 1 person as your student? Confirm only if you know them."],
    [4, "Confirm all 4 people as your students? Confirm only if you know each of them."],
  ])("EN: Confirm all asks about %i", (count, expected) => {
    expect(format(bundleFor("en"), "request-all-ask", { count })).toBe(expected);
  });

  it.each([
    [1, "✅ 1 ученик теперь в твоём списке."],
    [3, "✅ 3 ученика теперь в твоём списке."],
    [11, "✅ 11 учеников теперь в твоём списке."],
    [21, "✅ 21 ученик теперь в твоём списке."],
  ])("RU plural: %i confirmed", (count, expected) => {
    expect(format(bundleFor("ru"), "request-all-done", { count })).toBe(expected);
  });

  it.each([
    [1, "✅ 1 student is on your list now."],
    [2, "✅ 2 students are on your list now."],
  ])("EN plural: %i confirmed", (count, expected) => {
    expect(format(bundleFor("en"), "request-all-done", { count })).toBe(expected);
  });

  it("the waiting line names the shala and nothing else", () => {
    expect(format(bundleFor("en"), "request-waiting-line", { shala: "Mysore Room" })).toBe(
      "⏳ Waiting for an answer (Mysore Room)",
    );
    expect(format(bundleFor("ru"), "request-waiting-line", { shala: "Mysore Room" })).toBe(
      "⏳ Ждём ответа (Mysore Room)",
    );
  });

  it.each(LOCALES)("%s: nothing the student reads has a word for a refusal", (locale) => {
    const found = messages(SOURCES[locale]);
    for (const id of STUDENT) {
      expect(id).not.toMatch(/declin|reject|refus/);
      expect(found[id]).not.toMatch(/отклон|отказ|declin|reject|refus|not your|не тво/i);
    }
  });

  it.each(LOCALES)("%s: no line anywhere says declined or rejected", (locale) => {
    for (const text of Object.values(messages(SOURCES[locale]))) {
      expect(text).not.toMatch(/отклон|отказ|declined|rejected/i);
    }
  });

  it("RU speaks as «ты», with no gendered past tense about the reader", () => {
    for (const text of Object.values(messages(SOURCES.ru))) {
      expect(text).not.toMatch(/(?<![а-яё])(вы|вас|вам|ваш[а-яё]*)(?![а-яё])/i);
      expect(text).not.toMatch(/(?<![а-яё])ты [а-яё]+(л|ла)(?![а-яё])/i);
    }
  });
});
