import { Localized, useLocalization } from "@fluent/react";
import { Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import type { Me } from "../../api/client";
import { GUIDE_PAGE } from "../../guide";
import { ChunkGuard } from "../../shell/ChunkGuard";
import { lazyRetry } from "../../shell/lazyRetry";
import type { SettingsFocus } from "../../shell/nav";
import { backButtonAvailable, haptics, useBackButton } from "../../telegram";
import { GuideLink } from "../GuideLink";
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
  headingRef?: ((element: HTMLHeadingElement | null) => void) | undefined;
}

/** Settings (ID-06, UI-06 stage 3): the bot's five rows, each carrying its value, and a quiet
 * Guide row. Drawn from the account already loaded, so it asks the server nothing; each row
 * opens a short page that reads what it shows. Pushed by the gear and by Telegram's ⋯ item.
 * Loaded lazily, so Today stays light. */
export default function Settings({ me, onBack, focus, headingRef }: Props) {
  const { l10n } = useLocalization();
  const [page, setPage] = useState<PageName | null>(focus ?? null);
  // The page `focus` opened: Back there closes Settings (the person returns to where they
  // were). Any other page, also one reached from that page, goes back to the five rows.
  const [direct, setDirect] = useState(focus !== undefined);
  // A page whose chunk did not load: the rows say so and stay usable.
  const [failed, setFailed] = useState(false);
  // By the time a row is tapped its page is usually there.
  useEffect(() => {
    for (const load of Object.values(LOAD)) load().catch(() => undefined);
  }, []);

  // The rows stay mounted (hidden) under a page: Back finds them as they were left.
  const left = useRef<{ top: number; focus: Element | null } | null>(null);
  const title = useRef<HTMLHeadingElement | null>(null);
  const titleRef = useCallback(
    (element: HTMLHeadingElement | null) => {
      title.current = element;
      // Opened on a page, that page's heading takes the focus, not this hidden one.
      if (focus) return;
      headingRef?.(element);
    },
    [focus, headingRef],
  );
  const show = (name: PageName) => {
    setFailed(false);
    setDirect(false);
    setPage(name);
    window.scrollTo({ top: 0 });
  };
  const open = (name: PageName, from: Element) => {
    haptics.selection();
    left.current = { top: window.scrollY, focus: from };
    show(name);
  };
  // From one page to another (Reminders without a zone → My city): Back from there returns
  // to the rows, to the row that opened the first page, else to the heading.
  const openFromPage = (name: PageName) => {
    haptics.selection();
    left.current ??= { top: 0, focus: null };
    show(name);
  };
  const close = useCallback(() => {
    setPage(null);
  }, []);
  const failPage = useCallback(() => {
    setFailed(true);
    setPage(null);
  }, []);
  // Settings owns the Back layer of its pages, so Back works while a page's chunk still
  // loads. A field that has the focus is blurred first: it saves on blur (the name).
  const back = () => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    if (page && !direct) close();
    else onBack();
  };
  useBackButton(back);
  // Before the frame is painted: the rows come back where they were, with no jump.
  useLayoutEffect(() => {
    const was = left.current;
    if (page || !was) return;
    left.current = null;
    window.scrollTo({ top: was.top });
    // The row that was tapped takes the focus back (a tap focuses nothing on iOS).
    const to =
      was.focus instanceof HTMLElement && was.focus.isConnected ? was.focus : title.current;
    to?.focus({ preventScroll: true });
  }, [page]);

  const language = l10n.getString(
    me.locale_from_telegram ? "language-auto" : `language-${me.locale}`,
  );
  const Page = page && PAGES[page];
  return (
    <>
      {Page && (
        <ChunkGuard key={page} onFail={failPage}>
          <Suspense fallback={<main className="screen" aria-busy="true" />}>
            <Page me={me} onBack={back} onOpen={openFromPage} />
          </Suspense>
        </ChunkGuard>
      )}
      <main className="screen settings" hidden={page !== null}>
        {!backButtonAvailable() && (
          <Localized id="stats-back">
            <button type="button" className="link" onClick={onBack} />
          </Localized>
        )}
        <Localized id="settings-title">
          <h1 ref={titleRef} tabIndex={-1} />
        </Localized>
        {failed && (
          <Localized id="chunk-failed">
            <p className="status" role="alert" />
          </Localized>
        )}
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
        <GuideLink locale={me.locale} page={GUIDE_PAGE.settings} />
      </main>
    </>
  );
}
