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
