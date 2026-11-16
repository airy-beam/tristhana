import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";

import { isAccountDeleted, onAccountDeleted } from "./api/client";
import { L10nProvider } from "./i18n/L10nProvider";
import type { Locale } from "./i18n/negotiate";
import { AccountDeleted } from "./screens/AccountDeleted";
import { NotInTelegram } from "./screens/NotInTelegram";
import { Session } from "./screens/Session";
import { Shell } from "./shell/Shell";
import { markReady } from "./telegram";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

interface AppProps {
  locale: Locale;
  firstName: string | null;
  inTelegram: boolean;
}

/** Providers, the three states with no shell (account deleted, not in Telegram, session),
 * then the shell (UI-06 stage 2): tabs, stack and launch links live in `shell/`. */
export function App({ locale, firstName, inTelegram }: AppProps) {
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
      <Session launchLocale={locale}>{(me) => <Shell me={me} firstName={firstName} />}</Session>
    </QueryClientProvider>
  );
}
