import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { L10nProvider } from "./i18n/L10nProvider";
import type { Locale } from "./i18n/negotiate";
import { Home } from "./screens/Home";
import { NotInTelegram } from "./screens/NotInTelegram";
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
    document.documentElement.lang = locale;
  }, [locale]);
  useEffect(() => {
    // After the first commit, so Telegram drops its placeholder once something is painted.
    if (inTelegram) markReady();
  }, [inTelegram]);
  return (
    <L10nProvider locale={locale}>
      {inTelegram ? (
        <QueryClientProvider client={queryClient}>
          <Home
            firstName={firstName}
            showDetails={showDetails}
            onGreetingLongPress={() => {
              setShowDetails(true);
            }}
          />
        </QueryClientProvider>
      ) : (
        <NotInTelegram />
      )}
    </L10nProvider>
  );
}
