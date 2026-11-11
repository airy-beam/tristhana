import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Localized } from "@fluent/react";
import { lazy, Suspense, useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { isAccountDeleted, onAccountDeleted, useLinks, useMyShalas } from "./api/client";
import { L10nProvider } from "./i18n/L10nProvider";
import type { Locale } from "./i18n/negotiate";
import { AccountDeleted } from "./screens/AccountDeleted";
import { Home } from "./screens/Home";
import { NotInTelegram } from "./screens/NotInTelegram";
import { MoonCard } from "./screens/MoonCard";
import { TravelPrompt } from "./screens/settings/TravelPrompt";
import { Session } from "./screens/Session";
import { markTourSeen } from "./screens/onboard";
import { TodayCard } from "./screens/TodayCard";
import { TourOffer } from "./screens/tour/TourOffer";
import { useTour } from "./screens/tour/useTour";
import { markReady, useSettingsButton } from "./telegram";

// The stats screen (ST-01..03) is its own chunk: Home's first load doesn't pay for it.
const Stats = lazy(() => import("./screens/stats/Stats"));
const Settings = lazy(() => import("./screens/settings/Settings"));
const Progression = lazy(() => import("./screens/progression/Progression"));
const Links = lazy(() => import("./screens/settings/Links"));
const Students = lazy(() => import("./screens/teachers/Students"));
const MySchedule = lazy(() => import("./screens/shalas/MySchedule"));
const Announcements = lazy(() => import("./screens/announcements/Announcements"));
const DirectoryListing = lazy(() => import("./screens/settings/DirectoryListing"));

/** NT-03: the bot's `[📣 Announce]` opens the app with `?open=announce` (and `&shala=<id>`),
 * read once at launch. */
function launchAnnounce(): { shala: string | null } | null {
  const query = new URLSearchParams(window.location.search);
  if (query.get("open") !== "announce") return null;
  const shala = query.get("shala");
  return { shala: shala && /^[0-9a-f-]{36}$/i.test(shala) ? shala : null };
}

/** ID-05: the bot's `[Open the app]` on the directory-line screen opens with `?open=listing`. */
function launchListing(): boolean {
  return new URLSearchParams(window.location.search).get("open") === "listing";
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

interface AppProps {
  locale: Locale;
  firstName: string | null;
  inTelegram: boolean;
}

function StudentsRow({ onOpen }: { onOpen: () => void }) {
  const { data } = useLinks();
  if (!data?.students.length) return null;
  return (
    <Localized id="link-students-open">
      <button type="button" className="row-button" onClick={onOpen} />
    </Localized>
  );
}

/** Anyone in a shala (SC-03): every shala's week, in my zone. */
function MyScheduleRow({ onOpen }: { onOpen: () => void }) {
  const { data } = useMyShalas();
  if (!data?.length) return null;
  return (
    <Localized id="my-schedule-open">
      <button type="button" className="row-button" onClick={onOpen} />
    </Localized>
  );
}

export function App({ locale, firstName, inTelegram }: AppProps) {
  const [showDetails, setShowDetails] = useState(import.meta.env.DEV);
  const [view, setView] = useState<
    | "home"
    | "stats"
    | "settings"
    | "day-off"
    | "progression"
    | "links"
    | "students"
    | "links-students"
    | "my-schedule"
    | "announce"
    | "listing"
  >(() => (launchAnnounce() ? "announce" : launchListing() ? "listing" : "home"));
  const [announceTo] = useState(() => launchAnnounce()?.shala ?? null);
  const home = useCallback(() => {
    setView("home");
  }, []);
  const { Tour, start: startTour, close: closeTour } = useTour();
  const settings = useCallback(() => {
    closeTour(); // Telegram's ⋯ item works during the tour too
    setView("settings");
  }, [closeTour]);
  const tour = useCallback(() => {
    markTourSeen(); // taken from Settings: no offer for it afterwards
    setView("home");
    startTour();
  }, [startTour]);
  const links = useCallback(() => {
    setView("links");
  }, []);
  const stats = useCallback(() => {
    setView("stats"); // back from the day off opened on the stats screen
  }, []);
  const dayOff = useCallback(() => {
    setView("day-off"); // Settings, scrolled to the day off (PR-09)
  }, []);
  // Telegram's ⋯ menu "Settings" item (ID-06).
  useSettingsButton(settings);
  // ST-09: after deleting the account only the Done screen renders (no more requests).
  const deleted = useSyncExternalStore(onAccountDeleted, isAccountDeleted);
  useEffect(() => {
    // After the first commit, so Telegram drops its placeholder once something is painted.
    if (inTelegram) markReady();
  }, [inTelegram]);
  if (deleted) {
    return (
      <L10nProvider locale={locale}>
        <AccountDeleted />
      </L10nProvider>
    );
  }
  if (!inTelegram) {
    return (
      <L10nProvider locale={locale}>
        <NotInTelegram locale={locale} />
      </L10nProvider>
    );
  }
  return (
    <QueryClientProvider client={queryClient}>
      <Session launchLocale={locale}>
        {(me) =>
          me && view === "stats" ? (
            <Suspense fallback={<main className="screen" aria-busy="true" />}>
              <Stats locale={me.locale} zone={me.timezone} onBack={home} onDayOff={dayOff} />
            </Suspense>
          ) : me && view === "progression" ? (
            <Suspense fallback={<main className="screen" aria-busy="true" />}>
              <Progression locale={me.locale} onBack={home} />
            </Suspense>
          ) : me && view === "links" ? (
            <Suspense fallback={<main className="screen" aria-busy="true" />}>
              <Links
                onBack={settings}
                onStudents={() => {
                  setView("links-students");
                }}
              />
            </Suspense>
          ) : me && (view === "students" || view === "links-students") ? (
            <Suspense fallback={<main className="screen" aria-busy="true" />}>
              <Students locale={me.locale} onBack={view === "students" ? home : links} />
            </Suspense>
          ) : me && view === "announce" ? (
            <Suspense fallback={<main className="screen" aria-busy="true" />}>
              <Announcements
                mode={{ view: "compose", shala: announceTo }}
                locale={me.locale}
                onBack={home}
              />
            </Suspense>
          ) : me && view === "listing" ? (
            <Suspense fallback={<main className="screen" aria-busy="true" />}>
              <DirectoryListing locale={me.locale} onBack={home} />
            </Suspense>
          ) : me && view === "my-schedule" ? (
            <Suspense fallback={<main className="screen" aria-busy="true" />}>
              <MySchedule locale={me.locale} onBack={home} />
            </Suspense>
          ) : me && (view === "settings" || view === "day-off") ? (
            <Suspense fallback={<main className="screen" aria-busy="true" />}>
              <Settings
                me={me}
                onBack={view === "day-off" ? stats : home}
                onTour={tour}
                onLinks={links}
                focus={view === "day-off" ? "day-off" : undefined}
              />
            </Suspense>
          ) : (
            <Home
              firstName={me ? me.display_name : firstName}
              showDetails={showDetails}
              onGreetingLongPress={() => {
                setShowDetails(true);
              }}
            >
              {me && <TravelPrompt zone={me.timezone} locale={me.locale} home={me.home_city} />}
              {me && <TodayCard zone={me.timezone} locale={me.locale} />}
              {me && <TourOffer zone={me.timezone} onStart={startTour} />}
              {me && (
                <Localized id="stats-open">
                  <button
                    type="button"
                    className="row-button"
                    data-tour="stats"
                    onClick={() => {
                      closeTour(); // still loading: don't open it on the way back
                      setView("stats");
                    }}
                  />
                </Localized>
              )}
              {me && (
                <Localized id="progression-open">
                  <button
                    type="button"
                    className="row-button"
                    data-tour="asanas"
                    onClick={() => {
                      closeTour();
                      setView("progression");
                    }}
                  />
                </Localized>
              )}
              {me && (
                <StudentsRow
                  onOpen={() => {
                    closeTour();
                    setView("students");
                  }}
                />
              )}
              {me && (
                <MyScheduleRow
                  onOpen={() => {
                    closeTour();
                    setView("my-schedule");
                  }}
                />
              )}
              {me && <MoonCard locale={me.locale} />}
              {me && (
                <Localized id="settings-open">
                  <button
                    type="button"
                    className="row-button"
                    data-tour="settings"
                    onClick={settings}
                  />
                </Localized>
              )}
              {me && Tour && <Tour onExit={closeTour} />}
            </Home>
          )
        }
      </Session>
    </QueryClientProvider>
  );
}
