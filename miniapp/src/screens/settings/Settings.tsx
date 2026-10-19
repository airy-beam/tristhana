import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import {
  useMoonCities,
  useMoonDays,
  useNotificationSettings,
  usePatchMe,
  usePatchNotificationSettings,
  useSetMoonLocation,
  type Me,
  type NotificationSettings,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { backButtonAvailable, haptics, useBackButton } from "../../telegram";
import { cityName } from "../MoonCard";
import { inQuiet, PracticeReminderCard } from "../PracticeReminderCard";
import { loadShowLadies, saveShowLadies } from "../stats/cells";
import { deviceZone, labelOf, zoneCities } from "./zones";

const OFFSETS = [7, 3, 1] as const;
const MOON_TIMES = ["07:00", "12:00", "19:00", "21:00"] as const;
const CAPS = [1, 2, 3, 5] as const;
const HOURS = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, "0")}:00`);

interface Props {
  me: Me;
  onBack: () => void;
}

/** Everything in one place (ID-06): profile, time zone, moon days, reminders, privacy.
 * Loaded lazily, so Home stays light. */
export default function Settings({ me, onBack }: Props) {
  useBackButton(onBack);
  return (
    <main className="screen settings">
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      <Localized id="settings-title">
        <h1 />
      </Localized>
      <Profile me={me} />
      <Zone me={me} />
      <Moon locale={me.locale} zone={me.timezone} />
      <PracticeReminderCard zone={me.timezone} />
      <Quiet zone={me.timezone} />
      <Privacy />
    </main>
  );
}

function Profile({ me }: { me: Me }) {
  const patch = usePatchMe();
  const custom = me.name_from_telegram ? "" : (me.display_name ?? "");
  const [name, setName] = useState(custom);
  const save = () => {
    if (name.trim() === custom.trim()) return;
    patch.mutate({ display_name: name.trim() || null });
  };
  const current = me.locale_from_telegram ? null : me.locale;
  const languages: [Locale | null, string][] = [
    [null, "language-auto"],
    ["en", "language-en"],
    ["ru", "language-ru"],
  ];
  return (
    <section className="card">
      <label className="label">
        <Localized id="settings-name">
          <span />
        </Localized>
        <input
          type="text"
          maxLength={64}
          value={name}
          placeholder={me.name_from_telegram ? (me.display_name ?? "") : ""}
          onChange={(e) => {
            setName(e.target.value);
          }}
          onBlur={save}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
        />
      </label>
      <Localized id="settings-name-hint">
        <p className="hint small" />
      </Localized>
      <Localized id="settings-language">
        <p className="label" id="language-label" />
      </Localized>
      <div className="chips" role="group" aria-labelledby="language-label">
        {languages.map(([code, key]) => (
          <Localized key={key} id={key}>
            <button
              type="button"
              className="chip"
              aria-pressed={code === current}
              onClick={() => {
                haptics.impact("light");
                patch.mutate({ locale: code });
              }}
            />
          </Localized>
        ))}
      </div>
      {patch.isError && (
        <Localized id="settings-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}

function Zone({ me }: { me: Me }) {
  const cities = useMoonCities().data;
  const patch = usePatchMe();
  const device = deviceZone();
  const ru = me.locale === "ru";
  const now = (zone: string) =>
    new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: zone }).format(
      new Date(),
    );
  const set = (timezone: string) => {
    haptics.impact("light");
    patch.mutate({ timezone });
  };
  return (
    <section className="card">
      <Localized id="settings-zone">
        <h2 />
      </Localized>
      {me.timezone ? (
        <Localized
          id="settings-zone-now"
          vars={{ time: now(me.timezone), zone: labelOf(me.timezone) }}
        >
          <p />
        </Localized>
      ) : (
        <Localized id="settings-zone-unset">
          <p className="hint" />
        </Localized>
      )}
      {device && device !== me.timezone && (
        <Localized id="settings-zone-use-device" vars={{ zone: labelOf(device) }}>
          <button
            type="button"
            className="chip"
            onClick={() => {
              set(device);
            }}
          />
        </Localized>
      )}
      {cities && (
        <label className="label">
          <Localized id="settings-zone-pick">
            <span />
          </Localized>
          <select
            value={
              me.timezone === "UTC"
                ? "UTC"
                : (zoneCities(cities).find((c) => c.timezone === me.timezone)?.timezone ?? "")
            }
            onChange={(e) => {
              if (e.target.value) set(e.target.value);
            }}
          >
            <option value="" disabled />
            {zoneCities(cities).map((c) => (
              <option key={c.timezone} value={c.timezone}>
                {ru ? c.name_ru : c.name_en}
              </option>
            ))}
            <Localized id="settings-zone-utc">
              <option value="UTC" />
            </Localized>
          </select>
        </label>
      )}
      <Localized id="settings-zone-hint">
        <p className="hint small" />
      </Localized>
      {patch.isError && (
        <Localized id="settings-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}

function Moon({ locale, zone }: { locale: Locale; zone: string | null }) {
  const moon = useMoonDays().data;
  const cities = useMoonCities().data;
  const settings = useNotificationSettings().data;
  const setLocation = useSetMoonLocation();
  const save = usePatchNotificationSettings();
  if (!moon) return null;
  const slug = moon.location.slug;
  const city = cityName(
    cities?.find((c) => c.slug === slug),
    slug,
    locale,
  );
  const tap = (body: Parameters<typeof save.mutate>[0]) => {
    haptics.impact("light");
    save.mutate(body, {
      onError: () => {
        haptics.notify("error");
      },
    });
  };
  return (
    <section className="card">
      <Localized id="moon-title" vars={{ city }}>
        <h2 />
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
      <Localized id="moon-calc-note" vars={{ city }}>
        <p className="hint small" />
      </Localized>
      <Localized id="moon-reminders-label">
        <p className="label" id="moon-offsets-label" />
      </Localized>
      {zone && settings ? (
        <>
          <div className="chips" role="group" aria-labelledby="moon-offsets-label">
            {OFFSETS.map((k) => {
              const on = settings.moon.offsets.includes(k);
              return (
                <Localized key={k} id="moon-offset" vars={{ n: k }}>
                  <button
                    type="button"
                    className="chip"
                    aria-pressed={on}
                    onClick={() => {
                      const offsets = on
                        ? settings.moon.offsets.filter((o) => o !== k)
                        : [...settings.moon.offsets, k];
                      tap({ moon: { offsets } });
                    }}
                  />
                </Localized>
              );
            })}
          </div>
          <Localized id="settings-moon-time">
            <p className="label" id="moon-time-label" />
          </Localized>
          <div className="chips" role="group" aria-labelledby="moon-time-label">
            {MOON_TIMES.map((t) => {
              const blocked = quietContains(settings, t);
              return (
                <button
                  key={t}
                  type="button"
                  className="chip"
                  aria-pressed={settings.moon.at.startsWith(t)}
                  disabled={blocked}
                  onClick={() => {
                    tap({ moon: { at: `${t}:00` } });
                  }}
                >
                  {t}
                </button>
              );
            })}
          </div>
        </>
      ) : (
        <Localized id="moon-zone-needed-app">
          <p className="hint" />
        </Localized>
      )}
      {(save.isError || setLocation.isError) && (
        <Localized id="moon-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}

/** As the server's QuietHours.contains (shared with the practice card). */
const contains = (start: string, end: string, at: string) => inQuiet({ start, end }, at);

function quietContains(settings: NotificationSettings, at: string): boolean {
  return contains(settings.quiet.start, settings.quiet.end, at);
}

/** Times of the reminders that are on: quiet hours may not swallow them. */
function activeTimes(settings: NotificationSettings): string[] {
  const out: string[] = [];
  if (settings.moon.offsets.length) out.push(settings.moon.at);
  if (settings.practice.on) out.push(settings.practice.at);
  return out;
}

function Quiet({ zone }: { zone: string | null }) {
  const { l10n } = useLocalization();
  const settings = useNotificationSettings().data;
  const save = usePatchNotificationSettings();
  if (!zone || !settings) return null;
  const { start, end } = settings.quiet;
  const none = start === end;
  const times = activeTimes(settings);
  const swallows = (s: string, e: string) => times.find((t) => contains(s, e, t));
  const setQuiet = (s: string, e: string) => {
    haptics.impact("light");
    save.mutate({ quiet: { start: `${s}:00`, end: `${e}:00` } });
  };
  const conflict = (s: string, e: string) => swallows(`${s}:00`, `${e}:00`);
  return (
    <section className="card">
      <Localized id="settings-quiet">
        <h2 />
      </Localized>
      <div className="row">
        <select
          aria-label={l10n.getString("settings-quiet-from")}
          value={none ? "" : start.slice(0, 5)}
          onChange={(e) => {
            setQuiet(e.target.value, none ? "07:00" : end.slice(0, 5));
          }}
        >
          <option value="" disabled />
          {HOURS.map((h) => (
            <option
              key={h}
              value={h}
              disabled={Boolean(conflict(h, none ? "07:00" : end.slice(0, 5)))}
            >
              {h}
            </option>
          ))}
        </select>
        <select
          aria-label={l10n.getString("settings-quiet-to")}
          value={none ? "" : end.slice(0, 5)}
          onChange={(e) => {
            setQuiet(none ? "22:00" : start.slice(0, 5), e.target.value);
          }}
        >
          <option value="" disabled />
          {HOURS.map((h) => (
            <option
              key={h}
              value={h}
              disabled={Boolean(conflict(none ? "22:00" : start.slice(0, 5), h))}
            >
              {h}
            </option>
          ))}
        </select>
      </div>
      <label className="toggle">
        <input
          type="checkbox"
          checked={none}
          onChange={(e) => {
            if (e.target.checked) setQuiet("00:00", "00:00");
            else save.mutate({ quiet: null }); // back to the default 22:00–07:00
          }}
        />
        <Localized id="settings-quiet-off">
          <span />
        </Localized>
      </label>
      {times.some((t) => contains(start, end, t)) && (
        <Localized id="settings-quiet-conflict">
          <p className="hint" />
        </Localized>
      )}
      <Localized id="settings-cap" vars={{ n: settings.daily_cap }}>
        <p className="label" id="cap-label" />
      </Localized>
      <div className="chips" role="group" aria-labelledby="cap-label">
        {CAPS.map((n) => (
          <button
            key={n}
            type="button"
            className="chip"
            aria-pressed={settings.daily_cap === n}
            onClick={() => {
              haptics.impact("light");
              save.mutate({ daily_cap: n });
            }}
          >
            {n}
          </button>
        ))}
      </div>
      {save.isError && (
        <Localized id="settings-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}

function Privacy() {
  const [showLadies, setShowLadies] = useState(loadShowLadies);
  return (
    <section className="card">
      <Localized id="settings-privacy">
        <h2 />
      </Localized>
      <Localized id="settings-privacy-ladies">
        <p className="hint" />
      </Localized>
      <Localized id="settings-privacy-sharing">
        <p className="hint" />
      </Localized>
      <label className="toggle">
        <input
          type="checkbox"
          checked={showLadies}
          onChange={(e) => {
            setShowLadies(e.target.checked);
            saveShowLadies(e.target.checked);
          }}
        />
        <Localized id="stats-show-ladies">
          <span />
        </Localized>
      </label>
    </section>
  );
}
