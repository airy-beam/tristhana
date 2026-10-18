import { LocalizationProvider, ReactLocalization } from "@fluent/react";
import { useMemo, type ReactNode } from "react";

import { bundleFor } from "./bundles";
import { DEFAULT_LOCALE, type Locale } from "./negotiate";

export function L10nProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  const l10n = useMemo(() => {
    // Missing keys in the user's locale fall back to English.
    const chain = locale === DEFAULT_LOCALE ? [locale] : [locale, DEFAULT_LOCALE];
    return new ReactLocalization(chain.map(bundleFor));
  }, [locale]);
  return <LocalizationProvider l10n={l10n}>{children}</LocalizationProvider>;
}
