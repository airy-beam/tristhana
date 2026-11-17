import { Localized, useLocalization } from "@fluent/react";

import "./practiceCopy";

// Practice · Rest · 🌙 Moon day · 🌱 No practice, in this order (UI-06 stage 3, QA). The third
// and fourth carry the day card's own words (`status-*`): one word per thing.
const ITEMS = [
  ["practiced", "stats-legend-practiced"],
  ["rest", "stats-legend-rest"],
  ["ring", "status-moon"],
  ["skipped", "status-skipped"],
] as const;

/** What the marks mean: three fills and the moon ring. Today's outline, a day with nothing
 * logged and the days to come need no entry; a ladies' holiday is never a fifth one. */
export function Legend() {
  const { l10n } = useLocalization();
  return (
    <ul className="legend" aria-label={l10n.getString("stats-legend-label")}>
      {ITEMS.map(([swatch, id]) => (
        <li key={swatch}>
          <span className={`swatch ${swatch}`} aria-hidden="true" />
          <Localized id={id}>
            <span />
          </Localized>
        </li>
      ))}
    </ul>
  );
}
