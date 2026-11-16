import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { App } from "./App";

// UI-02 wiring: the Settings row starts the tour on Home, ⋯ Settings closes it.
// UI-06 (spec §3, §8): the bot's buttons open the app on a screen with `?open=…`.

const telegram = vi.hoisted(() => ({
  openSettings: vi.fn() as () => void,
  /** What Telegram's Back button does on the screen now shown. */
  back: vi.fn() as () => void,
}));

vi.mock("./telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: (back: () => void) => {
    telegram.back = back;
  },
  backButtonAvailable: vi.fn(() => true),
  markReady: vi.fn(),
  confirmDestructive: vi.fn(() => Promise.resolve(false)),
  openTelegramLink: vi.fn(),
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
let myShalas: unknown[] = [];
const myShala = (side: "staff" | "student") => ({
  id: "00000000-0000-0000-0000-0000000000c1",
  name: "Ashtanga Almaty",
  city: "almaty",
  online: false,
  side,
  owner: false,
  roles: side === "staff" ? ["teacher"] : [],
});

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

const NO_DAYS = {
  practiced: 0,
  possible: 0,
  skipped: 0,
  unlogged: 0,
  auto: 0,
  rest: { rest: 0, moon: 0, ladies: 0, sick: 0, travel: 0 },
  contexts: { mysore: 0, led: 0, private: 0, self: 0 },
  online: 0,
  series: [],
  unspecified: 0,
  duration: { total_min: 0, count: 0 },
};
const STATS = {
  today: TODAY,
  timezone_known: true,
  auto: [],
  year: 2026,
  first_year: 2026,
  cells: Array.from({ length: 310 }, () => "none"), // Jan 1 … Nov 6
  moon: { location: "mysuru", days: [] },
  months: Array.from({ length: 12 }, () => NO_DAYS),
  year_total: NO_DAYS,
  runs: { current: 0, longest: 0 },
};

function respond(path: string) {
  if (path === "/api/v1/me") return ME;
  if (path === "/api/v1/me/stats") return STATS;
  if (path === "/api/v1/me/badges") return { badges: [] };
  if (path === "/api/v1/health") return { version: "1", commit: "abcdef0" };
  if (path === "/api/v1/moon/cities") return [];
  if (path === "/api/v1/me/links") return { teachers: [], students: [] };
  if (path === "/api/v1/me/shalas") return myShalas;
  if (path === "/api/v1/me/schedule")
    return {
      zone: "Asia/Almaty",
      zone_known: true,
      today: "2026-11-07",
      moon_city: "almaty",
      days: [],
      shalas: [],
      has_teachers: false,
      is_staff: false,
      shifts: [],
      occurrences: [],
    };
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
  myShalas = [];
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
  window.history.replaceState(null, "", "/");
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

test("My schedule is on Home for any shala member, and opens the week", async () => {
  myShalas = [myShala("student")];
  vi.resetModules(); // App's query cache is module-wide: a fresh one, not the earlier tests'
  const { App: Fresh } = await import("./App");
  render(<Fresh locale="en" firstName="Ash" inTelegram />);

  fireEvent.click(await screen.findByRole("button", { name: "🗓 My schedule" }));

  expect(await screen.findByRole("heading", { name: "🗓 My schedule" })).toBeInTheDocument();
});

test("someone in no shala sees no My schedule row", async () => {
  myShalas = [];
  vi.resetModules();
  const { App: Fresh } = await import("./App");
  render(<Fresh locale="en" firstName="Ash" inTelegram />);
  await screen.findByText(OFFER);

  expect(screen.queryByRole("button", { name: "🗓 My schedule" })).toBeNull();
});

describe("opened by a bot button (?open=…)", () => {
  const LINKS = "👥 Teachers and students";
  const HOME_ROW = "📊 My practice";

  /** The app as Telegram opens it at this address (a fresh App: its query cache is module-wide). */
  async function launch(search: string) {
    window.history.replaceState(null, "", search);
    vi.resetModules();
    const { App: Fresh } = await import("./App");
    render(<Fresh locale="en" firstName="Ash" inTelegram />);
  }
  const back = () => {
    act(() => {
      telegram.back();
    });
  };

  test("?open=new-shala opens the create form, ready to type the name", async () => {
    await launch("/?open=new-shala");

    const name = await screen.findByLabelText("Name");

    expect(name).toHaveFocus();
    expect(screen.getByRole("heading", { name: LINKS })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "🏛 Create a shala" })).toBeNull();
  });

  test("Back from the create form goes Home, not to Settings", async () => {
    await launch("/?open=new-shala");
    await screen.findByLabelText("Name");

    back();

    expect(await screen.findByRole("button", { name: HOME_ROW })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: LINKS })).toBeNull();
    expect(screen.queryByRole("button", { name: "🧭 Quick tour" })).toBeNull();
  });

  test("Teachers and students from Settings still starts closed and goes back to Settings", async () => {
    await launch("/");
    await screen.findByRole("button", { name: HOME_ROW });
    openSettings();
    fireEvent.click(await screen.findByRole("button", { name: LINKS }));

    expect(await screen.findByRole("button", { name: "🏛 Create a shala" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Name")).toBeNull();
    back();

    expect(await screen.findByRole("button", { name: "🧭 Quick tour" })).toBeInTheDocument();
  });

  test("?open=practice opens My practice, and Back goes Home", async () => {
    await launch("/?open=practice");

    expect(await screen.findByRole("heading", { name: "My practice" })).toBeInTheDocument();
    back();

    expect(await screen.findByRole("button", { name: HOME_ROW })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "My practice" })).toBeNull();
  });

  test.each(["/?open=somewhere-new", "/?open=", "/?open=new-shala%20"])(
    "an unknown value opens Home: %s",
    async (search) => {
      await launch(search);

      expect(await screen.findByText(OFFER)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: HOME_ROW })).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: LINKS })).toBeNull();
      expect(screen.queryByRole("heading", { name: "My practice" })).toBeNull();
    },
  );
});
