import { Localized } from "@fluent/react";

import { guideUrl } from "../guide";
import type { Locale } from "../i18n/negotiate";

export function NotInTelegram({ locale }: { locale: Locale }) {
  return (
    <main className="screen">
      <Localized id="not-in-telegram">
        <p className="hint" />
      </Localized>
      <Localized id="guide-open">
        <a className="link" href={guideUrl(locale)} />
      </Localized>
    </main>
  );
}
