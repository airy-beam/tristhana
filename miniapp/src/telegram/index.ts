// The only place that talks to the Telegram SDK. Components use these wrappers, which are
// no-ops when a feature isn't supported (older clients, or a browser in dev).
import {
  backButton,
  closingBehavior,
  settingsButton,
  hapticFeedback,
  init,
  isTMA,
  mainButton,
  miniApp,
  retrieveLaunchParams,
  retrieveRawInitData,
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
  settingsButton.mount.ifAvailable();
  mainButton.mount.ifAvailable();
  closingBehavior.mount.ifAvailable();
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

/** Telegram's ⋯ menu "Settings" item opens `onOpen` while mounted (ID-06). */
export function useSettingsButton(onOpen: () => void): void {
  useEffect(() => {
    if (!settingsButton.show.isAvailable()) return;
    settingsButton.show();
    const off = settingsButton.onClick(onOpen);
    return () => {
      off();
    };
  }, [onOpen]);
}

export function backButtonAvailable(): boolean {
  return backButton.show.isAvailable();
}

/** Shows Telegram's Back button while mounted; `onBack` runs when it's pressed. */
export function useBackButton(onBack: () => void): void {
  useEffect(() => {
    if (!backButton.show.isAvailable()) return;
    backButton.show();
    const off = backButton.onClick(onBack);
    return () => {
      off();
      backButton.hide.ifAvailable();
    };
  }, [onBack]);
}

/** Tell Telegram the app is ready (hides its loading placeholder). */
export function markReady(): void {
  miniApp.ready.ifAvailable();
}

/** Unverified, for the first paint only; the backend's `/me` is the source of truth. */
export function launchUser(): LaunchUser {
  const user = retrieveLaunchParams().tgWebAppData?.user;
  return { firstName: user?.first_name ?? null, languageCode: user?.language_code ?? null };
}

/** The signed initData string, sent to the API on every request (ADR-0015). */
export function rawInitData(): string | undefined {
  try {
    return retrieveRawInitData();
  } catch {
    return undefined; // outside Telegram
  }
}

/** Ask before the app closes (unsaved diary text, PR-07); a no-op where unsupported. */
export function enableClosingConfirmation(): void {
  closingBehavior.enableConfirmation.ifAvailable();
}

export function disableClosingConfirmation(): void {
  closingBehavior.disableConfirmation.ifAvailable();
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
export function useMainButton(
  text: string,
  onClick: () => void,
  loading = false,
  visible = true,
): void {
  useEffect(() => {
    if (!mainButton.setParams.isAvailable()) return;
    if (!visible) {
      mainButton.setParams({ isVisible: false });
      return;
    }
    mainButton.setParams({ text, isVisible: true, isEnabled: true });
    const off = mainButton.onClick(onClick);
    return () => {
      off();
      mainButton.setParams.ifAvailable({ isVisible: false });
    };
  }, [text, onClick, visible]);

  useEffect(() => {
    mainButton.setParams.ifAvailable({ isLoaderVisible: loading, isEnabled: !loading });
  }, [loading]);
}
