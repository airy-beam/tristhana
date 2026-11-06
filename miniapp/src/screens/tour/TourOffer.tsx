import { Localized } from "@fluent/react";
import { useState } from "react";

import { useDays } from "../../api/client";
import { haptics } from "../../telegram";
import { loggedBefore, markTourSeen, tourSeen } from "../onboard";
import { travelPending } from "../settings/zones";

/** The one-time quick tour offer (UI-02), under the Today card. Decided once, when Home opens,
 * so nothing moves under a thumb mid-log. "Has logged" is the opposite of `home-first-hint`,
 * so the two never show together: logging comes first. */
export function TourOffer({ zone, onStart }: { zone: string | null; onStart: () => void }) {
  const days = useDays().data;
  const [offered, setOffered] = useState<boolean | null>(null);
  if (offered === null && days) {
    const logged = days.days.length > 0 || loggedBefore();
    setOffered(logged && !tourSeen() && !travelPending(zone));
  }
  if (!offered) return null;
  const answer = () => {
    haptics.impact("light");
    markTourSeen();
    setOffered(false);
  };
  return (
    <section className="card">
      <Localized id="tour-offer">
        <p />
      </Localized>
      <div className="chips">
        <Localized id="tour-offer-yes">
          <button
            type="button"
            className="chip"
            onClick={() => {
              answer();
              onStart();
            }}
          />
        </Localized>
        <Localized id="tour-offer-no">
          <button type="button" className="link" onClick={answer} />
        </Localized>
      </div>
    </section>
  );
}
