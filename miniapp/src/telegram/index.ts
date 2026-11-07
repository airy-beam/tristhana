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
  openTelegramLink as sdkOpenTelegramLink,
  popup,
  requestWriteAccess,
  retrieveLaunchParams,
  retrieveRawInitData,
  themeParams,
  viewport,
} from "@telegram-apps/sdk-react";
import { useEffect, useRef } from "react";

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
  followTelegramColorScheme();
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

/** Native controls (selects, date pickers, scrollbars) follow Telegram's theme, not the
 * phone's: the two can differ. Stays in sync when the theme changes while the app is open. */
function followTelegramColorScheme(): void {
  const apply = (dark: boolean) => {
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  };
  apply(themeParams.isDark());
  themeParams.isDark.sub(apply);
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

// One Back button, several layers: the newest one (a day editor over its screen) gets the press.
const backLayers: { current: () => void }[] = [];
let stopListening: (() => void) | undefined;

/** Shows Telegram's Back button while mounted and `enabled`; `onBack` runs when it's pressed,
 * unless a layer opened later is still there (that one closes first). */
export function useBackButton(onBack: () => void, enabled = true): void {
  const layer = useRef(onBack);
  useEffect(() => {
    layer.current = onBack;
  }, [onBack]);
  useEffect(() => {
    if (!enabled || !backButton.show.isAvailable()) return;
    backLayers.push(layer);
    if (backLayers.length === 1) {
      backButton.show();
      stopListening = backButton.onClick(() => {
        backLayers.at(-1)?.current();
      });
    }
    return () => {
      backLayers.splice(backLayers.indexOf(layer), 1);
      if (backLayers.length === 0) {
        stopListening?.();
        backButton.hide.ifAvailable();
      }
    };
  }, [enabled]);
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
  selection: (): void => {
    hapticFeedback.selectionChanged.ifAvailable();
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
    mainButton.setParams({ text, isVisible: true });
    const off = mainButton.onClick(onClick);
    return () => {
      off();
      mainButton.setParams.ifAvailable({ isVisible: false });
    };
  }, [text, onClick, visible]);

  // Also after showing it: a new label mid-load must not turn the button back on.
  useEffect(() => {
    mainButton.setParams.ifAvailable({ isLoaderVisible: loading, isEnabled: !loading });
  }, [loading, text, visible]);
}

/** Telegram's native confirm popup with a destructive button (ST-09 delete); resolves true
 * only for that button. Outside Telegram (dev), the browser's confirm. */
export async function confirmDestructive(
  message: string,
  confirm: string,
  cancel: string,
): Promise<boolean> {
  if (!popup.show.isAvailable()) return window.confirm(message);
  const id = await popup.show({
    message,
    buttons: [
      { id: "confirm", type: "destructive", text: confirm },
      { id: "cancel", type: "default", text: cancel },
    ],
  });
  return id === "confirm";
}

/** Asks Telegram to let the bot write to this person (ST-09: the export is a bot message;
 * someone who opened the app by link may never have started the bot). True = allowed. */
export async function allowBotMessages(): Promise<boolean> {
  if (!requestWriteAccess.isAvailable()) return false;
  try {
    return (await requestWriteAccess()) === "allowed";
  } catch {
    return false;
  }
}

/** Closes the Mini App (after the account was deleted); a no-op where unsupported. */
export function closeApp(): void {
  miniApp.close.ifAvailable();
}

export function openTelegramLink(url: string): void {
  sdkOpenTelegramLink.ifAvailable(url);
}
