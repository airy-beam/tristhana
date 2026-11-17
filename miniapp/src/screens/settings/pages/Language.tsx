import { Localized } from "@fluent/react";

import { usePatchMe } from "../../../api/client";
import type { Locale } from "../../../i18n/negotiate";
import { haptics } from "../../../telegram";
import { Page, PAGE_TITLE, SaveFailed, type PageProps } from "./Page";

const LANGUAGES: [Locale | null, string][] = [
  [null, "language-auto"],
  ["en", "language-en"],
  ["ru", "language-ru"],
];

/** Settings → Language (ID-06): three choices, one per row; a tap saves, and the whole app
 * answers in that language. */
export default function Language({ me, onBack }: PageProps) {
  const patch = usePatchMe();
  const current = me.locale_from_telegram ? null : me.locale;
  return (
    <Page title="settings-language" onBack={onBack}>
      <div className="card list" role="group" aria-labelledby={PAGE_TITLE}>
        {LANGUAGES.map(([code, key]) => (
          <Localized key={key} id={key}>
            <button
              type="button"
              className="lrow srow"
              aria-pressed={code === current}
              onClick={() => {
                haptics.impact("light");
                patch.mutate({ locale: code });
              }}
            />
          </Localized>
        ))}
      </div>
      <SaveFailed when={patch.isError} />
    </Page>
  );
}
