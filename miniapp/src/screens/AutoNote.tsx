import { Localized } from "@fluent/react";

import { useMoonCities, type AutoDay } from "../api/client";
import type { Locale } from "../i18n/negotiate";
import { cityName } from "./MoonCard";

/** Why an unlogged day shows as rest (PR-09, ADR-0022): a moon day of the followed city
 * or the weekly day off. Nothing is pressed: logging anything replaces it. */
export function AutoNote({
  auto,
  location,
  locale,
}: {
  auto: AutoDay;
  location: string;
  locale: Locale;
}) {
  const cities = useMoonCities().data;
  if (auto.kind === "day_off") {
    return (
      <Localized id="today-auto-day-off">
        <p className="hint" />
      </Localized>
    );
  }
  const city = cityName(
    cities?.find((c) => c.slug === location),
    location,
    locale,
  );
  return (
    <Localized id="today-auto-moon" vars={{ city, dayoff: auto.also_day_off ? "yes" : "no" }}>
      <p className="hint" />
    </Localized>
  );
}
