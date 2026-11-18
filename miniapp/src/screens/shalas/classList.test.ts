import shared from "../../../../data/classes/class_list_cases.json";
import type { ClassType } from "../../api/client";
import { currentClasses, dayRuns, type ClassRule } from "./classText";

// UI-06 stage 6 (spec §3.1): which of a shala's classes are current and how their weekdays
// read. The cases are the backend's too (tests/domain/test_class_list.py), so the bot's list
// and the app's cannot drift.

interface Row {
  id: string;
  type: string;
  start: string;
  weekdays: number[];
  starts_on: string;
  ends_on: string | null;
}

describe("dayRuns", () => {
  test.each(shared.day_runs.map((c) => [c.name, c.weekdays, c.runs] as const))(
    "%s",
    (_name, weekdays, runs) => {
      expect(dayRuns(weekdays)).toEqual(runs);
    },
  );
});

describe("currentClasses", () => {
  const rule = (row: Row): ClassRule => ({ ...row, type: row.type as ClassType });

  test.each(
    shared.current_classes.map((c) => [c.name, c.today, c.classes as Row[], c.expected] as const),
  )("%s", (_name, today, rows, expected) => {
    expect(currentClasses(rows.map(rule), today).map((c) => c.id)).toEqual(expected);
  });

  test("the shared table is read", () => {
    expect(shared.day_runs.length).toBeGreaterThanOrEqual(5);
    expect(shared.current_classes.length).toBeGreaterThanOrEqual(5);
  });
});
