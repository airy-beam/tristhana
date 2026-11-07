import { beforeEach, expect, test, vi } from "vitest";

// ID-04: Share goes through a wrapper like every other SDK call: the only place that talks to
// the SDK, and a no-op where the feature isn't supported.

const sdk = vi.hoisted(() => ({ available: true, open: vi.fn() }));

vi.mock("@telegram-apps/sdk-react", () => ({
  openTelegramLink: Object.assign(sdk.open, {
    isAvailable: () => sdk.available,
    ifAvailable: (...args: unknown[]) => {
      if (sdk.available) sdk.open(...args);
    },
  }),
}));

import { openTelegramLink } from ".";

const LINK = "https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fbot";

beforeEach(() => {
  sdk.open.mockReset();
  sdk.available = true;
});

test("opens the link inside Telegram", () => {
  openTelegramLink(LINK);

  expect(sdk.open).toHaveBeenCalledOnce();
  expect(sdk.open.mock.calls[0]?.[0]).toBe(LINK);
});

test("does nothing where it isn't supported", () => {
  sdk.available = false;

  expect(() => {
    openTelegramLink(LINK);
  }).not.toThrow();
  expect(sdk.open).not.toHaveBeenCalled();
});
