import { FluentResource } from "@fluent/bundle";

import enApp from "../locales/en/app.ftl?raw";
import enClassRow from "../locales/en/class-row.ftl?raw";
import enDetails from "../locales/en/details.ftl?raw";
import ruApp from "../locales/ru/app.ftl?raw";
import ruClassRow from "../locales/ru/class-row.ftl?raw";
import ruDetails from "../locales/ru/details.ftl?raw";
import { addMessages } from "./lazyMessages";
import { LOCALES } from "./negotiate";
import { bundleFor, definedIdCount, format, messageIds, messageVariables } from "./bundles";

// UI-06: the day card's panels and the class row carry their copy in their own lazy chunks
// (`details.ftl`, `class-row.ftl`); here they are added as those chunks do it.
const DETAILS = { en: enDetails, ru: ruDetails };
const CLASS_ROW = { en: enClassRow, ru: ruClassRow };
addMessages(DETAILS);
addMessages(CLASS_ROW);

/** Each message of a raw `.ftl` source with the `$variables` it uses. */
function shape(source: string): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  let current: string | null = null;
  for (const line of source.split("\n")) {
    const start = /^([a-z][a-z0-9-]*)\s*=/.exec(line);
    if (start) current = start[1] ?? null;
    else if (!/^\s/.test(line)) current = null;
    if (!current) continue;
    const found = [...line.matchAll(/\{\s*\$([a-z_]+)/g)].map((m) => m[1] ?? "");
    out[current] = [...new Set([...(out[current] ?? []), ...found])].sort();
  }
  return out;
}

describe.each([
  ["details.ftl", DETAILS],
  ["class-row.ftl", CLASS_ROW],
])("%s (lazy copy)", (_file, sources) => {
  it("has the same messages and variables in en and ru", () => {
    expect(shape(sources.ru)).toEqual(shape(sources.en));
    expect(Object.keys(shape(sources.en)).length).toBeGreaterThan(0);
  });

  it.each(LOCALES)("%s: every message parses, and none repeats an app.ftl message", (locale) => {
    const ids = Object.keys(shape(sources[locale]));
    expect(new FluentResource(sources[locale]).body).toHaveLength(ids.length);
    expect(ids.filter((id) => messageIds(locale).has(id))).toEqual([]);
  });
});

describe("Fluent bundles", () => {
  it.each(LOCALES)("%s: every message parses (no junk)", (locale) => {
    expect(messageIds(locale).size).toBe(definedIdCount(locale));
  });

  it("every locale uses the same variables per message", () => {
    const [first, ...rest] = LOCALES.map(messageVariables);
    for (const vars of rest) expect(vars).toEqual(first);
    expect(first?.["home-greeting"]).toEqual(["name"]);
  });

  it("every locale has the same message ids", () => {
    const [first, ...rest] = LOCALES.map((locale) => [...messageIds(locale)].sort());
    for (const ids of rest) expect(ids).toEqual(first);
    expect(first).toContain("home-greeting");
  });

  it.each([
    [1, "1 день"],
    [2, "2 дня"],
    [5, "5 дней"],
    [11, "11 дней"],
    [21, "21 день"],
    [22, "22 дня"],
    [25, "25 дней"],
  ])("RU plural: %i -> %s", (count, expected) => {
    expect(format(bundleFor("ru"), "practice-days", { count })).toBe(expected);
  });

  it.each([
    [1, "1 day"],
    [2, "2 days"],
  ])("EN plural: %i -> %s", (count, expected) => {
    expect(format(bundleFor("en"), "practice-days", { count })).toBe(expected);
  });

  // WH-01 part 2 (spec §7): the pause copy, both locales.
  const WH01 = [
    "pause-ask",
    "pause-days",
    "pause-other",
    "pause-back",
    "pause-set",
    "today-period",
    "pause-end",
    "pause-ended",
    "pause-cut",
    "pause-keep",
    "pause-kept",
    "remind-paused-until",
    "remind-resume",
    "settings-ladies-button",
    "settings-ladies-button-hint",
  ];

  it.each(LOCALES)("%s: has every WH-01 message", (locale) => {
    const ids = messageIds(locale);
    expect(WH01.filter((id) => !ids.has(id))).toEqual([]);
  });

  it.each([
    [2, "2 дня"],
    [3, "3 дня"],
    [4, "4 дня"],
    [5, "5 дней"],
    [6, "6 дней"],
    [7, "7 дней"],
    [10, "10 дней"],
    [14, "14 дней"],
  ])("RU pause days: %i -> %s", (n, expected) => {
    expect(format(bundleFor("ru"), "pause-days", { n })).toBe(expected);
  });

  it("pause-end follows the reminders", () => {
    expect(format(bundleFor("en"), "pause-end", { reminders: "on" })).toBe("⏹ End the pause");
    expect(format(bundleFor("en"), "pause-end", { reminders: "off" })).toBe("⏹ End early");
    expect(format(bundleFor("ru"), "pause-end", { reminders: "off" })).toBe("⏹ Закончить раньше");
  });

  it("RU quotes the label with „…“ in the pause question", () => {
    const text = format(bundleFor("ru"), "pause-ask", {
      label: "🌸 Женские дни",
      rel: "today",
      reminders: "off",
    });
    expect(text).toBe("Сколько дней отметить как „🌸 Женские дни“, включая сегодня?");
  });

  it("formats the greeting with the user's name", () => {
    expect(format(bundleFor("ru"), "home-greeting", { name: "Аня" })).toContain("Намасте, Аня");
  });
});

