import { Localized, useLocalization } from "@fluent/react";

import { useMoonCities, useMoonDays, type City } from "../api/client";
import type { Locale } from "../i18n/negotiate";

const UPCOMING = 3;

const DAY_MS = 86_400_000;
const daysBetween = (from: string, to: string) =>
  Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);

export const cityName = (city: City | undefined, slug: string, locale: Locale) =>
  city ? (locale === "ru" ? city.name_ru : city.name_en) : slug;

/** Upcoming moon days of the followed city (MD-03); the city and reminders are in Settings. */
export function MoonCard({ locale }: { locale: Locale }) {
  const { l10n } = useLocalization();
  const moon = useMoonDays().data;
  const cities = useMoonCities().data;
  if (!moon) return null;

  const slug = moon.location.slug;
  const city = cityName(
    cities?.find((c) => c.slug === slug),
    slug,
    locale,
  );
  const dateFormat = new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
  const upcoming = moon.days.slice(0, UPCOMING);

  return (
    <section className="card" aria-labelledby="moon-title">
      <Localized id="moon-title" vars={{ city }}>
        <h2 id="moon-title" />
      </Localized>
      {upcoming.length ? (
        <ul className="moon-days">
          {upcoming.map((d) => (
            <li key={d.date}>
              {l10n.getString("moon-day-line", {
                phase: l10n.getString("moon-phase-long", { phase: d.phase }),
                date: dateFormat.format(new Date(`${d.date}T00:00:00Z`)),
                in: l10n.getString("moon-in-days", { n: daysBetween(moon.today, d.date) }),
              })}
              {/* MD-04: the person's own city, only where its date differs (±1 day). */}
              {moon.home && d.home_date && (
                <Localized
                  id="moon-home-fyi"
                  vars={{
                    city: cityName(moon.home, moon.home.slug, locale),
                    date: dateFormat.format(new Date(`${d.home_date}T00:00:00Z`)),
                  }}
                >
                  <span className="hint small moon-home" />
                </Localized>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <Localized id="moon-none">
          <p className="hint" />
        </Localized>
      )}
      <Localized id="moon-calc-note" vars={{ city }}>
        <p className="hint small" />
      </Localized>
    </section>
  );
}
