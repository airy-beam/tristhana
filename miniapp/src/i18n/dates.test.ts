import { monthTitle } from "./dates";

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
