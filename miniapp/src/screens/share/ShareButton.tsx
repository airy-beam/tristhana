// ST-07: the small "Share" button (initial bundle); the sheet itself is a lazy chunk.
import { useLocalization } from "@fluent/react";
import { lazy, Suspense, useState } from "react";

import type { ShareSubject } from "../../api/client";
import { haptics } from "../../telegram";

const ShareSheet = lazy(() => import("./ShareSheet"));

/** `label` names what is shared ("Share: 2026") when a screen has several Share buttons. */
export function ShareButton({ subject, label }: { subject: ShareSubject; label?: string }) {
  const { l10n } = useLocalization();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="link share-open"
        aria-label={label}
        onClick={(e) => {
          e.stopPropagation();
          haptics.impact("light");
          setOpen(true);
        }}
      >
        {l10n.getString("share-open")}
      </button>
      {open && (
        <Suspense fallback={null}>
          <ShareSheet
            subject={subject}
            onClose={() => {
              setOpen(false);
            }}
          />
        </Suspense>
      )}
    </>
  );
}
