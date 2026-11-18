import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import { useMoonCities, usePatchMe, type MePatch } from "../../../api/client";
import { Field, Select } from "../../../ui/controls";
import { haptics, openLink } from "../../../telegram";
import { deviceZone, labelOf, placeFor } from "../zones";
import { Page, SaveFailed, type PageProps } from "./Page";

const OSM_COPYRIGHT = "https://www.openstreetmap.org/copyright";
const UNLISTED = "-"; // the select's "My city isn't listed" (never a slug)

const now = (zone: string) =>
  new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: zone }).format(
    new Date(),
  );

/** Settings → "🏙 My city" (MD-04, ADR-0029): a listed city sets its zone; otherwise the
 * phone's zone or UTC, with no city. */
export default function City({ me, onBack }: PageProps) {
  const { l10n } = useLocalization();
  const cities = useMoonCities().data;
  const patch = usePatchMe();
  const device = deviceZone();
  const ru = me.locale === "ru";
  const [unlisted, setUnlisted] = useState(false);
  const listed = me.home_city?.slug;
  const showUnlisted = unlisted || (me.home_city_chosen && !listed);
  // My own city: its name, no offset (ADR-0044). Without one the line says what the clock
  // is, so the offset is the information.
  const place = placeFor(me.home_city, me.timezone, me.locale);
  const save = (body: MePatch) => {
    haptics.impact("light");
    patch.mutate(body, {
      onError: () => {
        haptics.notify("error");
      },
    });
  };
  return (
    <Page title="settings-city" onBack={onBack} busy={!cities}>
      <section className="card">
        {me.timezone ? (
          <Localized
            id="settings-zone-now"
            vars={{
              time: now(me.timezone),
              zone: labelOf(me.timezone, place, place ? me.timezone : null),
            }}
          >
            <p />
          </Localized>
        ) : (
          <Localized id="settings-zone-unset">
            <p className="hint" />
          </Localized>
        )}
        {cities && (
          <Field label={l10n.getString("settings-city-pick")}>
            {/* Every listed city (Almaty and Astana share a zone, but each is its own). */}
            <Select
              value={showUnlisted ? UNLISTED : (listed ?? "")}
              onChange={(e) => {
                const value = e.target.value;
                if (value === UNLISTED) {
                  setUnlisted(true);
                  return;
                }
                setUnlisted(false);
                save({ home_city: value });
              }}
            >
              <option value="" disabled />
              {[...cities]
                .sort((a, b) =>
                  (ru ? a.name_ru : a.name_en).localeCompare(ru ? b.name_ru : b.name_en, me.locale),
                )
                .map((c) => (
                  <option key={c.slug} value={c.slug}>
                    {ru ? c.name_ru : c.name_en}
                  </option>
                ))}
              <Localized id="settings-city-unlisted-option">
                <option value={UNLISTED} />
              </Localized>
            </Select>
          </Field>
        )}
        {showUnlisted && (
          <div className="field">
            <div className="chips">
              {device && (
                <Localized id="settings-city-use-device" vars={{ zone: labelOf(device) }}>
                  <button
                    type="button"
                    className="chip"
                    aria-pressed={!listed && me.timezone === device}
                    onClick={() => {
                      save({ home_city: null, timezone: device });
                    }}
                  />
                </Localized>
              )}
              <Localized id="settings-zone-utc">
                <button
                  type="button"
                  className="chip"
                  aria-pressed={me.timezone === "UTC"}
                  onClick={() => {
                    save({ home_city: null, timezone: "UTC" });
                  }}
                />
              </Localized>
            </div>
          </div>
        )}
        <Localized id="settings-zone-hint">
          <p className="hint small" />
        </Localized>
        <SaveFailed when={patch.isError} />
      </section>
      {/* The map credit (ODbL, ADR-0029) sits where the location is talked about, linked to
       * OpenStreetMap's own copyright page. */}
      <Localized
        id="settings-privacy-location"
        elems={{
          osm: (
            <a
              href={OSM_COPYRIGHT}
              onClick={(event) => {
                event.preventDefault();
                openLink(OSM_COPYRIGHT);
              }}
            />
          ),
        }}
      >
        <p className="hint small" />
      </Localized>
    </Page>
  );
}
