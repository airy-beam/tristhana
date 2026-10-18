import shared from "../../../data/i18n/locale_cases.json";
import { negotiateLocale } from "./negotiate";

// The same table drives backend/tests/domain/test_locale.py, so the rules can't drift.
const cases = shared.cases as [string | null, string][];

describe("negotiateLocale", () => {
  it.each(cases)("%s -> %s", (code, expected) => {
    expect(negotiateLocale(code)).toBe(expected);
  });

  it("treats undefined like a missing code", () => {
    expect(negotiateLocale(undefined)).toBe("en");
  });
});
