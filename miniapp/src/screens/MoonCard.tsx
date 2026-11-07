import { Localized, useLocalization } from "@fluent/react";

import { useMoonCities, useMoonDays, type City, type MoonDays } from "../api/client";
import type { Locale } from "../i18n/negotiate";

const UPCOMING = 3;

const DAY_MS = 86_400_000;
const daysBetween = (from: string, to: string) =>
  Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);

export const cityName = (city: City | undefined, slug: string, locale: Locale) =>
  city ? (locale === "ru" ? city.name_ru : city.name_en) : slug;

/** Where the city comes from (MD-02): the main teacher, and for a teacher what students get. */
export function MoonSource({
  location,
  city,
  fallback,
}: {
  location: MoonDays["location"];
  city: string;
  /** The default city's name (first in `/moon/cities`): what students get without a choice. */
  fallback: string;
}) {
  const { l10n } = useLocalization();
  const name = location.teacher?.name ?? l10n.getString("link-no-name");
  return (
    <>
      {location.shala && location.source === "shala" && (
        <Localized id="moon-source-shala" vars={{ shala: location.shala.name }}>
          <p className="hint small" />
        </Localized>
      )}
      {location.teacher && location.source === "teacher" && (
        <Localized id="moon-source-teacher" vars={{ name }}>
          <p className="hint small" />
        </Localized>
      )}
      {location.teacher && location.source === "default" && location.follow_chosen && (
        <Localized id="moon-source-teacher-none" vars={{ name, city }}>
          <p className="hint small" />
        </Localized>
      )}
      {location.shared && (
        <Localized
          id="moon-teacher-shared"
          vars={{
            // "like yours" is untrue for one who follows their own teacher.
            chosen: location.shared.chosen ? "yes" : location.follow_chosen ? "follow" : "no",
            city: location.shared.chosen ? city : fallback,
          }}
        >
          <p className="hint small" />
        </Localized>
      )}
    </>
  );
}

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
    <section className="card" data-tour="moon" aria-labelledby="moon-title">
      <Localized id="moon-title" vars={{ city }}>
        <h2 id="moon-title" />
      </Localized>
      <MoonSource
        location={moon.location}
        city={city}
        fallback={cityName(cities?.[0], "mysuru", locale)}
      />
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
