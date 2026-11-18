import { monthTitle, shortDate } from "./dates";

// Node's, at test time only (the app's types have no `process`).
declare const process: { env: Record<string, string | undefined> };

// UI-06 stage 5 (Q352a): one month title on every screen. «Ноябрь 2026»: nominative, capitalised,
// no «г.»; the month is read from its numbers, so no phone zone moves it into the month before.
describe("monthTitle", () => {
  const zone = process.env.TZ;
  afterEach(() => {
    if (zone === undefined) delete process.env.TZ;
    else process.env.TZ = zone;
  });

  test.each(["UTC", "Pacific/Pago_Pago", "Pacific/Kiritimati"])("in %s", (tz) => {
    process.env.TZ = tz;
    expect(monthTitle(2026, 10, "en")).toBe("November 2026");
    expect(monthTitle(2026, 10, "ru")).toBe("Ноябрь 2026");
    expect(monthTitle(2027, 0, "ru")).toBe("Январь 2027");
    expect(monthTitle(2026, 4, "ru")).toBe("Май 2026");
    expect(monthTitle(2026, 11, "en")).toBe("December 2026");
  });

  test("the month alone, under a year's heading", () => {
    expect(monthTitle(2026, 10, "en", { year: false })).toBe("November");
    expect(monthTitle(2026, 10, "ru", { year: false })).toBe("Ноябрь");
    expect(monthTitle(2026, 2, "ru", { year: false })).toBe("Март");
  });

  test("inside running text, in the language's own case", () => {
    expect(monthTitle(2026, 10, "ru", { capital: false })).toBe("ноябрь 2026");
    expect(monthTitle(2026, 10, "en", { capital: false })).toBe("November 2026");
    expect(monthTitle(2026, 10, "ru", { year: false, capital: false })).toBe("ноябрь");
  });

  test("never the «г.» Intl adds in Russian", () => {
    for (let m = 0; m < 12; m++) expect(monthTitle(2026, m, "ru")).not.toMatch(/г\.|\bг\b/);
  });
});

// A short date with its year (My asanas' history, badges, the class form's dates, an old "Same as
// last time"): «18 нояб. 2026», never the «г.» Intl adds in Russian.
describe("shortDate", () => {
  const zone = process.env.TZ;
  afterEach(() => {
    if (zone === undefined) delete process.env.TZ;
    else process.env.TZ = zone;
  });

  test.each(["UTC", "Pacific/Pago_Pago", "Pacific/Kiritimati"])("in %s", (tz) => {
    process.env.TZ = tz;
    expect(shortDate("2026-11-18", "en")).toBe("Nov 18, 2026");
    expect(shortDate("2026-11-18", "ru")).toBe("18 нояб. 2026");
    expect(shortDate("2027-01-01", "ru")).toBe("1 янв. 2027");
  });

  test("with the weekday, and without the year", () => {
    expect(shortDate("2025-10-01", "en", { weekday: true })).toBe("Wed, Oct 1, 2025");
    expect(shortDate("2025-10-01", "ru", { weekday: true })).toBe("ср, 1 окт. 2025");
    expect(shortDate("2026-10-01", "en", { weekday: true, year: false })).toBe("Thu, Oct 1");
    expect(shortDate("2026-10-01", "ru", { weekday: true, year: false })).toBe("чт, 1 окт.");
  });

  test("never the «г.» Intl adds in Russian", () => {
    for (let m = 1; m <= 12; m++) {
      const day = `2026-${String(m).padStart(2, "0")}-15`;
      expect(shortDate(day, "ru")).toMatch(/ 2026$/); // «авг.» keeps its own «г.»
      expect(shortDate(day, "ru", { weekday: true })).toMatch(/ 2026$/);
    }
  });
});
