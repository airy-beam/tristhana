// UI-05: fills the demo database through the product's own doors (REST API and bot webhook),
// so encrypted fields are sealed and every rule runs as it does for a real person.
import { CAST, CITY, NEWS, SHALA, dayBefore, demoDay, todayIn } from "./cast.mjs";

const DAYS_BACK = 90;
const SATURDAY = 6; // ISO weekday

/**
 * @param {ReturnType<typeof import("./client.mjs").createClient>} client
 * @param {"en" | "ru"} locale
 * @param {{ today?: string, now?: Date, log?: (line: string) => void }} [options]
 */
export async function seedCast(client, locale, options = {}) {
  const { student, teacher, assistant } = CAST[locale];
  const today = options.today ?? todayIn(CITY.zone);
  const log = options.log ?? (() => {});

  for (const person of [student, teacher]) {
    await client.call(person, "POST", "/me/device-timezone", { timezone: CITY.zone });
    await client.call(person, "PATCH", "/me", { home_city: CITY.slug });
  }
  await client.call(student, "PUT", "/me/day-off", { day_off: [SATURDAY] });

  const moon = /** @type {{ days: { date: string }[] }} */ (
    await client.call(
      student,
      "GET",
      `/me/moon-days?from=${dayBefore(today, DAYS_BACK)}&to=${today}`,
    )
  );
  const moonDays = new Set(moon.days.map((day) => day.date));
  if (moonDays.size === 0) throw new Error(`${locale}: no moon days in the last ${DAYS_BACK} days`);

  let logged = 0;
  for (let back = DAYS_BACK; back >= 0; back--) {
    const date = dayBefore(today, back);
    const day = demoDay(date, back, moonDays);
    await client.call(student, "PUT", `/me/days/${date}`, { status: day.status });
    if (day.practice) {
      await client.call(student, "PUT", `/me/days/${date}/practices/1`, day.practice);
    }
    logged++;
  }
  log(`${locale}: ${student.name} logged ${logged} days (${moonDays.size} moon days)`);

  // The teacher shares an invite link; the student opens it in the bot and confirms.
  const invite = /** @type {{ url: string }} */ (
    await client.call(teacher, "POST", "/me/invite", {})
  );
  const code = /[?&]start=([\w-]+)/.exec(invite.url)?.[1];
  if (!code) throw new Error(`no start code in the invite link ${invite.url}`);
  const consent = await client.say(student, `/start ${code}`);
  await client.tap(student, consent, "✅");
  const links = /** @type {{ teachers: unknown[] }} */ (
    await client.call(student, "GET", "/me/links")
  );
  if (links.teachers.length !== 1) throw new Error(`${locale}: the teacher link was not made`);
  log(`${locale}: ${student.name} is linked to ${teacher.name}`);

  // The student's practice ends with full Primary; "My asanas" starts from there.
  await client.call(student, "POST", "/me/progression/events", {
    kind: "set",
    series: "primary",
    last: "setu-bandhasana",
    expected_event_id: null,
  });

  // The teacher has chosen a moon city, so students without one follow it (MD-02).
  await client.call(teacher, "PUT", "/me/moon-location", { slug: CITY.slug });

  // The teacher runs a small shala: Mysore five mornings a week, a Led class on Friday and
  // Saturday off.
  const shala = /** @type {{ id: string }} */ (
    await client.call(teacher, "POST", "/shalas", {
      name: SHALA[locale],
      city: CITY.slug,
      roles: ["teacher"],
    })
  );
  const at = `/shalas/${shala.id}`;
  await client.call(teacher, "PATCH", at, { days_off: [SATURDAY] });
  const card = /** @type {{ staff: { id: string, owner: boolean }[] }} */ (
    await client.call(teacher, "GET", at)
  );
  const teacher_id = card.staff.find((person) => person.owner)?.id;
  const starts_on = dayBefore(today, 30);
  /** @type {{ id: string, weekdays: number[] }[]} */
  const classes = [];
  for (const lesson of [
    { type: "mysore", start: "06:00", minutes: 150, weekdays: [7, 1, 2, 3, 4] },
    { type: "led", start: "06:30", minutes: 90, weekdays: [5] },
  ]) {
    const made = /** @type {{ id: string }} */ (
      await client.call(teacher, "POST", `${at}/classes`, { ...lesson, starts_on, teacher_id })
    );
    classes.push({ id: made.id, weekdays: lesson.weekdays });
  }
  const join = /** @type {{ url: string }} */ (
    await client.call(teacher, "POST", `${at}/join-link`, {})
  );
  const joinCode = /[?&]start=([\w-]+)/.exec(join.url)?.[1];
  if (!joinCode) throw new Error(`no start code in the shala link ${join.url}`);
  await client.tap(student, await client.say(student, `/start ${joinCode}`), "✅");
  const shalas = /** @type {unknown[] | { shalas: unknown[] }} */ (
    await client.call(student, "GET", "/me/shalas")
  );
  const joined = Array.isArray(shalas) ? shalas.length : shalas.shalas.length;
  if (joined !== 1) throw new Error(`${locale}: the student did not join the shala`);
  log(`${locale}: ${student.name} joined ${SHALA[locale]}`);

  // An assistant joins the staff by a one-time link and covers one Mysore morning.
  const staffLink = /** @type {{ url: string }} */ (
    await client.call(teacher, "POST", `${at}/staff-invites`, { role: "assistant" })
  );
  const staffCode = /[?&]start=([\w-]+)/.exec(staffLink.url)?.[1];
  if (!staffCode) throw new Error(`no start code in the staff link ${staffLink.url}`);
  await client.tap(assistant, await client.say(assistant, `/start ${staffCode}`), "✅");
  const staff = /** @type {{ staff: { id: string, owner: boolean }[] }} */ (
    await client.call(teacher, "GET", at)
  ).staff;
  const helper = staff.find((person) => !person.owner && person.id !== teacher_id);
  if (staff.length < 2 || !helper) throw new Error(`${locale}: the assistant did not join`);
  const mysore = classes[0];
  let covered = "";
  for (let ahead = 2; ahead <= 9 && !covered; ahead++) {
    const date = dayBefore(today, -ahead);
    const weekday = new Date(`${date}T12:00:00Z`).getUTCDay() || 7;
    if (!mysore.weekdays.includes(weekday)) continue;
    try {
      await client.call(teacher, "PUT", `${at}/classes/${mysore.id}/occurrences/${date}`, {
        teacher_id: helper.id,
      });
      covered = date;
    } catch {
      // a moon day or another change on that date: try the next morning
    }
  }
  if (!covered) throw new Error(`${locale}: no Mysore morning to cover in the next 9 days`);

  // A short closure three weeks ahead, one pinned announcement, and the student's own mark on
  // the latest class they could have come to.
  await client.call(teacher, "POST", `${at}/closures`, {
    start: dayBefore(today, -19),
    end: dayBefore(today, -21),
  });
  await client.call(teacher, "POST", "/me/announcements", {
    to: "shala",
    shala_id: shala.id,
    text: NEWS[locale],
    pin_days: 7,
  });
  const week =
    /** @type {{ occurrences: { class_id: string, key: string, can_claim: boolean, starts_at: string }[] }} */ (
      await client.call(student, "GET", `/me/schedule?from=${dayBefore(today, 6)}&days=7`)
    );
  const now = options.now ?? new Date();
  const came = week.occurrences.filter((o) => o.can_claim && new Date(o.starts_at) < now).at(-1);
  if (came) await client.call(student, "PUT", `/me/attendance/${came.class_id}/${came.key}`, {});
  log(
    `${locale}: ${assistant.name} covers ${covered}; ${student.name} marked ${came?.key ?? "no class"}`,
  );
}
