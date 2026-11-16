import { useLocalization } from "@fluent/react";
import { Suspense } from "react";

import { useMoonCities, useMoonDays, useMyShalas } from "../api/client";
import type { Locale } from "../i18n/negotiate";
import { ChunkGuard } from "../shell/ChunkGuard";
import { lazyRetry } from "../shell/lazyRetry";
import { haptics } from "../telegram";
import { cityName } from "./cityName";
import { moonDate, moonDayLine } from "./moonText";

// Only people in a shala load the row and ask for a schedule.
const ClassToday = lazyRetry(() => import("./ClassToday"));

/** Today's class as one row on Today (UI-06), only for people in a shala. A tap opens My
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

/** The next moon day of the followed city, as one row on Today (UI-06). A tap opens the whole
 * card: three days, where the city comes from, the calculation note. With no day in the
 * window the row is the card's title, so the screen stays reachable. */
export function MoonRow({ locale, onOpen }: { locale: Locale; onOpen: () => void }) {
  const { l10n } = useLocalization();
  const moon = useMoonDays().data;
  const cities = useMoonCities().data;
  if (!moon) return null;
  const next = moon.days[0];
  const slug = moon.location.slug;
  return (
    <button
      type="button"
      className="row-button"
      onClick={() => {
        haptics.selection();
        onOpen();
      }}
    >
      {next
        ? moonDayLine(l10n, next, moon.today, moonDate(locale))
        : l10n.getString("moon-title", {
            city: cityName(
              cities?.find((c) => c.slug === slug),
              slug,
              locale,
            ),
          })}
    </button>
  );
}
