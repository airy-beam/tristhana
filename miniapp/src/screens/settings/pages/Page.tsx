import { Localized } from "@fluent/react";
import { useCallback, type ReactNode } from "react";

import type { Me } from "../../../api/client";
import { backButtonAvailable, useBackButton } from "../../../telegram";

import "../settingsCopy";
import "../settings.css";

/** What every Settings page gets: the account as it is cached (a saved value shows at once),
 * and where Back leads (the five rows, or out of Settings for a page opened directly). */
export interface PageProps {
  me: Me;
  onBack: () => void;
}

/** The id of the page's heading, for a page whose one group of choices it names. */
export const PAGE_TITLE = "settings-page";

interface Props {
  /** The heading's message. */
  title: string;
  onBack: () => void;
  /** While what the page shows is still loading. */
  busy?: boolean | undefined;
  children: ReactNode;
}

/** The frame of a Settings page (UI-06 stage 3): its own Back layer over the five rows, and a
 * heading that takes the focus when the page opens. */
export function Page({ title, onBack, busy, children }: Props) {
  useBackButton(onBack);
  const heading = useCallback((element: HTMLHeadingElement | null) => {
    element?.focus({ preventScroll: true });
  }, []);
  return (
    <main className="screen settings" aria-busy={busy ? true : undefined}>
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      <Localized id={title}>
        <h1 id={PAGE_TITLE} ref={heading} tabIndex={-1} />
      </Localized>
      {children}
    </main>
  );
}

/** "Couldn't save": the same line under every page's controls. */
export function SaveFailed({ when }: { when: boolean }) {
  if (!when) return null;
  return (
    <Localized id="settings-save-failed">
      <p className="status" role="alert" />
    </Localized>
  );
}
