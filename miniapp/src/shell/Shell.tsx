import { Localized } from "@fluent/react";
import { Suspense, useCallback, useReducer, useRef, useState, type ReactNode } from "react";

import type { Me } from "../api/client";
import { Home } from "../screens/Home";
import { TravelPrompt } from "../screens/settings/TravelPrompt";
import { TodayCard } from "../screens/TodayCard";
import { MoonRow } from "../screens/TodayRows";
import { haptics, useBackButton, useBackShown, useSettingsButton } from "../telegram";
import { ChunkBoundary } from "./ChunkBoundary";
import { lazyRetry } from "./lazyRetry";
import { launchNav, navigate, type Screen, type Start, type Tab } from "./nav";
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

/** The Mini App's shell (UI-06 stage 2, ADR-0047): three tabs, one stack, a gear. One thing is
 * mounted: the top of the stack, else the tab's root. The tab bar and the gear are drawn only
 * while no Back layer is mounted, so a screen shows Back or the tabs, never both. */
export function Shell({ me, firstName }: Props) {
  const [nav, dispatch] = useReducer(navigate, window.location.search, launchNav);
  const [showDetails, setShowDetails] = useState(import.meta.env.DEV);
  const backShown = useBackShown();

  // After a tab switch the new root's heading takes the focus, whenever it mounts (a lazy
  // root mounts later than the switch).
  const switched = useRef(false);
  const heading = useCallback((element: HTMLHeadingElement | null) => {
    if (!element || !switched.current) return;
    switched.current = false;
    element.focus();
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
  const pop = useCallback(() => {
    dispatch({ type: "pop" });
  }, []);
  // The gear and Telegram's ⋯ "Settings" item (ID-06): one route.
  const openSettings = useCallback(() => {
    dispatch({ type: "settings" });
  }, []);
  useSettingsButton(openSettings);

  const top = nav.stack.at(-1);
  let shown: ReactNode;
  if (top) {
    shown = me ? <Pushed screen={top} me={me} onBack={pop} /> : busy;
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
          <MoonRow
            locale={me.locale}
            onOpen={() => {
              push({ name: "moon" });
            }}
          />
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
          window.scrollTo({ top: 0 });
          dispatch({ type: "settings", focus: "day-off" });
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

  const tabs = !backShown;
  return (
    <div className={tabs ? "shell tabs" : "shell"}>
      {/* Before the screen, so its own layers (a form, an unsaved note) sit above this one. */}
      {top && <StackBack onBack={pop} />}
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
      <ChunkBoundary
        key={top ? `${String(nav.stack.length)}:${top.name}` : nav.tab}
        onBack={top ? pop : undefined}
      >
        <Suspense fallback={busy}>{shown}</Suspense>
      </ChunkBoundary>
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

function Pushed({ screen, me, onBack }: { screen: Screen; me: Me; onBack: () => void }) {
  switch (screen.name) {
    case "settings":
      return <Settings me={me} onBack={onBack} focus={screen.focus} />;
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
