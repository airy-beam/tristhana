import { FluentResource } from "@fluent/bundle";

import enApp from "../locales/en/app.ftl?raw";
import enAsk from "../locales/en/ask.ftl?raw";
import enClassRow from "../locales/en/class-row.ftl?raw";
import enDetails from "../locales/en/details.ftl?raw";
import enPractice from "../locales/en/practice.ftl?raw";
import enRequests from "../locales/en/requests.ftl?raw";
import enSettings from "../locales/en/settings.ftl?raw";
import enShala from "../locales/en/shala.ftl?raw";
import ruApp from "../locales/ru/app.ftl?raw";
import ruAsk from "../locales/ru/ask.ftl?raw";
import ruClassRow from "../locales/ru/class-row.ftl?raw";
import ruDetails from "../locales/ru/details.ftl?raw";
import ruPractice from "../locales/ru/practice.ftl?raw";
import ruRequests from "../locales/ru/requests.ftl?raw";
import ruSettings from "../locales/ru/settings.ftl?raw";
import ruShala from "../locales/ru/shala.ftl?raw";
import { addMessages } from "./lazyMessages";
import { LOCALES } from "./negotiate";
import { bundleFor, definedIdCount, format, messageIds, messageVariables } from "./bundles";

// UI-06: the day card's panels and the class row carry their copy in their own lazy chunks
// (`details.ftl`, `class-row.ftl`); here they are added as those chunks do it.
const DETAILS = { en: enDetails, ru: ruDetails };
const CLASS_ROW = { en: enClassRow, ru: ruClassRow };
// UI-06 stage 4: the class form, the occurrence sheet's groups and the setup list (`shala.ftl`).
const SHALA = { en: enShala, ru: ruShala };
// ID-07: the waiting block and the waiting line (`requests.ftl`).
const REQUESTS = { en: enRequests, ru: ruRequests };
// UI-06 stage 4B: the picker's copy, the bot's own messages (`ask.ftl`, ADR-0049).
const ASK = { en: enAsk, ru: ruAsk };
addMessages(DETAILS);
addMessages(CLASS_ROW);
addMessages(SHALA);
// UI-06 stage 3: the Practice tab's own copy (`practice.ftl`).
const PRACTICE = { en: enPractice, ru: ruPractice };
// UI-06 stage 3: Settings' rows and pages (`settings.ftl`).
const SETTINGS = { en: enSettings, ru: ruSettings };
addMessages(REQUESTS);
addMessages(ASK);
addMessages(PRACTICE);
addMessages(SETTINGS);

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
  ["shala.ftl", SHALA],
  ["requests.ftl", REQUESTS],
  ["ask.ftl", ASK],
  ["practice.ftl", PRACTICE],
  ["settings.ftl", SETTINGS],
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
// Two phrases the list never meant (UI-06 stage 5 review): "Try again" asks for a retry after an
// error, and "Only you see" is the privacy promise. Neither judges the person or makes their
// practice small, so they are read out before the words above are looked for.
const AVOID_FREE = [/\btry again\b/giu, /\bonly you\b/giu];
const toneOf = (text: string) => AVOID_FREE.reduce((t, re) => t.replace(re, " "), text);

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
    expect(format(bundleFor("en"), "checkin-clear")).toBe("Remove answers");
    expect(format(bundleFor("ru"), "checkin-clear")).toBe("Убрать ответы");
    // Q313: the setting shows or hides the entry; it no longer promises "add one from the day".
    expect(format(bundleFor("en"), "settings-checkin")).toBe(
      "Show “How do you feel?” after practice",
    );
    expect(format(bundleFor("ru"), "settings-checkin")).toBe(
      "Показывать «Как самочувствие?» после практики",
    );
    expect(format(bundleFor("en"), "settings-checkin-hint")).toBe(
      "A few short questions on days you practice: mood, energy, effort, body and mind. If you turn this off, your answers stay and you can still change them.",
    );
    expect(format(bundleFor("ru"), "settings-checkin-hint")).toBe(
      "Несколько коротких вопросов в дни практики: настроение, энергия, усилие, тело и ум. Если выключить, ответы останутся, и их можно будет изменить.",
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
      AVOID.filter((word) => new RegExp(`(^|[^\\p{L}])${word}`, "iu").test(toneOf(text))).map(
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
    expect(format(en, "diary-title")).toBe("Note");
    expect(format(ru, "diary-title")).toBe("Заметка");
    // The bot's 📓, as every list row has an icon (UI-06).
    expect(format(en, "diary-add")).toBe("📓 Add a note");
    expect(format(ru, "diary-add")).toBe("📓 Добавить заметку");
    expect(format(en, "diary-row")).toBe("📓 Note");
    expect(format(ru, "diary-row")).toBe("📓 Заметка");
    expect(format(en, "diary-private-hint")).toBe("Only you see your notes.");
    expect(format(ru, "diary-private-hint")).toBe("Заметки видишь только ты.");
    expect(format(en, "diary-clear")).toBe("Remove note");
    expect(format(ru, "diary-clear")).toBe("Убрать заметку");
    expect(format(en, "diary-clear-confirm")).toBe("Remove this note?");
    expect(format(ru, "diary-clear-confirm")).toBe("Убрать заметку?");
    expect(format(en, "diary-clear-yes")).toBe("Remove");
    expect(format(ru, "diary-clear-yes")).toBe("Убрать");
    expect(format(en, "diary-removed")).toBe("Note removed.");
    expect(format(ru, "diary-removed")).toBe("Заметка убрана.");
    expect(format(en, "diary-unreadable")).toBe(
      "This note can't be read right now. You can write a new one or remove it.",
    );
    expect(format(ru, "diary-unreadable")).toBe(
      "Эту заметку сейчас не получается прочитать. Можно написать новую или убрать старую.",
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
      DIARY_AVOID.filter((word) =>
        new RegExp(`(^|[^\\p{L}'])${word}`, "iu").test(toneOf(text)),
      ).map((word) => `${id}: ${word}`),
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

// UI-06 stage 3 (spec §7): the Practice tab. Four legend words, one number, plain plurals; a run
// is "in a row", and nothing reads as a day that went wrong.
describe("the Practice tab's copy", () => {
  const en = bundleFor("en");
  const ru = bundleFor("ru");

  it.each([
    [0, "📅 2026 · the whole year", "📅 2026 · весь год"],
    [1, "📅 2026 · 1 practice", "📅 2026 · 1 практика"],
    [3, "📅 2026 · 3 practices", "📅 2026 · 3 практики"],
    [5, "📅 2026 · 5 practices", "📅 2026 · 5 практик"],
    [21, "📅 2026 · 21 practices", "📅 2026 · 21 практика"],
    [143, "📅 2026 · 143 practices", "📅 2026 · 143 практики"],
  ])("the year row with %i practices", (n, english, russian) => {
    expect(format(en, "stats-year-open", { year: "2026", n })).toBe(english);
    expect(format(ru, "stats-year-open", { year: "2026", n })).toBe(russian);
  });

  it("names the moon phase and the city on a day's card", () => {
    expect(format(en, "stats-day-moon", { phase: "purnima", city: "Mysuru" })).toBe(
      "🌕 Full moon · 📍 Mysuru",
    );
    expect(format(ru, "stats-day-moon", { phase: "amavasya", city: "Майсур" })).toBe(
      "🌑 Новолуние · 📍 Майсур",
    );
  });

  it("counts 'of' for any month, with the Russian genitive", () => {
    expect(format(en, "stats-consistency", { x: 9, y: 10 })).toBe("Practice on 9 of 10 days");
    expect(format(ru, "stats-consistency", { x: 9, y: 10 })).toBe("Практика в 9 из 10 дней");
    expect(format(ru, "stats-consistency", { x: 18, y: 21 })).toBe("Практика в 18 из 21 дня");
  });

  it("reads as written", () => {
    expect(format(en, "stats-more")).toBe("The month in numbers");
    expect(format(ru, "stats-more")).toBe("Месяц в цифрах");
    expect(format(en, "stats-legend-label")).toBe("What the marks mean");
    expect(format(ru, "stats-legend-label")).toBe("Что означают отметки");
    expect(format(en, "stats-show-ladies")).toBe("Show 🌸 in My practice");
    expect(format(ru, "stats-show-ladies")).toBe("Показывать 🌸 в «Моей практике»");
    expect(format(en, "stats-month-rest")).toBe("Rest is part of practice too.");
    expect(format(ru, "stats-month-rest")).toBe("Отдых тоже часть практики.");
    // No count: only where to tap.
    expect(format(en, "stats-unlogged")).toBe("Tap a day to add or change it.");
    expect(format(ru, "stats-unlogged")).toBe("Нажми на день, чтобы отметить или изменить.");
    expect(format(en, "stats-show-ladies-hint")).toBe(
      "On this phone only. While it's off, these days look like rest.",
    );
    expect(format(ru, "stats-show-ladies-hint")).toBe(
      "Только на этом телефоне. Пока выключено, эти дни выглядят как отдых.",
    );
  });

  it.each(LOCALES)("%s: the eight-item legend's keys are gone, the kept ones stay", (locale) => {
    const ids = new Set([...messageIds(locale), ...Object.keys(shape(PRACTICE[locale]))]);
    for (const gone of [
      "stats-legend-moon",
      "stats-legend-auto",
      "stats-legend-away",
      "stats-legend-skipped",
      "stats-legend-moon-marker",
      "stats-consistency-count",
    ]) {
      expect(ids.has(gone)).toBe(false);
    }
    for (const kept of ["stats-legend-practiced", "stats-legend-rest", "stats-legend-none"]) {
      expect(ids.has(kept)).toBe(true);
    }
  });

  it.each([
    ["en", enPractice],
    ["ru", ruPractice],
  ])("%s: never a streak, a miss or a skipped day", (_locale, source) => {
    expect(source).not.toMatch(/streak|missed|skipp|пропуск|серия|серии|полос/i);
  });
});

// UI-06 stage 3 (spec §4, §7): Settings. The rows are the bot's own lines (the site's test
// keeps the two files in step); here, that they read right with their values.
describe("Settings' copy", () => {
  const en = bundleFor("en");
  const ru = bundleFor("ru");

  it("puts the value on each row", () => {
    expect(format(en, "settings-language-line", { language: "English" })).toBe(
      "🗣 Language: English",
    );
    expect(format(ru, "settings-city-line", { zone: "Алматы" })).toBe("🏙 Мой город: Алматы");
    expect(format(en, "settings-city-unset-line", { zone: "Almaty (UTC+5)" })).toBe(
      "🏙 My city? 🕐 Almaty (UTC+5)",
    );
    expect(format(ru, "settings-city-unlisted-line", { zone: "Алматы (UTC+5)" })).toBe(
      "🕐 Моё время: Алматы (UTC+5)",
    );
  });

  it.each([
    [1, "😌 Day off: Monday", "😌 Выходной: понедельник"],
    [6, "😌 Day off: Saturday", "😌 Выходной: суббота"],
    [7, "😌 Day off: Sunday", "😌 Выходной: воскресенье"],
  ])("names the day off: %i", (d, english, russian) => {
    expect(format(en, "settings-day-off-line", { d })).toBe(english);
    expect(format(ru, "settings-day-off-line", { d })).toBe(russian);
  });

  it("names two days off, and says when there is none", () => {
    expect(format(en, "settings-days-off-line", { d: 6, e: 7 })).toBe(
      "😌 Days off: Saturday, Sunday",
    );
    expect(format(ru, "settings-days-off-line", { d: 3, e: 7 })).toBe(
      "😌 Выходные: среда, воскресенье",
    );
    expect(format(en, "settings-day-off-none-line")).toBe("😌 No fixed day off");
    expect(format(ru, "settings-day-off-unset-line")).toBe("😌 Выходной: не выбран");
  });

  it.each([
    [1, "at most 1 message a day", "не больше 1 сообщения в день"],
    [3, "at most 3 messages a day", "не больше 3 сообщений в день"],
    [5, "at most 5 messages a day", "не больше 5 сообщений в день"],
  ])("sums up quiet hours with a limit of %i", (n, english, russian) => {
    const hours = { start: "22:00", end: "07:00", n };
    expect(format(en, "settings-quiet-line", hours)).toBe(
      `🔕 Quiet hours 22:00–07:00 · ${english}`,
    );
    expect(format(ru, "settings-quiet-line", hours)).toBe(`🔕 Тихие часы 22:00–07:00 · ${russian}`);
    expect(format(en, "settings-quiet-off-line", { n })).toBe(`🔕 No quiet hours · ${english}`);
    expect(format(ru, "settings-quiet-off-line", { n })).toBe(`🔕 Без тихих часов · ${russian}`);
  });

  it("names the place of the Reminders page's times once", () => {
    expect(format(en, "settings-times-place", { zone: "Almaty" })).toBe("🕐 Times: Almaty");
    expect(format(ru, "settings-times-place", { zone: "Алматы" })).toBe("🕐 Время: Алматы");
  });

  it("says in two short sentences what a day off does; when it applies only once one is set", () => {
    expect(format(en, "settings-day-off-hint", { first: "yes" })).toBe(
      "Pick one or two. They show as rest and get no practice reminders.",
    );
    expect(format(en, "settings-day-off-hint", { first: "no" })).toBe(
      "Pick one or two. They show as rest and get no practice reminders. A change applies from today.",
    );
    expect(format(ru, "settings-day-off-hint", { first: "yes" })).toBe(
      "Выбери один или два. Они отмечаются как отдых, и напоминания о практике в эти дни не приходят.",
    );
    expect(format(ru, "settings-day-off-hint", { first: "no" })).toBe(
      "Выбери один или два. Они отмечаются как отдых, и напоминания о практике в эти дни не приходят. Изменение действует с сегодняшнего дня.",
    );
  });

  it("heads the moon reminders with their own words", () => {
    expect(format(en, "remind-moon-title")).toBe("🌙 Moon reminders");
    expect(format(ru, "remind-moon-title")).toBe("🌙 Лунные напоминания");
  });

  it("reads as written", () => {
    expect(format(en, "settings-log-title")).toBe("Your log");
    expect(format(ru, "settings-log-title")).toBe("Твой журнал");
    expect(format(en, "settings-privacy-open")).toBe("🔒 What others see");
    expect(format(ru, "settings-privacy-open")).toBe("🔒 Что видят другие");
    expect(format(en, "settings-more-button")).toBe("More…");
    expect(format(ru, "settings-more-title")).toBe("⚙️ Ещё настройки");
  });

  it.each(LOCALES)("%s: the city nudge and the labels it made needless are gone", (locale) => {
    const ids = new Set([...messageIds(locale), ...Object.keys(shape(SETTINGS[locale]))]);
    for (const gone of [
      "settings-city-nudge",
      "settings-city-not-now",
      "remind-time-label", // Reminders names the place once (`settings-times-place`)
      "moon-city", // the moon calendar's select is labelled with `moon-title`
    ]) {
      expect(ids.has(gone)).toBe(false);
    }
    // The guides quote these (spec §7).
    for (const kept of ["settings-open", "settings-quiet", "guide-open", "feed-open"]) {
      expect(ids.has(kept)).toBe(true);
    }
  });
});
