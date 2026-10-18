import { Localized, useLocalization } from "@fluent/react";
import { useCallback, useState } from "react";

import { useHealth } from "../api/client";
import { haptics, useMainButton } from "../telegram";
import { useLongPress } from "./useLongPress";

interface HomeProps {
  firstName: string | null;
  /** Server version/commit: always in dev, after a long press in production. */
  showDetails: boolean;
  onGreetingLongPress?: () => void;
}

export function Home({ firstName, showDetails, onGreetingLongPress }: HomeProps) {
  const { l10n } = useLocalization();
  const health = useHealth();
  const { refetch } = health;
  const pressHandlers = useLongPress(onGreetingLongPress);
  // After the main button is used, show its result even when server details are hidden.
  const [checked, setChecked] = useState(false);

  const checkConnection = useCallback(() => {
    haptics.impact("light"); // feedback before the network call
    setChecked(true);
    void refetch().then((result) => {
      haptics.notify(result.isError ? "error" : "success");
    });
  }, [refetch]);
  useMainButton(l10n.getString("home-check-connection"), checkConnection, health.isFetching);

  return (
    <main className="screen">
      {firstName ? (
        <Localized id="home-greeting" vars={{ name: firstName }}>
          <h1 {...pressHandlers} />
        </Localized>
      ) : (
        <Localized id="home-greeting-anon">
          <h1 {...pressHandlers} />
        </Localized>
      )}
      <Localized id="home-subtitle">
        <p className="hint" />
      </Localized>
      {health.isError ? (
        <Localized id="home-server-offline">
          <p className="status" role="status" />
        </Localized>
      ) : showDetails ? (
        health.data ? (
          <Localized
            id="home-server-status"
            vars={{ version: health.data.version, commit: health.data.commit.slice(0, 7) }}
          >
            <p className="status" role="status" />
          </Localized>
        ) : (
          <Localized id="home-server-loading">
            <p className="status" role="status" />
          </Localized>
        )
      ) : checked && health.isSuccess && !health.isFetching ? (
        <Localized id="home-connection-ok">
          <p className="status" role="status" />
        </Localized>
      ) : null}
    </main>
  );
}
