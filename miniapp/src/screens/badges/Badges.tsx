import { Localized, useLocalization, type ReactLocalization } from "@fluent/react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { api, fail, useCatalog, type Badge, type Badges, type Catalog } from "../../api/client";
import { addMessages } from "../../i18n/lazyMessages";
import type { Locale } from "../../i18n/negotiate";
import enBadges from "../../locales/en/badges.ftl?raw";
import ruBadges from "../../locales/ru/badges.ftl?raw";
import { backButtonAvailable, useBackButton } from "../../telegram";
import { get, itemLabel } from "../progression/progressionText";

addMessages({ en: enBadges, ru: ruBadges });

export const SEEN_KEY = "badges.seen";

/** Keys shown before on this device (the "New" pill). Storage may be blocked: then all is new. */
export function loadSeen(): Set<string> {
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter((k) => typeof k === "string") : []);
  } catch {
    return new Set();
  }
}

function saveSeen(keys: Iterable<string>): void {
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify([...new Set(keys)]));
  } catch {
    // Private mode or blocked storage: the pill just shows again next time.
  }
}

function useBadges() {
  return useQuery({
    queryKey: ["me", "badges"],
    queryFn: async (): Promise<Badges> => {
      const { data, error, response } = await api.GET("/api/v1/me/badges");
      if (!data) fail(response, error);
      return data;
    },
  });
}

/** The catalog name without the variant letter ("Kapotasana", not "Kapotasana B"). */
function stopName(catalog: Catalog, b: Badge, locale: Locale): string {
  const stop = catalog.series.find((s) => s.slug === b.series)?.stops.find((s) => s.key === b.stop);
  const name = stop ? (locale === "ru" ? stop.ru : stop.latin) : (b.stop ?? "");
  return name.replace(/ [A-Z]$/, "");
}

function args(
  l10n: ReactLocalization,
  catalog: Catalog,
  b: Badge,
  locale: Locale,
): Record<string, string | number> {
  const found: Record<string, string | number> = {};
  if (b.count != null) found.count = b.count;
  if (b.before != null) found.before = b.before;
  if (b.stop != null) found.asana = stopName(catalog, b, locale);
  if (b.item != null) found.item = itemLabel(l10n, catalog, b.item, locale);
  return found;
}

/** "🏅 Badges" (GM-02): what a person has, grouped, each with the date it came from. Nothing
 * here is a score: no locked badges, no progress, no "next". Its own chunk (with its copy),
 * opened from My practice. */
export default function BadgesScreen({ locale, onBack }: { locale: Locale; onBack: () => void }) {
  useBackButton(onBack);
  const query = useBadges();
  const catalogQuery = useCatalog();
  const catalog = catalogQuery.data;
  const [seen] = useState(loadSeen); // as it was when the screen opened
  const data = query.data;
  useEffect(() => {
    if (data) saveSeen([...seen, ...data.badges.map((b) => b.key)]);
  }, [data, seen]);
  return (
    <main className="screen badges">
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      <Localized id="badges-title">
        <h1 />
      </Localized>
      {query.isError || (catalogQuery.isError && !catalog) ? (
        <Localized id="badges-load-failed">
          <p className="status" role="alert" />
        </Localized>
      ) : !data || !catalog ? (
        <div aria-busy="true" />
      ) : (
        <List badges={data.badges} catalog={catalog} locale={locale} seen={seen} />
      )}
      <Localized id="badges-note">
        <p className="hint small" />
      </Localized>
    </main>
  );
}

function List({
  badges,
  catalog,
  locale,
  seen,
}: {
  badges: readonly Badge[];
  catalog: Catalog;
  locale: Locale;
  seen: Set<string>;
}) {
  const { l10n } = useLocalization();
  const [open, setOpen] = useState<string | null>(null);
  const format = useMemo(
    () =>
      new Intl.DateTimeFormat(locale, {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }),
    [locale],
  );
  // An older app skips keys it has no copy for (a badge added on the server).
  const known = badges.filter((b) => l10n.getBundle(`badge-${b.key}`) !== null);
  if (known.length === 0) {
    return (
      <Localized id="badges-empty">
        <p className="card" />
      </Localized>
    );
  }
  return (
    <>
      {(["practice", "asanas"] as const).map((group) => {
        const inGroup = known.filter((b) => b.group === group);
        if (inGroup.length === 0) return null;
        return (
          <section key={group} className="card" aria-labelledby={`badges-${group}`}>
            <Localized id={`badges-group-${group}`}>
              <h2 id={`badges-${group}`} />
            </Localized>
            <ul className="badge-list">
              {inGroup.map((b) => {
                const vars = args(l10n, catalog, b, locale);
                const id = `badge-${b.key}`;
                const name = get(l10n, id, vars);
                const about = aboutOf(l10n, id, vars);
                const when = b.at_record_start
                  ? get(l10n, "badges-at-start")
                  : b.earned_on
                    ? format.format(new Date(`${b.earned_on}T00:00:00Z`))
                    : "";
                const expanded = open === b.key;
                return (
                  <li key={b.key}>
                    <button
                      type="button"
                      className="badge-row"
                      aria-expanded={expanded}
                      onClick={() => {
                        setOpen(expanded ? null : b.key);
                      }}
                    >
                      <span className="badge-icon" aria-hidden="true">
                        {b.icon}
                      </span>
                      <span className="badge-name">
                        {name}
                        {!seen.has(b.key) && (
                          <>
                            {" "}
                            <span className="badge-new">{get(l10n, "badges-new")}</span>
                          </>
                        )}
                        {when && <span className="hint small badge-when">{when}</span>}
                      </span>
                    </button>
                    {expanded && about && <p className="hint badge-about">{about}</p>}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </>
  );
}

function aboutOf(l10n: ReactLocalization, id: string, vars: Record<string, string | number>) {
  const bundle = l10n.getBundle(id);
  const pattern = bundle?.getMessage(id)?.attributes.about;
  return bundle && pattern ? bundle.formatPattern(pattern, vars).replace(/[⁨⁩]/g, "") : "";
}
