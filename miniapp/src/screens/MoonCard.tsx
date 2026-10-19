import { Localized, useLocalization } from "@fluent/react";

import {
  useMoonCities,
  useMoonDays,
  useNotificationSettings,
  useSaveNotificationSettings,
  useSetMoonLocation,
  type City,
} from "../api/client";
import type { Locale } from "../i18n/negotiate";
import { haptics } from "../telegram";

const OFFSETS = [7, 3, 1] as const;
const UPCOMING = 3;

const DAY_MS = 86_400_000;
const daysBetween = (from: string, to: string) =>
  Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);

export const cityName = (city: City | undefined, slug: string, locale: Locale) =>
  city ? (locale === "ru" ? city.name_ru : city.name_en) : slug;

/** Upcoming moon days, the followed city, and reminder chips (MD-03). */
export function MoonCard({ locale, zone }: { locale: Locale; zone: string | null }) {
  const { l10n } = useLocalization();
  const moon = useMoonDays().data;
  const cities = useMoonCities().data;
  const settingsQuery = useNotificationSettings();
  const settings = settingsQuery.data;
  const setLocation = useSetMoonLocation();
  const save = useSaveNotificationSettings();
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

      {cities && (
        <label className="label">
          <Localized id="moon-city">
            <span />
          </Localized>
          <select
            value={slug}
            onChange={(e) => {
              haptics.impact("light");
              setLocation.mutate(e.target.value);
            }}
          >
            {cities.map((c) => (
              <option key={c.slug} value={c.slug}>
                {cityName(c, c.slug, locale)}
              </option>
            ))}
          </select>
        </label>
      )}

      <Localized id="moon-reminders-label">
        <p className="label" />
      </Localized>
      {settingsQuery.isError ? null : zone && settings ? (
        <div className="chips" role="group">
          {OFFSETS.map((k) => {
            const on = settings.moon.offsets.includes(k);
            return (
              <Localized key={k} id="moon-offset" vars={{ n: k }}>
                <button
                  type="button"
                  className="chip"
                  aria-pressed={on}
                  onClick={() => {
                    haptics.impact("light");
                    const offsets = on
                      ? settings.moon.offsets.filter((o) => o !== k)
                      : [...settings.moon.offsets, k];
                    save.mutate(
                      { ...settings, moon: { ...settings.moon, offsets } },
                      {
                        onError: () => {
                          haptics.notify("error");
                        },
                      },
                    );
                  }}
                />
              </Localized>
            );
          })}
        </div>
      ) : (
        <Localized id="moon-zone-needed-app">
          <p className="hint" />
        </Localized>
      )}
      {(save.isError || setLocation.isError || settingsQuery.isError) && (
        <Localized id="moon-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}
