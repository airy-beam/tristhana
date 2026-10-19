import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { L10nProvider } from "./i18n/L10nProvider";
import type { Locale } from "./i18n/negotiate";
import { Home } from "./screens/Home";
import { NotInTelegram } from "./screens/NotInTelegram";
import { MoonCard } from "./screens/MoonCard";
import { PracticeReminderCard } from "./screens/PracticeReminderCard";
import { Session } from "./screens/Session";
import { TodayCard } from "./screens/TodayCard";
import { markReady } from "./telegram";

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
        {(me) => (
          <Home
            firstName={me ? me.display_name : firstName}
            showDetails={showDetails}
            onGreetingLongPress={() => {
              setShowDetails(true);
            }}
          >
            {me && <TodayCard zone={me.timezone} locale={me.locale} />}
            {me && <MoonCard zone={me.timezone} locale={me.locale} />}
            {me && <PracticeReminderCard zone={me.timezone} />}
          </Home>
        )}
      </Session>
    </QueryClientProvider>
  );
}
