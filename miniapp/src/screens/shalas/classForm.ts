import type { ClassSeries, ClassType, NewClass, Shala } from "../../api/client";
import { WEEKDAYS, hmOf, minutesOf } from "./scheduleText";

/** The class form's rules (UI-06 stage 4, ADR-0048), pure: what a new class starts with, what
 * goes to the server, which fields a person changed, and the date a change applies from. */

export const DAY_MINUTES = 24 * 60;
export const TITLE_MAX = 48;
/** The length chips; any other length goes through "Other" and an end time. */
export const LENGTHS: readonly number[] = [60, 75, 90, 120];

// Mysore is a window (06:00–09:30); the others a length (ashtanga-expert, 2026-11-16).
const MINUTES: Record<ClassType, number> = {
  mysore: 210,
  led: 90,
  private: 60,
  conference: 60,
  pranayama: 60,
  chanting: 60,
  workshop: 120,
};
const START = "06:00";

type Staff = Shala["staff"][number];

export interface Draft {
  type: ClassType;
  title: string;
  /** A staff member's id; "" for none. */
  teacher: string;
  start: string;
  /** The length; an end before the start makes it negative, and that does not save. */
  minutes: number;
  /** One date instead of weekdays. */
  once: boolean;
  days: number[];
  /** The one date. */
  date: string;
  every: number;
  /** The first date of a weekly class. */
  from: string;
  /** The last date; "" for none. */
  end: string;
  online: boolean;
  /** The city whose clock the class runs on (another one only when online, Q124). */
  city: string;
}

/** Mysore starts with every day but the shala's day off; other types with none (expert). */
const presetDays = (type: ClassType, shala: Shala): number[] =>
  type === "mysore" ? WEEKDAYS.filter((d) => !(shala.days_off ?? []).includes(d)) : [];

/** Me when I hold Teacher in this shala, else nobody. */
export function defaultTeacher(shala: Shala, myId: string | undefined): string {
  return myId && shala.me.roles.includes("teacher") && shala.staff.some((s) => s.id === myId)
    ? myId
    : "";
}

/** Every staff member may be named: teachers and assistants first, then the rest. */
export function teacherChoices(staff: readonly Staff[]): Staff[] {
  const teaches = (s: Staff) => s.roles.includes("teacher") || s.roles.includes("assistant");
  return [...staff.filter(teaches), ...staff.filter((s) => !teaches(s))];
}

export function newDraft(shala: Shala, today: string, teacher: string): Draft {
  return {
    type: "mysore",
    title: "",
    teacher,
    start: START,
    minutes: MINUTES.mysore,
    once: false,
    days: presetDays("mysore", shala),
    date: today,
    every: 1,
    from: today,
    end: "",
    online: false,
    city: shala.city.slug,
  };
}

/** A new class of another type: its usual days and length. */
export function retyped(draft: Draft, type: ClassType, shala: Shala): Draft {
  return { ...draft, type, days: presetDays(type, shala), minutes: MINUTES[type] };
}

/** The form filled from a saved class. */
export function draftOf(c: ClassSeries, shala: Shala): Draft {
  return {
    type: c.type,
    title: c.title ?? "",
    teacher: c.teacher_id ?? "",
    start: c.start.slice(0, 5),
    minutes: c.minutes,
    once: c.weekdays.length === 0,
    days: [...c.weekdays],
    date: c.starts_on,
    every: c.every,
    from: c.starts_on,
    end: c.ends_on ?? "",
    online: c.online,
    city: c.city ?? shala.city.slug,
  };
}

/** The end as the form shows it: "09:30" for 06:00 and 210 minutes. */
export const endOf = (draft: Draft) => hmOf(minutesOf(draft.start) + draft.minutes);

/** The length when the end is set to `end`; midnight is the end of the day. */
export const minutesUntil = (start: string, end: string) =>
  (minutesOf(end) || DAY_MINUTES) - minutesOf(start);

/** What stops the form: a weekly class with no day, or a length that does not fit the day. */
export function problemOf(draft: Draft): "days" | "window" | null {
  if (!draft.once && draft.days.length === 0) return "days";
  const { minutes } = draft;
  if (!/^\d\d:\d\d/.test(draft.start)) return "window"; // the time field was cleared
  if (minutes < 15 || minutes > 480 || minutesOf(draft.start) + minutes > DAY_MINUTES)
    return "window";
  return null;
}

export function bodyOf(draft: Draft, shala: Shala): NewClass {
  const weekly = !draft.once;
  return {
    type: draft.type,
    title: draft.title.trim() || null,
    online: draft.online,
    city: draft.online && draft.city !== shala.city.slug ? draft.city : null,
    teacher_id: draft.teacher || null,
    start: hmOf(minutesOf(draft.start)),
    minutes: draft.minutes,
    weekdays: weekly ? [...draft.days].sort((a, b) => a - b) : [],
    every: weekly ? draft.every : 1,
    starts_on: weekly ? draft.from : draft.date,
    ends_on: weekly && draft.end ? draft.end : null,
  };
}

/** Only the fields that differ: what another person changed meanwhile stays (ADR-0048). */
export function changed(before: NewClass, after: NewClass): Partial<NewClass> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(after))
    if (JSON.stringify(value) !== JSON.stringify(before[key as keyof NewClass])) out[key] = value;
  return out;
}

/** A weekly class that has run: a change to it applies from a date, and earlier dates stay. */
export const hasStarted = (c: ClassSeries, today: string) =>
  c.weekdays.length > 0 && c.starts_on < today;

/** The date a change applies from: the one that was tapped, never before the shala's today. */
export const appliesFrom = (tapped: string, today: string) => (tapped > today ? tapped : today);