// PR-06 (spec §6): the check-in copy, both locales, and the words it never uses.

const PR06 = [
  "checkin-summary-energy",
  "checkin-summary-effort",
  "checkin-mood",
  "checkin-energy",
  "checkin-effort",
  "checkin-body",
  "checkin-mind",
  "checkin-mood-label",
  "checkin-mood-chip",
  "checkin-tag",
  "checkin-edit",
  "checkin-clear",
  "checkin-save-failed",
  "settings-checkin",
  "settings-checkin-hint",
];

const TAG_LABELS: [string, string, string][] = [
  ["stiff", "Stiff", "Скованность"],
  ["open", "Open", "Раскрытость"],
  ["strong", "Strong", "Сила"],
  ["light", "Light", "Лёгкость"],
  ["heavy", "Heavy", "Тяжесть"],
  ["sore", "Sore muscles", "Ноющие мышцы"],
  ["focused", "Focused", "Собранность"],
  ["calm", "Calm", "Спокойствие"],
  ["scattered", "Scattered", "Рассеянность"],
  ["steady_breath", "Steady breath", "Ровное дыхание"],
];

const AVOID = [
  "missed",
  "forgot",
  "bad",
  "pain",
  "push",
  "should",
  "only",
  "again",
  "streak",
  "recovery",
  "training load",
  "плохо",
  "пропустил",
  "боль",
  "надо",
  "всего лишь",
  "опять",
];

/** The raw source (every variant) of each `checkin-*` / `settings-checkin*` message. */
function checkInSources(source: string): Record<string, string> {
  const out: Record<string, string> = {};
  let current: string | null = null;
  for (const line of source.split("\n")) {
    const start = /^([a-z][a-z0-9-]*)\s*=(.*)$/.exec(line);
    if (start) {
      const id = start[1] ?? "";
      current = id.startsWith("checkin-") || id.startsWith("settings-checkin") ? id : null;
      if (current) out[current] = start[2] ?? "";
    } else if (current && /^\s/.test(line)) {
      out[current] = `${out[current] ?? ""}\n${line}`;
    } else {
      current = null;
    }
  }
  return out;
}

