import type { ClassSeries, Shala } from "../../api/client";
import {
  appliesFrom,
  bodyOf,
  changed,
  defaultFrom,
  defaultTeacher,
  draftOf,
  endOf,
  hasStarted,
  minutesUntil,
  newDraft,
  nextDate,
  problemOf,
  retyped,
  runsBefore,
  runsOn,
  teacherChoices,
} from "./classForm";
import { fullDate, hmOf, spanName, weekdayShort } from "./scheduleText";

// UI-06 stage 4 (spec §4, §5; ADR-0048): the class form's rules, pure.

const ANNA = "00000000-0000-0000-0000-0000000000a1";
type Staff = Shala["staff"][number];
const staff = (id: string, roles: Staff["roles"], owner = false): Staff => ({
  id,
  name: id,
  owner,
  roles,
});
const shala = (over: Record<string, unknown> = {}) =>
  ({
    id: "s",
    city: { slug: "almaty", name: "Almaty" },
    zone: "Asia/Almaty",
    days_off: [6],
    staff: [staff(ANNA, ["teacher"], true)],
    me: { owner: true, roles: ["teacher"], student: false, schedule: true },
    ...over,
  }) as unknown as Shala;
const TODAY = "2026-11-16";
const saved = (over: Partial<ClassSeries> = {}): ClassSeries => ({
  id: "c",
  type: "led",
  title: null,
  online: false,
  city: null,
  teacher_id: ANNA,
  start: "07:00",
  minutes: 90,
  weekdays: [5],
  every: 1,
  starts_on: "2026-10-02",
  ends_on: null,
  rrule: "FREQ=WEEKLY;BYDAY=FR",
  ...over,
});

describe("a new class", () => {
  it("is Mysore 06:00–09:30 on every day but the shala's day off, from today", () => {
    const draft = newDraft(shala(), TODAY, ANNA);

    expect(endOf(draft)).toBe("09:30");
    expect(bodyOf(draft, shala())).toEqual({
      type: "mysore",
      title: null,
      online: false,
      city: null,
      teacher_id: ANNA,
      start: "06:00",
      minutes: 210,
      weekdays: [1, 2, 3, 4, 5, 7],
      every: 1,
      starts_on: TODAY,
      ends_on: null,
    });
    expect(problemOf(draft)).toBeNull();
  });

  it.each([
    ["led", 90],
    ["private", 60],
    ["conference", 60],
    ["pranayama", 60],
    ["chanting", 60],
    ["workshop", 120],
  ] as const)("%s starts with no day and %i minutes", (type, minutes) => {
    const draft = retyped(newDraft(shala(), TODAY, ""), type, shala());

    expect(draft.days).toEqual([]);
    expect(draft.minutes).toBe(minutes);
    expect(problemOf(draft)).toBe("days"); // weekly with no day does not save
  });

  it("keeps the length when the start changes", () => {
    const draft = { ...retyped(newDraft(shala(), TODAY, ""), "led", shala()), start: "18:30" };

    expect(endOf(draft)).toBe("20:00");
  });

  it("takes one date instead of weekdays", () => {
    const draft = { ...newDraft(shala(), TODAY, ""), once: true, date: "2026-12-05", end: "x" };

    expect(bodyOf(draft, shala())).toMatchObject({
      weekdays: [],
      every: 1,
      starts_on: "2026-12-05",
      ends_on: null,
    });
    expect(problemOf(draft)).toBeNull();
  });

  it("refuses a length that does not fit the day", () => {
    const draft = newDraft(shala(), TODAY, "");

    expect(problemOf({ ...draft, minutes: minutesUntil("09:00", "08:00") })).toBe("window");
    expect(problemOf({ ...draft, start: "22:00" })).toBe("window"); // past midnight
    expect(problemOf({ ...draft, minutes: 10 })).toBe("window");
    expect(minutesUntil("21:00", "00:00")).toBe(180); // midnight ends the day
  });

  it("names another city only for an online class", () => {
    const draft = { ...newDraft(shala(), TODAY, ""), city: "berlin" };

    expect(bodyOf(draft, shala()).city).toBeNull();
    expect(bodyOf({ ...draft, online: true }, shala()).city).toBe("berlin");
  });
});

describe("the teacher", () => {
  it("is me when I hold Teacher, else nobody", () => {
    expect(defaultTeacher(shala(), ANNA)).toBe(ANNA);
    const office = shala({ me: { owner: true, roles: ["office"], student: false } });
    expect(defaultTeacher(office, ANNA)).toBe("");
    expect(defaultTeacher(shala(), undefined)).toBe("");
  });

  it("may be any staff member: teachers and assistants first, an owner without roles too", () => {
    const all = [
      staff("owner", [], true),
      staff("desk", ["office"]),
      staff("teacher", ["teacher"]),
      staff("assistant", ["assistant"]),
    ];

    expect(teacherChoices(all).map((s) => s.id)).toEqual(["teacher", "assistant", "owner", "desk"]);
  });
});

describe("a change to a saved class", () => {
  it("fills the form from the class and finds nothing changed", () => {
    const draft = draftOf(saved(), shala());

    expect(draft).toMatchObject({ type: "led", start: "07:00", days: [5], once: false });
    expect(changed(bodyOf(draft, shala()), bodyOf(draft, shala()))).toEqual({});
  });

  it("sends only what differs, a cleared value as null", () => {
    const before = draftOf(saved({ title: "Full Primary" }), shala());
    const after = { ...before, start: "07:30", title: " ", days: [5, 7] };

    expect(changed(bodyOf(before, shala()), bodyOf(after, shala()))).toEqual({
      start: "07:30",
      title: null,
      weekdays: [5, 7],
    });
  });

  it("applies from the tapped date, never before the shala's today", () => {
    expect(appliesFrom("2026-11-20", TODAY)).toBe("2026-11-20");
    expect(appliesFrom("2026-11-13", TODAY)).toBe(TODAY); // a date of last week
  });

  it("has started only as a weekly class with a date before today", () => {
    expect(hasStarted(saved(), TODAY)).toBe(true);
    expect(hasStarted(saved({ starts_on: TODAY }), TODAY)).toBe(false);
    expect(hasStarted(saved({ starts_on: "2026-12-01" }), TODAY)).toBe(false);
    expect(hasStarted(saved({ weekdays: [], starts_on: "2026-11-01" }), TODAY)).toBe(false);
  });
});

