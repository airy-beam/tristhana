// UI-05: fills the demo database through the product's own doors (REST API and bot webhook),
// so encrypted fields are sealed and every rule runs as it does for a real person.
import { CAST, CITY, SHALA, dayBefore, demoDay, todayIn } from "./cast.mjs";

const DAYS_BACK = 90;
const SATURDAY = 6; // ISO weekday

/**
 * @param {ReturnType<typeof import("./client.mjs").createClient>} client
 * @param {"en" | "ru"} locale
 * @param {{ today?: string, log?: (line: string) => void }} [options]
 */
export async function seedCast(client, locale, options = {}) {
  const { student, teacher } = CAST[locale];
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

  // The teacher runs a small shala: Mysore five mornings a week and a Led class on Friday.
  const shala = /** @type {{ id: string }} */ (
    await client.call(teacher, "POST", "/shalas", { name: SHALA[locale], city: CITY.slug })
  );
  const starts_on = dayBefore(today, 30);
  for (const lesson of [
    { type: "mysore", start: "06:00", minutes: 150, weekdays: [7, 1, 2, 3, 4] },
    { type: "led", start: "06:30", minutes: 90, weekdays: [5] },
  ]) {
    await client.call(teacher, "POST", `/shalas/${shala.id}/classes`, { ...lesson, starts_on });
  }
  const join = /** @type {{ url: string }} */ (
    await client.call(teacher, "POST", `/shalas/${shala.id}/join-link`, {})
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
}
