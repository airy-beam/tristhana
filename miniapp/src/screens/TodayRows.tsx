import { useLocalization } from "@fluent/react";
import { Suspense } from "react";

import { useMoonCities, useMoonDays, useMyShalas } from "../api/client";
import type { Locale } from "../i18n/negotiate";
import { ChunkGuard } from "../shell/ChunkGuard";
import { lazyRetry } from "../shell/lazyRetry";
import { haptics } from "../telegram";
import { cityName } from "./cityName";
import { daysBetween, moonDate, moonShareable } from "./moonText";
import { Row } from "./Row";
import { ShareButton } from "./share/ShareButton";

// Only people in a shala load the row and ask for a schedule.
const ClassToday = lazyRetry(() => import("./ClassToday"));

/** Today's class as one list row on Today (UI-06), only for people in a shala. A tap opens My
 * schedule. If its chunk fails to load there is just no row: Today stays as it is. */
export function ClassRow({ locale, onOpen }: { locale: Locale; onOpen: () => void }) {
  if (!useMyShalas().data?.length) return null;
  return (
    <ChunkGuard>
      <Suspense fallback={null}>
        <ClassToday locale={locale} onOpen={onOpen} />
      </Suspense>
    </ChunkGuard>
  );
}

/** The next moon day of the followed city, as one list row on Today (UI-06): "Next moon day",
 * then the phase and the date ("today" and "tomorrow" in a word). A tap opens the whole card:
 * three days with their count, where the city comes from, the calculation note. With no day
 * in the window the row is the card's title, so the screen stays reachable. From 3 days before
 * the moon day through the day itself a "Share" button stands beside the row (ST-10). */
export function MoonRow({ locale, onOpen }: { locale: Locale; onOpen: () => void }) {
  const { l10n } = useLocalization();
  const moon = useMoonDays().data;
  const cities = useMoonCities().data;
  if (!moon) return null;
  const next = moon.days[0];
  const slug = moon.location.slug;
  const open = () => {
    haptics.selection();
    onOpen();
  };
  if (!next) {
    const city = cityName(
      cities?.find((c) => c.slug === slug),
      slug,
      locale,
    );
    return <Row label={plain(l10n.getString("moon-title", { city }))} onClick={open} />;
  }
  const away = daysBetween(moon.today, next.date);
  const fact = plain(
    l10n.getString("today-moon-fact", {
      phase: next.phase,
      when: away <= 1 ? l10n.getString("moon-in-days", { n: away }) : moonDate(locale)(next.date),
    }),
  );
  const row = (
    <Row label={l10n.getString("today-moon", { phase: next.phase })} sub={fact} onClick={open} />
  );
  if (!moonShareable(moon.today, next.date)) return row;
  // Two controls side by side, never one inside the other.
  return (
    <div className="lrow-share">
      {row}
      <ShareButton
        subject={{ kind: "moon", date: next.date }}
        label={plain(l10n.getString("share-entry", { entry: fact }))}
      />
    </div>
  );
}

// Fluent's bidi isolation marks around variables: noise in a composed line.
const plain = (text: string) => text.replace(/[\u2068\u2069]/g, "");