describe("PR-06 check-in copy", () => {
  it.each(LOCALES)("%s: has every PR-06 message, in app.ftl or details.ftl", (locale) => {
    const ids = new Set([...messageIds(locale), ...Object.keys(shape(DETAILS[locale]))]);
    expect(PR06.filter((id) => !ids.has(id))).toEqual([]);
  });

  it("reads as written: the entry carries the bot's words (UI-06)", () => {
    expect(format(bundleFor("en"), "checkin-edit")).toBe("✨ How do you feel?");
    expect(format(bundleFor("ru"), "checkin-edit")).toBe("✨ Как самочувствие?");
    expect(format(bundleFor("en"), "checkin-summary-energy", { n: 4 })).toBe("⚡ energy 4/5");
    expect(format(bundleFor("ru"), "checkin-summary-effort", { n: 3 })).toBe("🔥 усилие 3/5");
    expect(format(bundleFor("en"), "checkin-clear")).toBe("Remove check-in");
    expect(format(bundleFor("ru"), "checkin-clear")).toBe("Убрать самочувствие");
    // Q313: the setting shows or hides the entry; it no longer promises "add one from the day".
    expect(format(bundleFor("en"), "settings-checkin")).toBe(
      "Show “How do you feel?” after practice",
    );
    expect(format(bundleFor("ru"), "settings-checkin")).toBe(
      "Показывать «Как самочувствие?» после практики",
    );
    expect(format(bundleFor("en"), "settings-checkin-hint")).toBe(
      "Mood, energy and effort on a day you practiced. A check-in you already made stays and can be changed.",
    );
    expect(format(bundleFor("ru"), "settings-checkin-hint")).toBe(
      "Настроение, энергия и усилие в день практики. Уже сделанная отметка остаётся, и её можно изменить.",
    );
  });

  it.each([1, 2, 3, 4, 5])("mood %i: an emoji and an aria label", (n) => {
    expect(format(bundleFor("en"), "checkin-mood-chip", { n })).toBe(
      ["😔", "😕", "😐", "🙂", "😊"][n - 1],
    );
    expect(format(bundleFor("en"), "checkin-mood-label", { n })).toBe(`Mood ${String(n)} of 5`);
    expect(format(bundleFor("ru"), "checkin-mood-label", { n })).toBe(
      `Настроение ${String(n)} из 5`,
    );
  });

  it.each(TAG_LABELS)("tag %s has a label in both locales", (tag, en, ru) => {
    expect(format(bundleFor("en"), "checkin-tag", { tag })).toBe(en);
    expect(format(bundleFor("ru"), "checkin-tag", { tag })).toBe(ru);
  });

  it.each([
    ["en", `${enApp}\n${enDetails}`],
    ["ru", `${ruApp}\n${ruDetails}`],
  ])("%s: never uses a word to avoid", (_locale, source) => {
    const sources = checkInSources(source);
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(PR06.length);
    const found = Object.entries(sources).flatMap(([id, text]) =>
      AVOID.filter((word) => new RegExp(`(^|[^\\p{L}])${word}`, "iu").test(text)).map(
        (word) => `${id}: ${word}`,
      ),
    );
    expect(found).toEqual([]);
  });
});

// PR-07 (spec §6): the diary copy, both locales, and the words it never uses (PR-06's list
// plus the diary's own).

const PR07 = [
  "diary-title",
  "diary-add",
  "diary-row",
  "diary-edit",
  "diary-save",
  "diary-cancel",
  "diary-counter",
  "diary-save-failed",
  "diary-private-hint",
  "diary-unreadable",
  "diary-clear",
  "diary-clear-confirm",
  "diary-clear-yes",
  "diary-removed",
];

const DIARY_AVOID = [
  ...AVOID,
  "journal",
  "wrong",
  "mistake",
  "fail",
  "improve",
  "progress",
  "goal",
  "performance",
  "achieve",
  "lazy",
  "excuse",
  "keep up",
  "don't forget",
  "remember to",
  "every day",
  "habit",
  "журнал",
  "ошибк",
  "неудач",
  "прогресс",
  "цель",
  "результат",
  "лень",
  "оправдан",
  "не забудь",
  "каждый день",
  "привычк",
  "должен",
  "должна",
];

/** The raw source (every variant) of each `diary-*` message. */
function diarySources(source: string): Record<string, string> {
  const out: Record<string, string> = {};
  let current: string | null = null;
  for (const line of source.split("\n")) {
    const start = /^([a-z][a-z0-9-]*)\s*=(.*)$/.exec(line);
    if (start) {
      const id = start[1] ?? "";
      current = id.startsWith("diary-") ? id : null;
      if (current) out[current] = start[2] ?? "";
    } else if (current && /^\s/.test(line)) {
      out[current] = `${out[current] ?? ""}\n${line}`;
    } else {
      current = null;
    }
  }
  return out;
}

