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

  it("formats the greeting with the user's name", () => {
    expect(format(bundleFor("ru"), "home-greeting", { name: "Аня" })).toContain("Намасте, Аня");
  });
});
