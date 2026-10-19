import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Localized } from "@fluent/react";
import { lazy, Suspense, useCallback, useEffect, useState } from "react";

import { L10nProvider } from "./i18n/L10nProvider";
import type { Locale } from "./i18n/negotiate";
import { Home } from "./screens/Home";
import { NotInTelegram } from "./screens/NotInTelegram";
import { MoonCard } from "./screens/MoonCard";
import { PracticeReminderCard } from "./screens/PracticeReminderCard";
import { Session } from "./screens/Session";
import { TodayCard } from "./screens/TodayCard";
import { markReady } from "./telegram";

// The stats screen (ST-01..03) is its own chunk: Home's first load doesn't pay for it.
const Stats = lazy(() => import("./screens/stats/Stats"));

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
  const [view, setView] = useState<"home" | "stats">("home");
  const home = useCallback(() => {
    setView("home");
  }, []);
  useEffect(() => {
    // After the first commit, so Telegram drops its placeholder once something is painted.
    if (inTelegram) markReady();
  }, [inTelegram]);
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
              <Stats locale={me.locale} zone={me.timezone} onBack={home} />
            </Suspense>
          ) : (
            <Home
              firstName={me ? me.display_name : firstName}
              showDetails={showDetails}
              onGreetingLongPress={() => {
                setShowDetails(true);
              }}
            >
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
              {me && <MoonCard zone={me.timezone} locale={me.locale} />}
              {me && <PracticeReminderCard zone={me.timezone} />}
            </Home>
          )
        }
      </Session>
    </QueryClientProvider>
  );
}