describe("PR-07 diary copy", () => {
  it.each(LOCALES)("%s: has every PR-07 message", (locale) => {
    const ids = messageIds(locale);
    expect(PR07.filter((id) => !ids.has(id))).toEqual([]);
  });

  it("reads as written", () => {
    const en = bundleFor("en");
    const ru = bundleFor("ru");
    expect(format(en, "diary-title")).toBe("Diary");
    expect(format(ru, "diary-title")).toBe("Дневник");
    // The bot's 📓, as every list row has an icon (UI-06).
    expect(format(en, "diary-add")).toBe("📓 Add a note");
    expect(format(ru, "diary-add")).toBe("📓 Добавить заметку");
    expect(format(en, "diary-row")).toBe("📓 Note");
    expect(format(ru, "diary-row")).toBe("📓 Заметка");
    expect(format(en, "diary-private-hint")).toBe("Your diary is private: teachers don't see it.");
    expect(format(ru, "diary-private-hint")).toBe("Дневник личный: учителя его не видят.");
    expect(format(en, "diary-clear")).toBe("Remove note");
    expect(format(ru, "diary-clear")).toBe("Удалить заметку");
    expect(format(en, "diary-clear-confirm")).toBe("Remove this note?");
    expect(format(ru, "diary-clear-confirm")).toBe("Удалить заметку?");
    expect(format(en, "diary-clear-yes")).toBe("Remove");
    expect(format(ru, "diary-clear-yes")).toBe("Удалить");
    expect(format(en, "diary-removed")).toBe("Removed from your diary.");
    expect(format(ru, "diary-removed")).toBe("Заметка удалена из дневника.");
    expect(format(en, "diary-unreadable")).toBe(
      "This note can't be read right now. You can write a new one or remove it.",
    );
    expect(format(ru, "diary-unreadable")).toBe(
      "Эту заметку сейчас не получается прочитать. Можно написать новую или удалить старую.",
    );
    expect(format(en, "diary-save")).toMatch(/^save$/i);
    expect(format(en, "diary-cancel")).toMatch(/^cancel$/i);
    expect(format(en, "diary-edit")).toMatch(/edit/i);
  });

  it.each(LOCALES)("%s: the counter shows both numbers, plural-free", (locale) => {
    const text = format(bundleFor(locale), "diary-counter", { n: 1850, max: 2000 });
    expect(text).toMatch(/1[,.\s\u00a0\u202f]?850/);
    expect(text).toMatch(/2[,.\s\u00a0\u202f]?000/);
    expect(messageVariables(locale)["diary-counter"]?.sort()).toEqual(["max", "n"]);
  });

  it.each([
    ["en", enApp],
    ["ru", ruApp],
  ])("%s: never uses a word to avoid", (_locale, source) => {
    const sources = diarySources(source);
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(PR07.length);
    const found = Object.entries(sources).flatMap(([id, text]) =>
      DIARY_AVOID.filter((word) => new RegExp(`(^|[^\\p{L}'])${word}`, "iu").test(text)).map(
        (word) => `${id}: ${word}`,
      ),
    );
    expect(found).toEqual([]);
  });

  it.each([
    ["en", enApp],
    ["ru", ruApp],
  ])("%s: the Add link never nudges (no 'yet', no question, no count)", (_locale, source) => {
    const add = diarySources(source)["diary-add"] ?? "";
    expect(add).not.toMatch(/yet|пока|\?|\d/i);
  });

  it.each([
    ["en", enApp],
    ["ru", ruApp],
  ])("%s: the diary icon is 📓, never a flower, a lotus or 📝", (_locale, source) => {
    const all = Object.values(diarySources(source)).join(" ");
    for (const icon of ["📝", "📖", "🪷", "🙏", "🌸", "🌺", "🌼", "🌷"]) {
      expect(all).not.toContain(icon);
    }
  });
});

// NF-09: comments are notes for whoever edits the copy. The build drops them from every
// `.ftl` (`vite.config.ts`), so the first chunk carries the messages only.
describe("the copy as it ships", () => {
  const sources = import.meta.glob<string>("../locales/*/*.ftl", {
    query: "?raw",
    import: "default",
    eager: true,
  });

  it.each(Object.entries(sources))("%s has no comment lines", (_path, source) => {
    expect(source.split("\n").filter((line) => line.startsWith("#"))).toEqual([]);
    expect(source).toMatch(/^[a-z][a-z0-9-]* = /m); // and still has its messages
  });

  it("keeps every message: none is lost with its comment", () => {
    for (const locale of LOCALES) {
      expect(messageIds(locale).size).toBe(definedIdCount(locale));
      expect(messageIds(locale).size).toBeGreaterThan(500);
    }
  });
});
