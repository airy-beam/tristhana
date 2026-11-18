import { Localized } from "@fluent/react";

import { guideUrl } from "../guide";
import { haptics, openLink } from "../telegram";

/** The quiet "📖 Guide" row (UI-05): the guide page about this screen, in the person's
 * language (UI-06 stage 6). `page` is the path under the language root, e.g. `staff/classes/`. */
export function GuideLink({ locale, page }: { locale: string; page: string }) {
  return (
    <Localized id="guide-open">
      <button
        type="button"
        className="link guide"
        onClick={() => {
          haptics.selection();
          openLink(guideUrl(locale, page));
        }}
      />
    </Localized>
  );
}
