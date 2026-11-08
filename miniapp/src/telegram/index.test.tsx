import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => {
  const clicks = new Set<() => void>();
  const fn = () => Object.assign(vi.fn(), { isAvailable: () => true, ifAvailable: vi.fn() });
  const show = fn();
  const hide = fn();
  const setParams = fn();
  const isDark = Object.assign(
    vi.fn(() => true),
    { sub: vi.fn() },
  );
  return { clicks, show, hide, setParams, isDark };
});

vi.mock("@telegram-apps/sdk-react", () => {
  const off = { ifAvailable: vi.fn(), isAvailable: () => false };
  return {
    backButton: {
      mount: off,
      show: sdk.show,
      hide: sdk.hide,
      onClick: (listener: () => void) => {
        sdk.clicks.add(listener);
        return () => sdk.clicks.delete(listener);
      },
    },
    closingBehavior: { mount: off },
    settingsButton: { mount: off },
    hapticFeedback: {},
    init: vi.fn(),
    isTMA: () => true,
    mainButton: { mount: off, setParams: sdk.setParams, onClick: () => vi.fn() },
    miniApp: { mountSync: off },
    popup: {},
    requestWriteAccess: {},
    retrieveLaunchParams: vi.fn(),
    retrieveRawInitData: vi.fn(),
    themeParams: { mountSync: off, bindCssVars: off, isDark: sdk.isDark },
    viewport: { mount: off },
  };
});

import { initTelegram, useBackButton, useMainButton } from ".";

function press() {
  act(() => {
    sdk.clicks.forEach((listener) => {
      listener();
    });
  });
}

function Layer({ onBack, enabled }: { onBack: () => void; enabled?: boolean }) {
  useBackButton(onBack, enabled);
  return null;
}

function Screen({ onBack, editor }: { onBack: () => void; editor?: () => void }) {
  return (
    <>
      <Layer onBack={onBack} />
      {editor && <Layer onBack={editor} />}
    </>
  );
}

describe("useBackButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(cleanup);

  it("closes the newest layer first, then the screen", () => {
    const screen = vi.fn();
    const editor = vi.fn();
    const { rerender } = render(<Screen onBack={screen} />);
    rerender(<Screen onBack={screen} editor={editor} />);

    press();
    expect(editor).toHaveBeenCalledOnce();
    expect(screen).not.toHaveBeenCalled();

    rerender(<Screen onBack={screen} />);
    press();
    expect(screen).toHaveBeenCalledOnce();
    expect(sdk.hide.ifAvailable).not.toHaveBeenCalled();
  });

  it("calls the newest handler without changing the layer order", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = render(<Layer onBack={first} />);
    rerender(<Layer onBack={second} />);

    press();
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledOnce();
  });

  it("skips a disabled layer", () => {
    const screen = vi.fn();
    const form = vi.fn();
    render(
      <>
        <Layer onBack={screen} />
        <Layer onBack={form} enabled={false} />
      </>,
    );

    press();
    expect(form).not.toHaveBeenCalled();
    expect(screen).toHaveBeenCalledOnce();
  });

  it("hides the button and stops listening after the last layer", () => {
    const { unmount } = render(<Layer onBack={vi.fn()} />);
    expect(sdk.show).toHaveBeenCalledOnce();

    unmount();
    expect(sdk.hide.ifAvailable).toHaveBeenCalledOnce();
    expect(sdk.clicks.size).toBe(0);
  });
});

describe("useMainButton", () => {
  function Main({ text, loading }: { text: string; loading: boolean }) {
    useMainButton(text, vi.fn(), loading);
    return null;
  }
  afterEach(cleanup);

  it("stays disabled when the label changes mid-load", () => {
    const { rerender } = render(<Main text="One" loading />);
    sdk.setParams.ifAvailable.mockClear();
    sdk.setParams.mockClear();

    rerender(<Main text="Two" loading />);

    const last = sdk.setParams.ifAvailable.mock.lastCall?.[0] as { isEnabled: boolean };
    expect(last.isEnabled).toBe(false);
    expect(sdk.setParams).not.toHaveBeenCalledWith(expect.objectContaining({ isEnabled: true }));
  });
});

describe("initTelegram", () => {
  it("makes native controls follow Telegram's theme, also when it changes", () => {
    initTelegram();
    expect(document.documentElement.style.colorScheme).toBe("dark");

    const change = sdk.isDark.sub.mock.lastCall?.[0] as (dark: boolean) => void;
    change(false);
    expect(document.documentElement.style.colorScheme).toBe("light");
  });
});

describe("hasTelegramBridge", () => {
  afterEach(() => {
    delete (window as { TelegramWebviewProxy?: unknown }).TelegramWebviewProxy;
  });

  it("is false in a plain browser tab, even with saved launch params (a reloaded dev tab)", async () => {
    sessionStorage.setItem("tapps/launchParams", "tgWebAppVersion=8.0");
    const { hasTelegramBridge } = await import("./index");

    expect(hasTelegramBridge()).toBe(false);
    sessionStorage.clear();
  });

  it("is true when a native Telegram app injects its proxy", async () => {
    (window as { TelegramWebviewProxy?: unknown }).TelegramWebviewProxy = { postEvent: vi.fn() };
    const { hasTelegramBridge } = await import("./index");

    expect(hasTelegramBridge()).toBe(true);
  });
});
