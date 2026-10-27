import enApp from "../locales/en/app.ftl?raw";
import ruApp from "../locales/ru/app.ftl?raw";
import { LOCALES } from "./negotiate";
import { bundleFor, definedIdCount, format, messageIds, messageVariables } from "./bundles";

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
  "checkin-title",
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
  it.each(LOCALES)("%s: has every PR-06 message", (locale) => {
    const ids = messageIds(locale);
    expect(PR06.filter((id) => !ids.has(id))).toEqual([]);
  });

  it("reads as written", () => {
    expect(format(bundleFor("en"), "checkin-title")).toBe("How do you feel?");
    expect(format(bundleFor("ru"), "checkin-title")).toBe("Самочувствие");
    expect(format(bundleFor("en"), "checkin-edit")).toBe("✨ Check-in");
    expect(format(bundleFor("ru"), "checkin-edit")).toBe("✨ Самочувствие");
    expect(format(bundleFor("en"), "checkin-clear")).toBe("Remove check-in");
    expect(format(bundleFor("ru"), "checkin-clear")).toBe("Убрать самочувствие");
    expect(format(bundleFor("en"), "settings-checkin")).toBe("Offer a check-in after practice");
    expect(format(bundleFor("ru"), "settings-checkin")).toBe(
      "Предлагать отметить самочувствие после практики",
    );
    expect(format(bundleFor("en"), "settings-checkin-hint")).toBe(
      "Mood, energy and effort right after logging today's practice. You can always add one from the day.",
    );
    expect(format(bundleFor("ru"), "settings-checkin-hint")).toBe(
      "Настроение, энергия и усилие сразу после отметки практики. Добавить можно и позже, в любой день практики.",
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
    ["en", enApp],
    ["ru", ruApp],
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
