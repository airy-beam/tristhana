import { Localized } from "@fluent/react";
import { useCallback, type ReactNode } from "react";

import type { Me } from "../../../api/client";
import { backButtonAvailable } from "../../../telegram";

import "../settingsCopy";
import "../settings.css";

/** What every Settings page gets: the account as it is cached (a saved value shows at once),
 * where Back leads (the five rows, or out of Settings for a page opened directly), and a way to
 * another page (Reminders without a zone → My city). */
export interface PageProps {
  me: Me;
  onBack: () => void;
  /** Settings gives it; a page mounted on its own has no other page to go to. */
  onOpen?: ((page: "city") => void) | undefined;
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

/** The frame of a Settings page (UI-06 stage 3): a heading that takes the focus when the page
 * opens, and a back link where Telegram has no Back button. Telegram's Back is Settings' own
 * layer, so it also works while a page's chunk loads. */
export function Page({ title, onBack, busy, children }: Props) {
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
