# ADR-0035: My schedule: one read across my shalas, shown in the viewer's zone with the class zone as a second label; followed teachers only through shared shalas
- Status: accepted (owner, 2026-11-08)
- Date: 2026-11-08

## Context
SC-03 asks that students see their teachers' and shalas' schedules in their own zone, with labels (`06 Time Zones`: every time carries `07:00 Almaty (UTC+5)`; a "⚠ time shift" chip around DST). SC-02 (ADR-0034) shows each shala's schedule in the **shala's** zone with a "your time" note for online classes, and a staff-only "My classes" (`staff_windows`, `/me/classes`, `/classes`) in each shala's zone. A person may belong to up to 15 shalas (SC-01 caps: 10 staff, 5 student). Teacher links (ADR-0030) are personal; a linked teacher may be staff at shalas the student has not joined, and shala schedules are member-only (Q106, SC-02). Spec: `docs/specs/SC-03-my-schedule.md`.

## Decision
- **One read, one use case.** `ScheduleRepository.member_windows(me, start, end, staff_only)` returns SC-02's `ScheduleWindow` for every shala where I am a member, plus my linked teacher ids, in one statement; `GetMySchedule` expands each with the existing `expand` and serves the bot (`/schedule`, `/classes` = the *Mine* filter) and `GET /api/v1/me/schedule`. It replaces `staff_windows` and `GetMyClasses`; `GET /me/classes` stays one release as a deprecated adapter over the same use case.
- **Viewer's zone first.** Days are the viewer's local dates (rows bucketed by the instant in the viewer's zone; read margin ±2 days for extreme offset pairs). The header carries the viewer's label (home-city name, ADR-0029); any row whose class offset differs at that instant also shows the class's own wall clock with its zone label. An unknown viewer zone falls back, labelled, to the first shala's zone.
- **Shift line from a pure function.** `domain.classes.shifts(zones, viewer, start, end)` samples *class offset − viewer offset* at the viewer's local noon from the day before the window to its end and reports each change; both surfaces render it. Row times are always exact.
- **My own moon day in the same read (owner, ashtanga-expert review).** The viewer's effective moon city comes from the pure `domain.accounts.moon_follow_of` on the already loaded account (one-hop teacher/shala inheritance, ADR-0032); `member_windows` takes it as `moon_city` and returns its `moon_day` dates as one more scalar subquery. The day row shows 🌙 for those dates; read-only, no prompt. The port reads only `moon_day`, so `application.classes` still imports no log, rest or women's-health port and needs no import-linter exception. Shala moon cancellations stay per shala (🌙-led rows; ❌ for closures and manual cancels; a held row on its shala's moon day gets a quiet 🌙).
- **Visibility = membership.** Each window applies its own membership policy (1:1 to that shala's staff only). A followed teacher's classes appear only from shalas I've joined, marked from my own links; no shala of a teacher's is revealed by the link.

## Consequences
- No migration, no new dependency, no new policy; 2 statements per tap (account load + `member_windows` with teacher ids and my moon dates); expansion stays sub-10 ms for the worst case (measured before done).
- "My classes" changes from shala time to my time; the second label keeps the shala's time visible.
- SC-06 (personal ICS) and SC-05 (attendance from a row) reuse `GetMySchedule` and the occurrence key.
- Students of a teacher who works at a shala they haven't joined see nothing of it; opening schedules beyond members needs a later, explicit visibility setting and its own ADR.

## Alternatives considered
- **Class zone first, "your time" second (as SC-02):** keeps the studio clock primary, but the requirement says "in their own zone" and mixed zones in one list would need a label on every row.
- **N per-shala reads (reuse `window` in a loop):** simpler SQL, but up to 15 round trips per tap, against the one-round-trip rule.
- **Show a followed teacher's classes at any shala:** what students may expect from "my teachers' schedules", but it exposes member-only schedules and the teacher's shala list to anyone they link with, without the shala's consent.
- **Keep "My classes" as a separate read:** a parallel expansion path and a second Home row for staff; the *Mine* filter does the same over the same read.
- **My moon day through `GetMoonView` / `MoonCalendarRepository`:** reuses the MD use case, but adds a third statement per tap and pulls notification settings it doesn't need.
- **Client-only DST chip:** possible with `Intl`, but the bot needs it too; one domain function keeps both surfaces identical.