describe("the form's texts", () => {
  it("names a weekday chip shortly, in the person's language", () => {
    expect([1, 6, 7].map((d) => weekdayShort(d, "en"))).toEqual(["Mon", "Sat", "Sun"]);
    expect([1, 6, 7].map((d) => weekdayShort(d, "ru"))).toEqual(["пн", "сб", "вс"]);
  });

  it("names a week in one short line, also across a month and a year", () => {
    const span = (a: string, b: string, locale: "en" | "ru") =>
      spanName(a, b, locale).replace(/\s/g, " ");
    expect(span("2026-11-16", "2026-11-22", "en")).toBe("Nov 16 – 22");
    expect(span("2026-11-16", "2026-11-22", "ru")).toBe("16–22 нояб.");
    expect(span("2026-11-30", "2026-12-06", "ru")).toBe("30 нояб. – 6 дек.");
    expect(span("2026-12-28", "2027-01-03", "en")).toBe("Dec 28 – Jan 3"); // no years
  });

  it("names a date with its year where the year matters", () => {
    expect(fullDate("2026-01-05", "en")).toBe("Jan 5, 2026");
    expect(fullDate("2026-01-05", "ru")).toBe("5 янв. 2026 г.");
  });

  it("shows an end as a time of day, also one before the start", () => {
    expect(hmOf(570)).toBe("09:30");
    expect(hmOf(1440)).toBe("00:00");
    expect(hmOf(-60)).toBe("23:00");
  });
});

// Review fixes: the last date against the first (or the apply) date; the class's own dates,
// and the date a change is proposed from when today's class has already begun.
describe("the last date and the class's own dates", () => {
  it("stops a last date before the first one, or before the apply date", () => {
    const draft = { ...newDraft(shala(), TODAY, ANNA), from: "2026-11-20", end: "2026-11-19" };

    expect(problemOf(draft)).toBe("end");
    expect(problemOf({ ...draft, end: "2026-11-20" })).toBeNull(); // the same day is a class
    expect(problemOf({ ...draft, end: "" })).toBeNull();
    // A class that has run: its first date is long past; the apply date is what counts.
    const running = { ...draft, from: "2026-10-02", end: "2026-11-30" };
    expect(problemOf(running, "2026-11-23")).toBeNull();
    expect(problemOf(running, "2026-12-01")).toBe("end");
    expect(problemOf({ ...draft, once: true })).toBeNull(); // one date has no last date
  });

  it("knows the saved rule's dates, as the server counts them", () => {
    const fridays = saved(); // Fridays from Fri 2 Oct
    expect(runsOn(fridays, "2026-11-20")).toBe(true);
    expect(runsOn(fridays, "2026-11-19")).toBe(false);
    expect(runsOn(fridays, "2026-09-25")).toBe(false); // before its first date
    expect(runsOn(saved({ ends_on: "2026-11-13" }), "2026-11-20")).toBe(false);
    // Every 2 weeks: weeks count from the first date's own week (2 Oct, 16 Oct, …, 13 Nov).
    const fortnightly = saved({ every: 2 });
    expect(runsOn(fortnightly, "2026-11-13")).toBe(true);
    expect(runsOn(fortnightly, "2026-11-20")).toBe(false);
    expect(runsOn(saved({ weekdays: [], starts_on: "2026-11-20" }), "2026-11-20")).toBe(true);

    expect(runsBefore(fridays, "2026-10-02")).toBe(false); // its first date
    expect(runsBefore(fridays, "2026-10-09")).toBe(true);
    // First date set to a Monday, classes on Fridays: nothing before the first Friday.
    expect(runsBefore(saved({ starts_on: "2026-09-28" }), "2026-10-02")).toBe(false);
    expect(runsBefore(saved({ weekdays: [], starts_on: "2026-11-20" }), "2026-11-20")).toBe(false);

    expect(nextDate(fridays, "2026-11-20")).toBe("2026-11-27");
    expect(nextDate(fortnightly, "2026-11-13")).toBe("2026-11-27");
    expect(nextDate(saved({ ends_on: "2026-11-20" }), "2026-11-20")).toBeNull();
  });

  it("proposes the class's next date once the tapped date's class has begun", () => {
    const daily = saved({ weekdays: [1, 2, 3, 4, 5, 7] }); // no Saturday
    expect(defaultFrom(daily, TODAY, TODAY, false)).toBe(TODAY);
    expect(defaultFrom(daily, TODAY, TODAY, true)).toBe("2026-11-17");
    expect(defaultFrom(daily, "2026-11-20", "2026-11-20", true)).toBe("2026-11-22"); // Fri → Sun
    expect(defaultFrom(daily, "2026-11-13", TODAY, true)).toBe("2026-11-17"); // last week's date
    // Today is not one of its days: nothing has begun today.
    expect(defaultFrom(saved(), TODAY, TODAY, true)).toBe(TODAY);
    // Its last date is today: there is no next one to move to.
    expect(defaultFrom(saved({ ...daily, ends_on: TODAY }), TODAY, TODAY, true)).toBe(TODAY);
  });
});
