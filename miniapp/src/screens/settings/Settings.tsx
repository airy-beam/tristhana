import { Localized, useLocalization } from "@fluent/react";
import { Suspense, useCallback, useEffect, useRef, useState, type Ref } from "react";

import type { Me } from "../../api/client";
import { guideUrl } from "../../guide";
import { lazyRetry } from "../../shell/lazyRetry";
import type { SettingsFocus } from "../../shell/nav";
import { backButtonAvailable, haptics, openLink, useBackButton } from "../../telegram";
import { labelOf, placeFor } from "./zones";

import "./settingsCopy";
import "./settings.css";

// Each page is its own chunk (UI-06 stage 3): the five rows need none of them to show.
const LOAD = {
  language: () => import("./pages/Language"),
  city: () => import("./pages/City"),
  "day-off": () => import("./pages/DayOff"),
  remind: () => import("./pages/Reminders"),
  more: () => import("./pages/More"),
};
type PageName = keyof typeof LOAD;
const PAGES = {
  language: lazyRetry(LOAD.language),
  city: lazyRetry(LOAD.city),
  "day-off": lazyRetry(LOAD["day-off"]),
  remind: lazyRetry(LOAD.remind),
  more: lazyRetry(LOAD.more),
};
/** The bot's five rows, in the bot's order. */
const ROWS = Object.keys(LOAD) as PageName[];

type Line = [id: string, vars?: Record<string, string | number>];

/** A row's label with its value, as the bot's `/settings` builds it (same keys, same text). */
function lineOf(page: PageName, me: Me, language: string): Line {
  switch (page) {
    case "language":
      return ["settings-language-line", { language }];
    case "city": {
      const zone = me.timezone;
      if (!zone) return ["settings-city-no-zone-line"];
      // My own city: its name, no offset (ADR-0044).
      if (me.home_city) {
        const place = placeFor(me.home_city, zone, me.locale);
        return ["settings-city-line", { zone: labelOf(zone, place, zone) }];
      }
      // No city: the row says what the clock is, so the offset is the information.
      return [
        me.home_city_chosen ? "settings-city-unlisted-line" : "settings-city-unset-line",
        { zone: labelOf(zone) },
      ];
    }
    case "day-off": {
      if (!me.day_off) return ["settings-day-off-unset-line"];
      const [d, e] = [...me.day_off].sort((a, b) => a - b);
      if (d === undefined) return ["settings-day-off-none-line"];
      return e === undefined
        ? ["settings-day-off-line", { d }]
        : ["settings-days-off-line", { d, e }];
    }
    case "remind":
      return ["settings-reminders-button"];
    case "more":
      return ["settings-more-button"];
  }
}

interface Props {
  me: Me;
  onBack: () => void;
  /** Open on a page: the stats "Set your weekly day off" link, or the practice reminder
   * (UI-06). Back from that page closes Settings: the person returns to where they were. */
  focus?: SettingsFocus | undefined;
  /** The shell focuses the heading when Settings opens. */
  headingRef?: Ref<HTMLHeadingElement> | undefined;
}

/** Settings (ID-06, UI-06 stage 3): the bot's five rows, each carrying its value, and a quiet
 * Guide row. Drawn from the account already loaded, so it asks the server nothing; each row
 * opens a short page that reads what it shows. Pushed by the gear and by Telegram's ⋯ item.
 * Loaded lazily, so Today stays light. */
export default function Settings({ me, onBack, focus, headingRef }: Props) {
  useBackButton(onBack);
  const { l10n } = useLocalization();
  const [page, setPage] = useState<PageName | null>(focus ?? null);
  // By the time a row is tapped its page is usually there.
  useEffect(() => {
    for (const load of Object.values(LOAD)) load().catch(() => undefined);
  }, []);

  // The rows stay mounted (hidden) under a page: Back finds them as they were left.
  const left = useRef<{ top: number; focus: Element } | null>(null);
  const open = (name: PageName, from: Element) => {
    haptics.selection();
    left.current = { top: window.scrollY, focus: from };
    setPage(name);
    window.scrollTo({ top: 0 });
  };
  const close = useCallback(() => {
    setPage(null);
  }, []);
  useEffect(() => {
    const was = left.current;
    if (page || !was) return;
    left.current = null;
    window.scrollTo({ top: was.top });
    // The row that was tapped takes the focus back (a tap focuses nothing on iOS).
    if (was.focus instanceof HTMLElement) was.focus.focus({ preventScroll: true });
  }, [page]);

  const language = l10n.getString(
    me.locale_from_telegram ? "language-auto" : `language-${me.locale}`,
  );
  const Page = page && PAGES[page];
  return (
    <>
      {Page && (
        <Suspense fallback={<main className="screen" aria-busy="true" />}>
          <Page me={me} onBack={focus ? onBack : close} />
        </Suspense>
      )}
      <main className="screen settings" hidden={page !== null}>
        {!backButtonAvailable() && (
          <Localized id="stats-back">
            <button type="button" className="link" onClick={onBack} />
          </Localized>
        )}
        <Localized id="settings-title">
          {/* Opened on a page, that page's heading takes the focus, not this hidden one. */}
          <h1 ref={focus ? undefined : headingRef} tabIndex={-1} />
        </Localized>
        <div className="card list">
          {ROWS.map((name) => {
            const [id, vars = {}] = lineOf(name, me, language);
            return (
              <Localized key={name} id={id} vars={vars}>
                <button
                  type="button"
                  className="lrow srow"
                  onClick={(event) => {
                    open(name, event.currentTarget);
                  }}
                />
              </Localized>
            );
          })}
        </div>
        <Localized id="guide-open">
          <button
            type="button"
            className="link guide"
            onClick={() => {
              haptics.selection();
              openLink(guideUrl(me.locale));
            }}
          />
        </Localized>
      </main>
    </>
  );
}
