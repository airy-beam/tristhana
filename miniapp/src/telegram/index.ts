// The only place that talks to the Telegram SDK. Components use these wrappers, which are
// no-ops when a feature isn't supported (older clients, or a browser in dev).
import {
  backButton,
  hapticFeedback,
  init,
  isTMA,
  mainButton,
  miniApp,
  retrieveLaunchParams,
  themeParams,
  viewport,
} from "@telegram-apps/sdk-react";
import { useEffect } from "react";

export interface LaunchUser {
  firstName: string | null;
  languageCode: string | null;
}

export function isInTelegram(): boolean {
  return isTMA();
}

/** Mounts the SDK components and binds theme/viewport CSS variables. Call once. */
export function initTelegram(): void {
  init();
  backButton.mount.ifAvailable();
  mainButton.mount.ifAvailable();
  if (miniApp.mountSync.isAvailable()) {
    miniApp.mountSync(); // also mounts themeParams
  } else {
    themeParams.mountSync.ifAvailable(); // older clients without miniApp support
  }
  themeParams.bindCssVars.ifAvailable();
  if (viewport.mount.isAvailable()) {
    viewport
      .mount()
      .then(() => {
        viewport.bindCssVars.ifAvailable();
        viewport.expand.ifAvailable();
      })
      .catch(() => {
        // Some clients time out here; the CSS has viewport fallbacks.
      });
  }
}

/** Tell Telegram the app is ready (hides its loading placeholder). */
export function markReady(): void {
  miniApp.ready.ifAvailable();
}

/** Unverified, for display only; never sent to the backend as identity (Phase 1: initData). */
export function launchUser(): LaunchUser {
  const user = retrieveLaunchParams().tgWebAppData?.user;
  return { firstName: user?.first_name ?? null, languageCode: user?.language_code ?? null };
}

export const haptics = {
  impact: (style: "light" | "medium" | "heavy" = "light"): void => {
    hapticFeedback.impactOccurred.ifAvailable(style);
  },
  notify: (type: "success" | "error" | "warning"): void => {
    hapticFeedback.notificationOccurred.ifAvailable(type);
  },
};

/** Shows Telegram's main button with `text` while the component is mounted; `loading` shows
 * its spinner and disables it. */
export function useMainButton(text: string, onClick: () => void, loading = false): void {
  useEffect(() => {
    if (!mainButton.setParams.isAvailable()) return;
    mainButton.setParams({ text, isVisible: true, isEnabled: true });
    const off = mainButton.onClick(onClick);
    return () => {
      off();
      mainButton.setParams.ifAvailable({ isVisible: false });
    };
  }, [text, onClick]);

  useEffect(() => {
    mainButton.setParams.ifAvailable({ isLoaderVisible: loading, isEnabled: !loading });
  }, [loading]);
}
