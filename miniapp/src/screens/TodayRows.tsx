import { useLocalization } from "@fluent/react";

import { useMoonCities, useMoonDays } from "../api/client";
import type { Locale } from "../i18n/negotiate";
import { haptics } from "../telegram";
import { cityName } from "./cityName";
import { moonDate, moonDayLine } from "./moonText";

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
