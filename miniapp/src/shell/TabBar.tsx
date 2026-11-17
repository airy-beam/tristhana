import { Localized, useLocalization } from "@fluent/react";

import { haptics } from "../telegram";
import { TABS, type Tab } from "./nav";

interface Props {
  tab: Tab;
  onTab: (tab: Tab) => void;
}

/** Today / Practice / Shala (UI-06). Drawn by the shell only while no Back layer is mounted.
 * A `nav` with `aria-current`, not a `tablist`: there is no arrow-key contract. */
export function TabBar({ tab, onTab }: Props) {
  const { l10n } = useLocalization();
  return (
    <nav className="tabbar" aria-label={l10n.getString("tabs-label")}>
      {TABS.map((t) => (
        <Localized key={t} id={`tab-${t}`}>
          <button
            type="button"
            aria-current={t === tab ? "page" : undefined}
            onClick={() => {
              haptics.selection();
              onTab(t);
            }}
          />
        </Localized>
      ))}
    </nav>
  );
}
