import { bundleFor, format, messageIds } from "./bundles";
import { LOCALES } from "./negotiate";

// PR-08 Phase 3 (spec §8): the copy the Mini App needs for teacher marks, in both languages.
// The bot's side, the banned words and the consent line are pinned in
// backend/tests/infrastructure/test_i18n_teacher_marks.py.

const KEYS = [
  "students-give",
  "students-give-option",
  "students-give-range",
  "students-give-ask",
  "students-give-ask-range",
  "students-give-ask-across",
  "students-give-yes",
  "students-given",
  "students-given-range",
  "students-give-stale",
  "students-give-unset",
  "progression-marked-by",
  "progression-event-by",
  "progression-by-teacher",
  "progression-mark-moved-on",
];

const plain = (text: string) => text.replace(/[⁨⁩]/g, "");

describe("teacher-mark copy", () => {
  it.each(LOCALES)("%s: has every message", (locale) => {
    const ids = messageIds(locale);
    expect(KEYS.filter((id) => !ids.has(id))).toEqual([]);
  });

  it("reads as accepted", () => {
    const en = bundleFor("en");
    const ru = bundleFor("ru");
    const range = { from: "Supta Vajrasana", asana: "Bharadvajasana" };
    expect(format(en, "students-give")).toBe("🎉 Mark new asana");
    expect(format(ru, "students-give")).toBe("🎉 Отметить новую асану");
    expect(plain(format(en, "students-give-range", range))).toBe("→ Bharadvajasana");
    expect(plain(format(en, "students-given", { asana: "Supta Vajrasana" }))).toBe(
      "✅ Marked: Supta Vajrasana.",
    );
    expect(plain(format(ru, "students-given-range", range))).toBe(
      "✅ Отмечено: Supta Vajrasana → Bharadvajasana.",
    );
    expect(plain(format(en, "students-give-unset", { name: "Anna" }))).toBe(
      "Anna hasn't set their practice yet.",
    );
    expect(plain(format(ru, "students-give-unset", { name: "Anna" }))).toBe(
      "Anna: практика пока не указана.",
    );
    expect(format(en, "students-give-stale")).toBe(
      "This card was out of date, so nothing was marked. Here it is now.",
    );
    expect(plain(format(en, "progression-event-by", { teacher: "Anna" }))).toBe("· Anna");
    expect(plain(format(en, "progression-marked-by", { teacher: "Anna" }))).toBe("Marked by Anna");
    expect(plain(format(ru, "progression-marked-by", { teacher: "Anna" }))).toBe("Отметка: Anna");
    expect(format(en, "progression-by-teacher")).toBe("a teacher");
    expect(format(ru, "progression-by-teacher")).toBe("учитель");
  });

  it("the confirm names the student twice and the series", () => {
    const vars = { name: "Anna", asana: "Supta Vajrasana", series: "Intermediate" };
    expect(plain(format(bundleFor("en"), "students-give-ask", vars))).toBe(
      "Anna: the next asana is Supta Vajrasana (Intermediate). Mark it as new? Anna gets a message from the bot and can undo it.",
    );
    expect(plain(format(bundleFor("ru"), "students-give-ask", { ...vars, series: "вторая" }))).toBe(
      "Anna: следующая асана — Supta Vajrasana (вторая серия). Отметить как новую? Anna получит сообщение от бота и сможет отменить отметку.",
    );
  });

  it("a range across a series boundary names both series", () => {
    const vars = {
      name: "Anna",
      from: "Setu Bandhasana",
      from_series: "Primary",
      asana: "Krounchasana",
      series: "Intermediate",
    };
    expect(plain(format(bundleFor("en"), "students-give-ask-across", vars))).toBe(
      "Anna: new asanas Setu Bandhasana (Primary) → Krounchasana (Intermediate). Mark them? Anna gets one message from the bot and can undo it.",
    );
    const ru = { ...vars, from_series: "первая", series: "вторая" };
    expect(plain(format(bundleFor("ru"), "students-give-ask-across", ru))).toBe(
      "Anna: новые асаны — Setu Bandhasana (первая серия) → Krounchasana (вторая серия). Отметить? Anna получит одно сообщение от бота и сможет отменить отметку.",
    );
  });

  it("the Settings line no longer says Later", () => {
    expect(format(bundleFor("en"), "settings-privacy-sharing")).not.toContain("Later");
    expect(format(bundleFor("ru"), "settings-privacy-sharing")).not.toContain("Позже");
    expect(format(bundleFor("en"), "settings-privacy-sharing")).toContain(
      "you get a message and can undo it",
    );
  });
});
