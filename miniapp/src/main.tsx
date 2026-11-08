import "./theme/tokens.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { bundleFor, format } from "./i18n/bundles";
import { negotiateLocale } from "./i18n/negotiate";
import { hasTelegramBridge, initTelegram, isInTelegram, launchUser } from "./telegram";

async function start(): Promise<void> {
  // Not `!isInTelegram()`: after a reload the SDK finds the mock's saved launch params and
  // says yes, but nothing would answer its events (UnknownEnvError at init).
  if (import.meta.env.DEV && !hasTelegramBridge()) {
    const { mockTelegram } = await import("./telegram/mock");
    await mockTelegram();
  }

  const inTelegram = isInTelegram();
  let user = {
    firstName: null as string | null,
    languageCode: navigator.language as string | null,
  };
  if (inTelegram) {
    initTelegram();
    user = launchUser();
  }

  const root = document.getElementById("root");
  if (!root) throw new Error("#root missing");
  createRoot(root).render(
    <StrictMode>
      <App
        locale={negotiateLocale(user.languageCode)}
        firstName={user.firstName}
        inTelegram={inTelegram}
      />
    </StrictMode>,
  );
}

start().catch((error: unknown) => {
  // Keep something on screen rather than a blank page; details go to the console only.
  console.error("startup failed", error);
  const locale = negotiateLocale(navigator.language);
  document.body.textContent = format(bundleFor(locale), "startup-failed");
});
