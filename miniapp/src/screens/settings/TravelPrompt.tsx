import { Localized } from "@fluent/react";
import { useState } from "react";

import { useMoonCities, usePatchMe } from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { haptics } from "../../telegram";
import { deviceZone, keep, keptFor, offsetOf, placeOf } from "./zones";

/** "Your phone is on Bangkok time" when the phone's UTC offset differs from the account's
 * zone. The zone is never changed silently (ID-06): a phone and a desktop would flip it. */
export function TravelPrompt({ zone, locale }: { zone: string | null; locale: Locale }) {
  const cities = useMoonCities().data;
  const patch = usePatchMe();
  const [dismissed, setDismissed] = useState(false);
  const device = deviceZone();
  if (!zone || !device || dismissed || keptFor(device)) return null;
  if (offsetOf(device) === offsetOf(zone)) return null; // Kiev vs Kyiv: same clock
  const ru = locale === "ru";
  const there = placeOf(device, cities, ru);
  const here = placeOf(zone, cities, ru);
  return (
    <section className="card" role="status">
      <Localized
        id="zone-travel"
        vars={{ device: `${there} (${offsetOf(device)})`, current: `${here} (${offsetOf(zone)})` }}
      >
        <p />
      </Localized>
      <div className="chips">
        <Localized id="zone-travel-switch" vars={{ city: there }}>
          <button
            type="button"
            className="chip"
            onClick={() => {
              haptics.impact("light");
              // Hidden only once it worked: a failed switch must not look like success.
              patch.mutate(
                { timezone: device },
                {
                  onSuccess: () => {
                    setDismissed(true);
                  },
                },
              );
            }}
          />
        </Localized>
        <Localized id="zone-travel-keep" vars={{ city: here }}>
          <button
            type="button"
            className="chip"
            onClick={() => {
              keep(device);
              setDismissed(true);
            }}
          />
        </Localized>
      </div>
      {patch.isError && (
        <Localized id="settings-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}
