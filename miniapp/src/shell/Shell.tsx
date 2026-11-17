import { Localized } from "@fluent/react";
import {
  Suspense,
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { Me } from "../api/client";
import { Home } from "../screens/Home";
import { NextStep } from "../screens/NextStep";
import { TravelPrompt } from "../screens/settings/TravelPrompt";
import { placeFor } from "../screens/settings/zones";
import { TodayCard } from "../screens/TodayCard";
import { ClassRow, MoonRow } from "../screens/TodayRows";
import { haptics, useBackButton, useBackShown, useSettingsButton } from "../telegram";
import { Covered } from "../telegram/covered";
import { ChunkBoundary } from "./ChunkBoundary";
import { lazyRetry } from "./lazyRetry";
import { launchNav, navigate, type Screen, type SettingsFocus, type Start, type Tab } from "./nav";
import { TabBar } from "./TabBar";

// Today is in the first chunk; the other tabs and every pushed screen are their own chunks.
const Stats = lazyRetry(() => import("../screens/stats/Stats"));
const Links = lazyRetry(() => import("../screens/settings/Links"));
const Settings = lazyRetry(() => import("../screens/settings/Settings"));
const Progression = lazyRetry(() => import("../screens/progression/Progression"));
const MoonScreen = lazyRetry(() => import("../screens/moon/MoonScreen"));
const MySchedule = lazyRetry(() => import("../screens/shalas/MySchedule"));
const Students = lazyRetry(() => import("../screens/teachers/Students"));
const Announcements = lazyRetry(() => import("../screens/announcements/Announcements"));
const DirectoryListing = lazyRetry(() => import("../screens/settings/DirectoryListing"));

const busy = <main className="screen" aria-busy="true" />;

interface Props {
  /** The account, once `/me` has answered. */
  me: Me | undefined;
  /** From the launch params, for the greeting until then. */
  firstName: string | null;
}

/** The Mini App's shell (UI-06 stage 2, ADR-0047): three tabs, one stack, a gear. What shows
 * is the top of the stack, else the tab's root. Settings is the one screen that opens over
 * anything (Telegram's ⋯ item works everywhere), so what it was opened over stays mounted,
 * hidden, and Back finds it as it was left. The tab bar and the gear are drawn only on a root
 * with no Back layer mounted, so a screen shows Back or the tabs, never both. */
export function Shell({ me, firstName }: Props) {
  const [nav, dispatch] = useReducer(navigate, window.location.search, launchNav);
  const [showDetails, setShowDetails] = useState(import.meta.env.DEV);
  const backShown = useBackShown();
  const top = nav.stack.at(-1);
  const settings = top?.name === "settings" ? top : undefined;
  /** The pushed screen that shows, or waits under Settings; none on a root. */
  const below = settings ? nav.stack.at(-2) : top;
  const pushed = below?.name === "settings" ? undefined : below; // never two Settings
  const covered = settings !== undefined;

  // After a tab switch, a pop or Settings opening, the heading of what mounts takes the
  // focus, whenever it mounts (a lazy screen mounts later than the switch).
  const switched = useRef(false);
  const heading = useCallback((element: HTMLHeadingElement | null) => {
    if (!element || !switched.current) return;
    switched.current = false;
    element.focus({ preventScroll: true }); // the page is scrolled on purpose, not by this
  }, []);

  const toTab = useCallback(
    (tab: Tab, start?: Start) => {
      window.scrollTo({ top: 0 }); // also what a tap on the active tab does
      if (tab === nav.tab && nav.stack.length === 0 && !start) return;
      switched.current = true;
      dispatch(start ? { type: "tab", tab, start } : { type: "tab", tab });
    },
    [nav],
  );
  const push = useCallback((screen: Screen) => {
    window.scrollTo({ top: 0 });
    dispatch({ type: "push", screen });
  }, []);

  // The gear and Telegram's ⋯ "Settings" item (ID-06): one route. Where it was opened (the
  // page's scroll, the focus) is given back when it closes.
  const under = useRef<HTMLDivElement>(null);
  const left = useRef<{ top: number; focus: Element | null } | null>(null);
  const openSettings = useCallback(
    (focus?: SettingsFocus) => {
      if (covered) return;
      left.current = { top: window.scrollY, focus: document.activeElement };
      window.scrollTo({ top: 0 });
      switched.current = true;
      dispatch(focus ? { type: "settings", focus } : { type: "settings" });
    },
    [covered],
  );
  const menuSettings = useCallback(() => {
    openSettings();
  }, [openSettings]);
  useSettingsButton(menuSettings);
  useEffect(() => {
    const was = left.current;
    if (covered || !was) return;
    left.current = null;
    switched.current = false; // Settings may never have mounted (its chunk failed)
    window.scrollTo({ top: was.top });
    // What had the focus, when it is still there (the gear is drawn anew); else the heading.
    const focus =
      was.focus instanceof HTMLElement && was.focus !== document.body && was.focus.isConnected
        ? was.focus
        : under.current?.querySelector("h1");
    focus?.focus({ preventScroll: true });
  }, [covered]);

  const pop = useCallback(() => {
    if (!covered) {
      // A root mounts anew: at the top, its heading focused.
      window.scrollTo({ top: 0 });
      switched.current = true;
    }
    dispatch({ type: "pop" });
  }, [covered]);

  let shown: ReactNode;
  if (pushed) {
    shown = me ? <Pushed screen={pushed} me={me} onBack={pop} /> : busy;
  } else if (nav.tab === "today") {
    shown = (
      <Home
        firstName={me ? me.display_name : firstName}
        showDetails={showDetails}
        onGreetingLongPress={() => {
          setShowDetails(true);
        }}
        headingRef={heading}
      >
        {me && <TravelPrompt zone={me.timezone} locale={me.locale} home={me.home_city} />}
        {me && <TodayCard zone={me.timezone} locale={me.locale} />}
        {me && (
          <NextStep
            zone={me.timezone}
            place={placeFor(me.home_city, me.timezone, me.locale)}
            onOpen={(step) => {
              // Each step leads to the place where it is done (spec §6): a shala step to the
              // class form or the student invite on that shala's card.
              if (step.kind === "reminder") openSettings("remind");
              else if (step.kind === "position") push({ name: "asanas" });
              else if (!step.shala_id) toTab("shala", "invite");
              else
                toTab("shala", `${step.kind === "add_class" ? "class" : "join"}:${step.shala_id}`);
            }}
          />
        )}
        {/* Today's class and the next moon day: two rows of one small card (gone while it has
            neither). */}
        {me && (
          <div className="card list">
            <ClassRow
              locale={me.locale}
              onOpen={() => {
                push({ name: "schedule" });
              }}
            />
            <MoonRow
              locale={me.locale}
              onOpen={() => {
                push({ name: "moon" });
              }}
            />
          </div>
        )}
      </Home>
    );
  } else if (!me) {
    shown = busy;
  } else if (nav.tab === "practice") {
    shown = (
      <Stats
        locale={me.locale}
        zone={me.timezone}
        headingRef={heading}
        onAsanas={() => {
          push({ name: "asanas" });
        }}
        onDayOff={() => {
          openSettings("day-off");
        }}
      />
    );
  } else {
    shown = (
      <Links
        start={nav.start}
        headingRef={heading}
        onSchedule={() => {
          push({ name: "schedule" });
        }}
        onStudents={() => {
          push({ name: "students" });
        }}
      />
    );
  }

  // `!top` as well: a pushed screen's Back layer is counted only after its first frame.
  const tabs = !backShown && !top;
  return (
    <div className={tabs ? "shell tabs" : "shell"}>
      {/* Before the screen, so its own layers (a form, an unsaved note) sit above this one. */}
      {pushed && <StackBack onBack={pop} />}
      {tabs && (
        <Localized id="settings-open" attrs={{ "aria-label": true }}>
          <button
            type="button"
            className="gear"
            onClick={() => {
              haptics.selection();
              openSettings();
            }}
          />
        </Localized>
      )}
      {/* Settings' Back layer mounts when it opens: over every layer of the hidden screen, and
          there while its chunk loads or fails. */}
      {settings && <StackBack onBack={pop} />}
      {/* First in the page, so an id both screens use (a card's heading) is found here. */}
      {settings && (
        <ChunkBoundary onBack={pop}>
          <Suspense fallback={busy}>
            {me ? (
              <Settings me={me} onBack={pop} focus={settings.focus} headingRef={heading} />
            ) : (
              busy
            )}
          </Suspense>
        </ChunkBoundary>
      )}
      <div className="under" ref={under} hidden={covered}>
        <Covered value={covered}>
          <ChunkBoundary key={pushed ? pushed.name : nav.tab} onBack={pushed ? pop : undefined}>
            <Suspense fallback={busy}>{shown}</Suspense>
          </ChunkBoundary>
        </Covered>
      </div>
      {tabs && <TabBar tab={nav.tab} onTab={toTab} />}
    </div>
  );
}

/** A pushed screen has Back from the moment it is pushed: while its chunk loads, and when the
 * chunk fails. The screen's own layer goes on top of this one and does the same. */
function StackBack({ onBack }: { onBack: () => void }) {
  useBackButton(onBack);
  return null;
}

function Pushed({
  screen,
  me,
  onBack,
}: {
  screen: Exclude<Screen, { name: "settings" }>;
  me: Me;
  onBack: () => void;
}) {
  switch (screen.name) {
    case "asanas":
      return <Progression locale={me.locale} onBack={onBack} />;
    case "moon":
      return <MoonScreen locale={me.locale} onBack={onBack} />;
    case "schedule":
      return <MySchedule locale={me.locale} onBack={onBack} />;
    case "students":
      return <Students locale={me.locale} onBack={onBack} />;
    case "announce":
      return (
        <Announcements
          mode={{ view: "compose", shala: screen.shala }}
          locale={me.locale}
          onBack={onBack}
        />
      );
    case "listing":
      return <DirectoryListing locale={me.locale} onBack={onBack} />;
  }
}
