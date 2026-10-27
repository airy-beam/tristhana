import { Localized } from "@fluent/react";

import { closeApp } from "../telegram";

/** Shown after "Delete everything" (ST-09): nothing else renders, so no request goes out. */
export function AccountDeleted() {
  return (
    <main className="screen">
      <Localized id="delete-done-app">
        <p role="status" />
      </Localized>
      <Localized id="delete-close">
        <button type="button" className="row-button" onClick={closeApp} />
      </Localized>
    </main>
  );
}
