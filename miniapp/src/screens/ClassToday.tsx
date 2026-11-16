import { useLocalization } from "@fluent/react";
import { useState } from "react";

import { useMe, useMySchedule, type MyRow } from "../api/client";
import { addMessages } from "../i18n/lazyMessages";
import type { Locale } from "../i18n/negotiate";
import enClassRow from "../locales/en/class-row.ftl?raw";
import ruClassRow from "../locales/ru/class-row.ftl?raw";
import { haptics } from "../telegram";
import { placeFor } from "./settings/zones";
import { dateIn, plain, timeIn } from "./shalas/scheduleText";
import { offsetText, timeLabel, zoneLabel } from "./timeLabel";

addMessages({ en: enClassRow, ru: ruClassRow });

// Mysore, Led and 1:1 reuse the practice words; the rest have their own (as the class form).
const CONTEXT: Partial<Record<MyRow["type"], string>> = {
  mysore: "context-mysore",
  led: "context-led",
  private: "context-private",
};

/** Today's class row (UI-06), shown when a shala I'm in has a class today: the next one still
 * ahead, else the day's first. Times are in my zone (the place, no offset: ADR-0044), with the
 * class's own time when its clock differs. Lazy: mounted by `ClassRow` for shala members. */
export default function ClassToday({ locale, onOpen }: { locale: Locale; onOpen: () => void }) {
  const { l10n } = useLocalization();
  const me = useMe().data;
  const week = useMySchedule(null).data;
  const [now] = useState(() => Date.now()); // when Today was opened
  if (!week) return null;
  const mine = week.zone;
  const rows = week.occurrences.filter(
    (r) => !r.cancelled && dateIn(r.starts_at, mine) === week.today,
  );
  const row = rows.find((r) => Date.parse(r.starts_at) > now) ?? rows[0];
  if (!row) return null;

  const viewer = week.zone_known ? mine : null; // unknown: nothing is "my own" yet
  const start = timeIn(row.starts_at, mine);
  const type = l10n.getString(CONTEXT[row.type] ?? "class-type", { type: row.type });
  const parts = [
    l10n.getString("today-class", {
      time: timeLabel(start, mine, week.today, {
        place: placeFor(me?.home_city, viewer, locale),
        viewer,
      }),
      type: row.title ? `${type} ${row.title}` : type,
      shala: week.shalas.find((s) => s.id === row.shala_id)?.name ?? "",
    }),
  ];
  const there = timeIn(row.starts_at, row.zone);
  // The class's own wall clock, with the offset at that time (a change night too).
  if (offsetText(row.zone, row.on, there) !== offsetText(mine, week.today, start)) {
    const zone = zoneLabel(row.zone, row.on, { at: there, viewer });
    parts.push(l10n.getString("today-class-there", { time: there, zone }));
  }
  if (rows.length > 1) parts.push(l10n.getString("today-class-more", { n: rows.length - 1 }));
  return (
    <button
      type="button"
      className="row-button"
      onClick={() => {
        haptics.selection();
        onOpen();
      }}
    >
      {plain(parts.join(" "))}
    </button>
  );
}
