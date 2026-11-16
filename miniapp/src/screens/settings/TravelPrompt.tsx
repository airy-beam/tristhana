import { Localized } from "@fluent/react";
import { useState } from "react";

import { useMoonCities, usePatchMe, type City } from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { haptics } from "../../telegram";
import { deviceZone, keep, labelOf, placeFor, placeOf, travelPending } from "./zones";

/** "Your phone is on Bangkok time" when the phone's UTC offset differs from the account's
 * zone. The zone is never changed silently (ID-06): a phone and a desktop would flip it. */
export function TravelPrompt({
  zone,
  locale,
  home,
}: {
  zone: string | null;
  locale: Locale;
  /** The home city (MD-04): names "here"; switching away clears it on the server. */
  home?: City | null | undefined;
}) {
  const cities = useMoonCities().data;
  const patch = usePatchMe();
  const [dismissed, setDismissed] = useState(false);
  const device = deviceZone();
  if (!zone || !device || dismissed || !travelPending(zone)) return null;
  const ru = locale === "ru";
  const there = placeOf(device, cities, ru);
  const here = placeFor(home, zone, locale) ?? placeOf(zone, cities, ru);
  return (
    <section className="card" role="status">
      {/* Says what the two zones are, so both keep their offset (ADR-0044). */}
      <Localized
        id="zone-travel"
        vars={{ device: labelOf(device, there), current: labelOf(zone, here) }}
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
                  onError: () => {
                    haptics.notify("error");
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
