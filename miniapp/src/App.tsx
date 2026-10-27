import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Localized } from "@fluent/react";
import { lazy, Suspense, useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { isAccountDeleted, onAccountDeleted } from "./api/client";
import { L10nProvider } from "./i18n/L10nProvider";
import type { Locale } from "./i18n/negotiate";
import { AccountDeleted } from "./screens/AccountDeleted";
import { Home } from "./screens/Home";
import { NotInTelegram } from "./screens/NotInTelegram";
import { MoonCard } from "./screens/MoonCard";
import { TravelPrompt } from "./screens/settings/TravelPrompt";
import { Session } from "./screens/Session";
import { TodayCard } from "./screens/TodayCard";
import { markReady, useSettingsButton } from "./telegram";

// The stats screen (ST-01..03) is its own chunk: Home's first load doesn't pay for it.
const Stats = lazy(() => import("./screens/stats/Stats"));
const Settings = lazy(() => import("./screens/settings/Settings"));
const Progression = lazy(() => import("./screens/progression/Progression"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

interface AppProps {
  locale: Locale;
  firstName: string | null;
  inTelegram: boolean;
}

export function App({ locale, firstName, inTelegram }: AppProps) {
  const [showDetails, setShowDetails] = useState(import.meta.env.DEV);
  const [view, setView] = useState<"home" | "stats" | "settings" | "day-off" | "progression">(
    "home",
  );
  const home = useCallback(() => {
    setView("home");
  }, []);
  const settings = useCallback(() => {
    setView("settings");
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
        <NotInTelegram />
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
          ) : me && (view === "settings" || view === "day-off") ? (
            <Suspense fallback={<main className="screen" aria-busy="true" />}>
              <Settings
                me={me}
                onBack={view === "day-off" ? stats : home}
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
              {me && <TravelPrompt zone={me.timezone} locale={me.locale} />}
              {me && <TodayCard zone={me.timezone} locale={me.locale} />}
              {me && (
                <Localized id="stats-open">
                  <button
                    type="button"
                    className="row-button"
                    onClick={() => {
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
                    onClick={() => {
                      setView("progression");
                    }}
                  />
                </Localized>
              )}
              {me && <MoonCard locale={me.locale} />}
              {me && (
                <Localized id="settings-open">
                  <button type="button" className="row-button" onClick={settings} />
                </Localized>
              )}
            </Home>
          )
        }
      </Session>
    </QueryClientProvider>
  );
}
