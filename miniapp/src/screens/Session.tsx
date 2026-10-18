import { Localized } from "@fluent/react";
import { useEffect, useRef, type ReactNode } from "react";

import { ApiError, useMe, useReportDeviceTimezone, type Me } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import type { Locale } from "../i18n/negotiate";

interface SessionProps {
  /** From the launch params, until `/me` answers (no flash of the wrong language). */
  launchLocale: Locale;
  children: (me: Me | undefined) => ReactNode;
}

/** Resolves the account (created on first open, ID-01), switches to its locale, and reports
 * the device time zone once if the account has none. */
export function Session({ launchLocale, children }: SessionProps) {
  const me = useMe();
  const locale = me.data?.locale ?? launchLocale;
  useReportTimezoneOnce(me.data);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const expired = me.error instanceof ApiError && me.error.status === 401;
  return (
    <L10nProvider locale={locale}>
      {expired ? (
        <main className="screen">
          <Localized id="session-expired">
            <p className="hint" role="alert" />
          </Localized>
        </main>
      ) : (
        children(me.data)
      )}
    </L10nProvider>
  );
}

function useReportTimezoneOnce(me: Me | undefined) {
  const { mutate } = useReportDeviceTimezone();
  const reported = useRef(false);
  useEffect(() => {
    if (!me || me.timezone !== null || reported.current) return;
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    // UTC usually means a misconfigured device, not a place (the server ignores it too).
    if (!zone || zone === "UTC" || zone === "Etc/UTC") return;
    reported.current = true;
    mutate(zone); // fire and forget: a failure is retried on the next open
  }, [me, mutate]);
}
