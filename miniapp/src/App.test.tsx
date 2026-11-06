import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { App } from "./App";

// UI-02 wiring: the Settings row starts the tour on Home, ⋯ Settings closes it.

const telegram = vi.hoisted(() => ({ openSettings: vi.fn() as () => void }));

vi.mock("./telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  markReady: vi.fn(),
  useMainButton: vi.fn(),
  useSettingsButton: (open: () => void) => {
    telegram.openSettings = open;
  },
  enableClosingConfirmation: vi.fn(),
  disableClosingConfirmation: vi.fn(),
}));

const TODAY = "2026-11-06";
const ME = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Ash",
  locale: "en",
  timezone: null,
  name_from_telegram: true,
  locale_from_telegram: true,
  hide_ladies: false,
  offer_check_in: true,
  home_city_chosen: true,
  day_off: null,
};
const OFFER = "Want a quick look around? It takes a minute.";

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

function respond(path: string) {
  if (path === "/api/v1/me") return ME;
  if (path === "/api/v1/health") return { version: "1", commit: "abcdef0" };
  if (path === "/api/v1/moon/cities") return [];
  if (path === "/api/v1/me/days") {
    return {
      today: TODAY,
      timezone_known: true,
      days: [{ date: TODAY, status: "rest", practices: [], check_ins: [] }],
      auto: [],
      moon_location: "mysuru",
      notes: [],
      periods: [],
    };
  }
  if (path === "/api/v1/me/moon-days") {
    return { location: { slug: "mysuru", explicit: false }, today: TODAY, days: [] };
  }
  if (path === "/api/v1/me/notification-settings") {
    return {
      moon: { offsets: [1, 7], at: "19:00:00" },
      quiet: { start: "22:00:00", end: "07:00:00" },
      daily_cap: 3,
      practice: { on: true, at: "20:00:00", days: [1, 2, 3, 4, 5, 7] },
      timezone: null,
    };
  }
  return {};
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => Promise.resolve(json(respond(new URL(request.url).pathname)))),
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe = vi.fn();
      disconnect = vi.fn();
    },
  );
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const renderApp = () => render(<App locale="en" firstName="Ash" inTelegram />);
const openSettings = () => {
  act(() => {
    telegram.openSettings();
  });
};

test("the Settings row starts the tour on Home, and no offer follows it", async () => {
  renderApp();
  await screen.findByText(OFFER);
  openSettings();

  fireEvent.click(await screen.findByRole("button", { name: "🧭 Quick tour" }));

  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  expect(screen.queryByText(OFFER)).not.toBeInTheDocument();
  expect(localStorage.getItem("onboard.tour")).toBe("1");
});

test("Telegram's ⋯ Settings closes the tour, and it doesn't come back on Home", async () => {
  renderApp();
  fireEvent.click(await screen.findByRole("button", { name: "Show me" }));
  await screen.findByRole("dialog");

  openSettings();

  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  await screen.findByRole("button", { name: "🧭 Quick tour" });
});
