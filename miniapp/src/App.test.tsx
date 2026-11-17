import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

// UI-06 stage 2 (spec §2, §4, §10; ADR-0047): three tabs, one stack, a gear. A screen shows
// Back or the tabs, never both. The bot's `?open=…` values stay a contract.
// The Telegram SDK is the mock, not `./telegram`: the Back layers are the real ones.

const sdk = vi.hoisted(() => ({
  /** Listeners of Telegram's Back button, and whether Telegram shows it (else: Close). */
  back: new Set<() => void>(),
  backShown: false,
  /** Listeners of Telegram's ⋯ "Settings" item. */
  settings: new Set<() => void>(),
  haptic: [] as string[],
  /** What Telegram's main button was last told. */
  main: [] as { text?: string; isVisible?: boolean }[],
}));

vi.mock("@telegram-apps/sdk-react", () => {
  const safe = (run: (...args: never[]) => unknown = () => undefined) =>
    Object.assign(vi.fn(run), { isAvailable: () => true, ifAvailable: vi.fn(run) });
  const listen = (listeners: Set<() => void>) => (listener: () => void) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  };
  return {
    init: vi.fn(),
    isTMA: () => true,
    backButton: {
      mount: safe(),
      show: safe(() => {
        sdk.backShown = true;
      }),
      hide: safe(() => {
        sdk.backShown = false;
      }),
      onClick: listen(sdk.back),
    },
    settingsButton: { mount: safe(), show: safe(), onClick: listen(sdk.settings) },
    mainButton: {
      mount: safe(),
      setParams: safe((params: { text?: string; isVisible?: boolean }) => {
        sdk.main.push(params);
      }),
      onClick: () => () => undefined,
    },
    closingBehavior: {
      mount: safe(),
      enableConfirmation: safe(),
      disableConfirmation: safe(),
    },
    hapticFeedback: {
      impactOccurred: safe(),
      notificationOccurred: safe(),
      selectionChanged: safe(() => sdk.haptic.push("selection")),
    },
    miniApp: { mountSync: safe(), ready: safe(), close: safe(), setBottomBarColor: safe() },
    popup: { show: safe(() => Promise.resolve("cancel")) },
    requestWriteAccess: safe(() => Promise.resolve("denied")),
    retrieveLaunchParams: () => ({}),
    retrieveRawInitData: () => "user=%7B%7D&hash=abc",
    themeParams: { mountSync: safe(), bindCssVars: safe(), isDark: safe(() => false) },
    viewport: { mount: safe(() => Promise.resolve()), bindCssVars: safe(), expand: safe() },
    openLink: safe(),
    openTelegramLink: safe(),
  };
});

const TODAY = "2026-11-06";
const SHALA = "00000000-0000-0000-0000-0000000000c1";
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
const myShala = (side: "staff" | "student") => ({
  id: SHALA,
  name: "Ashtanga Almaty",
  city: "almaty",
  online: false,
  side,
  owner: false,
  roles: side === "staff" ? ["teacher"] : [],
});
const LENA = {
  id: "00000000-0000-0000-0000-0000000000a1",
  name: "Лена",
  primary: true,
  primary_chosen: false,
  linked_at: "2026-11-01T06:00:00Z",
};
const SHIVA = {
  id: "00000000-0000-0000-0000-0000000000b1",
  name: "Shiva",
  linked_at: "2026-11-02T06:00:00Z",
};
const OWNED = {
  id: SHALA,
  name: "Ashtanga Almaty",
  city: { slug: "almaty", name: "Almaty" },
  zone: "Asia/Almaty",
  online: false,
  moon_city: null,
  staff: [{ id: "00000000-0000-0000-0000-000000000001", name: "Ash", owner: true, roles: [] }],
  students_total: 0,
  days_off: null,
  moon_policy: "closed",
  me: { owner: true, roles: [], student: false, schedule: true, announce: true },
};
const QR = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkAAAACklEQVR4AQ==";

/** Who this person is, per test. Nobody by default: no teacher, no student, no shala. */
let account: Record<string, unknown> = ME;
let myShalas: unknown[] = [];
let links: { teachers: unknown[]; students: unknown[] } = { teachers: [], students: [] };
let seen: Request[] = [];
/** What GET /me/next-steps offers, and today's classes in My schedule (UI-06). */
let nextSteps: { kind: string; shala_id: string | null }[] = [];
let classesToday: unknown[] = [];
/** Whether GET /shalas/<id> answers with a card I own (else `{}`, as for any unknown path). */
let ownedShala = false;
/** The page's scroll, and a section scrolled into view (jsdom has neither). */
const scrollTo = vi.fn();
const scrollIntoView = vi.fn();

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

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

function respond(path: string): Response {
  // The device-timezone reply is the account too, and replaces it outside UTC.
  if (path === "/api/v1/me" || path === "/api/v1/me/device-timezone") return json(account);
  if (path === "/api/v1/me/stats") return json(STATS);
  if (path === "/api/v1/me/badges") return json({ badges: [] });
  if (path === "/api/v1/health") return json({ version: "1", commit: "abcdef0" });
  if (path === "/api/v1/moon/cities") return json([]);
  if (path === "/api/v1/me/next-steps") return json({ steps: nextSteps });
  if (path === "/api/v1/me/links") return json(links);
  if (path === "/api/v1/me/shalas") return json(myShalas);
  if (path === "/api/v1/me/invite")
    return json({ url: "https://t.me/tristhana_bot?start=t_a", qr: QR });
  if (ownedShala && path === `/api/v1/shalas/${SHALA}`) return json(OWNED);
  if (path === `/api/v1/shalas/${SHALA}/join-link`)
    return json({ url: "https://t.me/tristhana_bot?start=s_a", qr: QR });
  if (path === `/api/v1/shalas/${SHALA}/schedule`)
    return json({
      zone: "Asia/Almaty",
      city: "almaty",
      moon_policy: "closed",
      days_off: null,
      days: [],
      occurrences: [],
      closures: [],
    });
  if (path === "/api/v1/me/students") return json({ total: 1, students: [] });
  // My asanas shows its heading while these load or fail; their shapes are its own tests'.
  if (path === "/api/v1/catalog" || path.startsWith("/api/v1/me/progression"))
    return json({ code: "unavailable" }, 503);
  if (path === "/api/v1/me/schedule")
    return json({
      zone: "Asia/Almaty",
      zone_known: true,
      today: "2026-11-07",
      moon_city: "almaty",
      days: [],
      shalas: myShalas,
      has_teachers: false,
      is_staff: false,
      shifts: [],
      occurrences: classesToday,
    });
  if (path === "/api/v1/me/days") {
    return json({
      today: TODAY,
      timezone_known: true,
      days: [{ date: TODAY, status: "rest", practices: [], check_ins: [] }],
      auto: [],
      moon_location: "mysuru",
      notes: [],
      periods: [],
    });
  }
  if (path === "/api/v1/me/moon-days") {
    return json({
      location: { slug: "mysuru", explicit: false },
      today: TODAY,
      days: [{ date: "2026-11-09", kind: "amavasya", phase: "amavasya" }],
    });
  }
  if (path === "/api/v1/me/notification-settings") {
    return json({
      moon: { offsets: [1, 7], at: "19:00:00" },
      quiet: { start: "22:00:00", end: "07:00:00" },
      daily_cap: 3,
      practice: { on: true, at: "20:00:00", days: [1, 2, 3, 4, 5, 7] },
      timezone: null,
    });
  }
  return json({});
}

// Every screen behind a tab or a row is a lazy chunk, and `launch()` resets the modules. The
// first test to open one pays for its transform, which on a busy machine can outlast the one
// second `findBy…` waits (a flake seen on "the gear opens Settings…"). Loading each once here
// fills the transform cache, which outlives a reset, so no test's first open is the slow one.
beforeAll(async () => {
  await Promise.all([
    import("./App"),
    import("./screens/stats/Stats"),
    import("./screens/stats/Year"),
    import("./screens/badges/Badges"),
    import("./screens/trends/Trends"),
    import("./screens/settings/Links"),
    import("./screens/settings/Settings"),
    import("./screens/settings/pages/Language"),
    import("./screens/settings/pages/City"),
    import("./screens/settings/pages/DayOff"),
    import("./screens/settings/pages/Reminders"),
    import("./screens/settings/pages/More"),
    import("./screens/settings/DirectoryListing"),
    import("./screens/progression/Progression"),
    import("./screens/progression/Timeline"),
    import("./screens/moon/MoonScreen"),
    import("./screens/shalas/MySchedule"),
    import("./screens/shalas/ShalaScreen"),
    import("./screens/shalas/Attendance"),
    import("./screens/teachers/Students"),
    import("./screens/announcements/Announcements"),
    import("./screens/ClassToday"),
    import("./screens/share/ShareSheet"),
  ]);
}, 60_000);

beforeEach(() => {
  localStorage.clear();
  account = ME;
  myShalas = [];
  links = { teachers: [], students: [] };
  seen = [];
  nextSteps = [];
  classesToday = [];
  ownedShala = false;
  sdk.haptic.length = 0;
  sdk.main.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      seen.push(request);
      return Promise.resolve(respond(new URL(request.url).pathname));
    }),
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe = vi.fn();
      disconnect = vi.fn();
    },
  );
  scrollTo.mockClear();
  scrollIntoView.mockClear();
  vi.stubGlobal("scrollTo", scrollTo);
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  Element.prototype.scrollIntoView = scrollIntoView;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.doUnmock("./screens/stats/Stats");
  vi.doUnmock("./screens/settings/Settings");
  vi.doUnmock("./telegram");
  Reflect.deleteProperty(window, "scrollY");
  window.history.replaceState(null, "", "/");
});

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");

/** The app as Telegram opens it at this address (a fresh App: its query cache is module-wide). */
async function launch(search = "/") {
  window.history.replaceState(null, "", search);
  vi.resetModules();
  const { App } = await import("./App");
  render(<App locale="en" firstName="Ash" inTelegram />);
}

const TABS = { today: "📝 Today", practice: "📊 Practice", shala: "🏛 Shala" } as const;
const bar = () => screen.queryByRole("navigation", { name: "Sections" });
const tab = (name: keyof typeof TABS) =>
  within(screen.getByRole("navigation", { name: "Sections" })).getByRole("button", {
    name: TABS[name],
  });
const current = () =>
  within(screen.getByRole("navigation", { name: "Sections" }))
    .getAllByRole("button")
    .filter((b) => b.getAttribute("aria-current") === "page")
    .map((b) => b.textContent);
const gear = () => screen.getByRole("button", { name: "Settings" });
const heading = (name: string | RegExp | ((name: string) => boolean)) =>
  screen.findByRole("heading", { level: 1, name });
const today = () => heading((n: string) => plain(n) === "Namaste, Ash 🙏");
const practice = () => heading("My practice");
const shala = () => heading("🏛 Shala");
const settings = () => heading("Settings");

/** Telegram's Back button (and Android's hardware back, which follows it). */
const back = () => {
  expect(sdk.backShown).toBe(true);
  act(() => {
    [...sdk.back].forEach((listener) => {
      listener();
    });
  });
};
/** Telegram's ⋯ menu → Settings. */
const menuSettings = () => {
  act(() => {
    [...sdk.settings].forEach((listener) => {
      listener();
    });
  });
};
const go = async (name: keyof typeof TABS) => {
  fireEvent.click(tab(name));
  await (name === "today" ? today() : name === "practice" ? practice() : shala());
};

describe("the tab bar", () => {
  test("three tabs, Today first and current; Telegram shows Close, not Back", async () => {
    await launch();
    await today();

    const tabs = within(screen.getByRole("navigation", { name: "Sections" })).getAllByRole(
      "button",
    );
    expect(tabs.map((b) => b.textContent)).toEqual(["📝 Today", "📊 Practice", "🏛 Shala"]);
    expect(current()).toEqual(["📝 Today"]);
    expect(sdk.backShown).toBe(false);
    expect(sdk.back.size).toBe(0);
  });

  test("a tap switches the tab, moves the focus to its heading and scrolls to the top", async () => {
    await launch();
    await today();
    scrollTo.mockClear();

    fireEvent.click(tab("practice"));

    await waitFor(async () => {
      expect(await practice()).toHaveFocus();
    });
    expect(current()).toEqual(["📊 Practice"]);
    expect(scrollTo).toHaveBeenCalledWith({ top: 0 });
    expect(sdk.haptic).toContain("selection");
    expect(sdk.backShown).toBe(false); // a root has no Back

    fireEvent.click(tab("shala"));
    await waitFor(async () => {
      expect(await shala()).toHaveFocus();
    });
    expect(current()).toEqual(["🏛 Shala"]);

    fireEvent.click(tab("today"));
    expect(await today()).toHaveFocus();
    expect(sdk.backShown).toBe(false);
  });

  test("the heading isn't focused when the app opens", async () => {
    await launch();

    expect(await today()).not.toHaveFocus();
  });

  test("a tap on the active tab only scrolls to the top", async () => {
    await launch();
    await today();
    await go("practice");
    scrollTo.mockClear();

    fireEvent.click(tab("practice"));

    expect(scrollTo).toHaveBeenCalledWith({ top: 0 });
    expect(current()).toEqual(["📊 Practice"]);
    expect(await practice()).toBeInTheDocument();
  });

  test("Today has no rows for the other tabs, no tour offer and no Settings row", async () => {
    await launch();
    await today();
    await screen.findByRole("heading", { level: 2, name: /^Today, / });

    for (const gone of [
      "📊 My practice",
      "🧘 My asanas",
      "👥 My students",
      "🗓 My schedule",
      "⚙️ Settings",
      "Show me",
    ]) {
      expect(screen.queryByRole("button", { name: gone })).toBeNull();
    }
    expect(screen.queryByText(/quick look around/)).toBeNull();
  });
});

describe("Settings: the gear and Telegram's ⋯ item are one route", () => {
  test("the gear opens Settings over the tab, without the bar; Back returns to that tab", async () => {
    await launch();
    await today();
    await go("practice");

    fireEvent.click(gear());

    await settings();
    expect(bar()).toBeNull();
    expect(screen.queryByRole("button", { name: "Settings" })).toBeNull();
    back();

    expect(await practice()).toBeInTheDocument();
    expect(current()).toEqual(["📊 Practice"]);
    expect(sdk.backShown).toBe(false);
  });

  test("⋯ Settings does the same, and a second tap doesn't stack a second screen", async () => {
    await launch();
    await today();
    await go("shala");

    menuSettings();
    await settings();
    menuSettings();
    await settings();
    back();

    expect(await shala()).toBeInTheDocument();
    expect(sdk.backShown).toBe(false);
  });

  test("⋯ Settings over a pushed screen goes back to that screen", async () => {
    await launch();
    await today();
    await go("practice");
    fireEvent.click(await screen.findByRole("button", { name: "🧘 My asanas" }));
    await heading("My asanas");

    menuSettings();
    await settings();
    back();

    expect(await heading("My asanas")).toBeInTheDocument();
    back();
    expect(await practice()).toBeInTheDocument();
  });

  test("Settings has no Teachers and students row and no tour", async () => {
    await launch();
    await today();
    fireEvent.click(gear());
    await settings();
    await screen.findByRole("button", { name: "📖 Guide" });

    expect(screen.queryByRole("button", { name: /Teachers and students/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /tour/i })).toBeNull();
  });

  // UI-06 stage 3: both land on the bot's five rows, each carrying its value, and Guide.
  test.each([
    ["the gear", () => fireEvent.click(gear())],
    ["⋯ Settings", menuSettings],
  ])("%s shows the five rows, drawn from the account already loaded", async (_name, open) => {
    account = { ...ME, timezone: "Asia/Almaty", day_off: [7] };
    await launch();
    await today();

    open();

    const screenOf = (await settings()).closest("main") as HTMLElement;
    expect(
      within(screenOf)
        .getAllByRole("button")
        .map((b) => plain(b.textContent)),
    ).toEqual([
      "🗣 Language: As in Telegram",
      "🕐 My time: Almaty (UTC+5)",
      "😌 Day off: Sunday",
      "🔔 Reminders",
      "More…",
      "📖 Guide",
    ]);
    // None of what the pages read (the one long screen read these as it opened).
    const paths = seen.map((r) => new URL(r.url).pathname);
    expect(paths).not.toContain("/api/v1/me/notification-settings");
    expect(paths).not.toContain("/api/v1/me/calendar-feed");
    expect(paths).not.toContain("/api/v1/me/links");
  });

  test("a row opens its page over the rows; Back returns to the rows, then to the tab", async () => {
    await launch();
    await today();
    fireEvent.click(gear());
    await settings();

    fireEvent.click(screen.getByRole("button", { name: "More…" }));

    expect(await heading("⚙️ More settings")).toHaveFocus();
    expect(screen.queryByRole("heading", { level: 1, name: "Settings" })).toBeNull();
    expect(bar()).toBeNull();
    back();

    expect(await settings()).toBeVisible();
    expect(screen.getByRole("button", { name: "More…" })).toHaveFocus();
    expect(screen.queryByRole("heading", { level: 1, name: "⚙️ More settings" })).toBeNull();
    back();

    expect(await today()).toBeInTheDocument();
    expect(sdk.backShown).toBe(false);
  });

  test("the day-off link on Practice opens the Day off page, and Back returns to Practice", async () => {
    await launch();
    await today();
    await go("practice");

    fireEvent.click(await screen.findByRole("button", { name: "😌 Set your weekly day off" }));

    expect(await heading("Day off")).toHaveFocus();
    expect(screen.getByRole("group", { name: "Day off" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Settings" })).toBeNull(); // not the rows
    back();

    expect(await practice()).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Day off" })).toBeNull();
    expect(sdk.backShown).toBe(false);
  });
});

// ADR-0047 as amended in review: what Settings was opened over stays mounted, hidden, so Back
// returns to it as it was left (a half-filled form, an unsaved note), as Stats under Badges.
describe("Settings keeps what it was opened over", () => {
  const mainButtonShown = () => sdk.main.findLast((p) => p.isVisible !== undefined)?.isVisible;

  test("a half-filled create-shala form is still filled after ⋯ Settings and Back", async () => {
    await launch("/?open=new-shala");
    await shala();
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: "Ashtanga Almaty" } });

    menuSettings();

    await settings();
    expect(screen.getByDisplayValue("Ashtanga Almaty")).not.toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: "🏛 Shala" })).toBeNull();
    expect(bar()).toBeNull();
    back();

    expect(await shala()).toBeVisible();
    expect(screen.getByDisplayValue("Ashtanga Almaty")).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: "Settings" })).toBeNull();
    expect(sdk.backShown).toBe(false);
    expect(bar()).not.toBeNull();
  });

  test("an unsaved note is still there: Back closes Settings first, the note keeps its own", async () => {
    await launch();
    await today();
    fireEvent.click(await screen.findByRole("button", { name: "📓 Add a note" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Diary" }), {
      target: { value: "Kapotasana felt lighter" },
    });

    menuSettings();
    await settings();
    expect(screen.queryByRole("textbox", { name: "Diary" })).toBeNull(); // hidden, not gone
    back();

    expect(await screen.findByRole("textbox", { name: "Diary" })).toHaveValue(
      "Kapotasana felt lighter",
    );
    expect(screen.queryByRole("heading", { level: 1, name: "Settings" })).toBeNull();
    expect(sdk.backShown).toBe(true); // the note's own layer, as before Settings
    expect(bar()).toBeNull();
  });

  test("the month chosen on Practice is kept under the day-off setting", async () => {
    await launch();
    await today();
    await go("practice");
    const link = await screen.findByRole("button", { name: "😌 Set your weekly day off" });
    const stats = seen.filter((r) => new URL(r.url).pathname === "/api/v1/me/stats").length;

    fireEvent.click(link);
    await heading("Day off");
    back();

    expect(await practice()).toBeVisible();
    expect(link).toBeVisible(); // the same element: Practice was never unmounted
    expect(seen.filter((r) => new URL(r.url).pathname === "/api/v1/me/stats")).toHaveLength(stats);
  });

  test("Settings opens at the top with its heading focused; Back gives the scroll back", async () => {
    await launch();
    await today();
    await go("practice");
    Object.defineProperty(window, "scrollY", { value: 420, configurable: true });
    scrollTo.mockClear();

    menuSettings();

    await waitFor(async () => {
      expect(await settings()).toHaveFocus();
    });
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 0 });
    back();

    await practice();
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 420 });
    // The gear that opened it is drawn anew, so the focus lands on the screen's heading.
    expect(await practice()).toHaveFocus();
  });

  test("Telegram's main button of the screen underneath is hidden meanwhile", async () => {
    await launch();
    await today();
    await waitFor(() => {
      expect(mainButtonShown()).toBe(true);
    });
    expect(sdk.main).toContainEqual({ text: "Check connection", isVisible: true });

    menuSettings();
    await settings();

    expect(mainButtonShown()).toBe(false);
    back();
    await today();
    await waitFor(() => {
      expect(mainButtonShown()).toBe(true);
    });
  });
});

describe("Back or tabs, never both", () => {
  test("a pushed screen has no bar from its first frame, before its Back layer is counted", async () => {
    // The frame before effects run: no layer is counted yet.
    vi.doMock("./telegram", async (original) => ({
      ...(await original<typeof import("./telegram")>()),
      useBackShown: () => false,
    }));
    await launch();
    await today();
    expect(bar()).not.toBeNull();

    fireEvent.click(await screen.findByRole("button", { name: "🌑 Next moon day" }));

    expect(bar()).toBeNull();
    expect(screen.queryByRole("button", { name: "Settings" })).toBeNull();
  });

  test("after a pop the root is at the top with its heading focused", async () => {
    await launch();
    await today();
    await go("practice");
    fireEvent.click(await screen.findByRole("button", { name: "🧘 My asanas" }));
    await heading("My asanas");
    scrollTo.mockClear();

    back();

    await waitFor(async () => {
      expect(await practice()).toHaveFocus();
    });
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 0 });
  });

  test("the bar is absent inside a pushed screen and returns on the root", async () => {
    await launch();
    await today();

    fireEvent.click(await screen.findByRole("button", { name: "🌑 Next moon day" }));

    await heading((n: string) => plain(n) === "🌙 Moon days · 📍 mysuru");
    expect(bar()).toBeNull();
    expect(sdk.backShown).toBe(true);
    back();

    await today();
    expect(bar()).not.toBeNull();
    expect(sdk.backShown).toBe(false);
  });

  test("the bar is absent while a note has unsaved text", async () => {
    await launch();
    await today();
    fireEvent.click(await screen.findByRole("button", { name: "📓 Add a note" }));
    expect(bar()).not.toBeNull(); // nothing typed yet: nothing to protect

    fireEvent.change(screen.getByRole("textbox", { name: "Diary" }), {
      target: { value: "Kapotasana felt lighter" },
    });

    expect(bar()).toBeNull();
    expect(sdk.backShown).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(bar()).not.toBeNull();
    });
  });

  test("an inner layer hides the bar too: Badges over Practice", async () => {
    await launch();
    await today();
    await go("practice");

    fireEvent.click(await screen.findByRole("button", { name: "🏅 Badges" }));

    await waitFor(() => {
      expect(bar()).toBeNull();
    });
    back();
    await waitFor(() => {
      expect(bar()).not.toBeNull();
    });
    expect(current()).toEqual(["📊 Practice"]);
  });

  // UI-06 stage 3: the year is a layer over the Practice root, and the day card is one too.
  test("the year over Practice hides the bar; Back returns to the month", async () => {
    await launch();
    await today();
    await go("practice");
    await screen.findByRole("heading", { level: 2, name: "November 2026" });

    fireEvent.click(screen.getByRole("button", { name: /^📅/ }));

    expect(await heading("2026")).toHaveFocus();
    await waitFor(() => {
      expect(bar()).toBeNull();
    });
    back();
    await waitFor(() => {
      expect(bar()).not.toBeNull();
    });
    expect(screen.getByRole("heading", { level: 2, name: "November 2026" })).toBeVisible();
    expect(current()).toEqual(["📊 Practice"]);
  });

  test("a day opened on the Practice month hides the bar until Back closes it", async () => {
    await launch();
    await today();
    await go("practice");

    fireEvent.click(
      await screen.findByRole("button", { name: (n) => plain(n).startsWith("Tue, Nov 3:") }),
    );

    const card = await screen.findByRole("region", { name: (n) => plain(n).includes("Nov 3") });
    await waitFor(() => {
      expect(bar()).toBeNull();
    });
    expect(within(card).getByRole("heading", { level: 2 })).toHaveFocus();
    back();
    await waitFor(() => {
      expect(bar()).not.toBeNull();
    });
    expect(screen.queryByRole("region", { name: (n) => plain(n).includes("Nov 3") })).toBeNull();
    expect(await practice()).toBeInTheDocument(); // still the Practice root
  });
});

describe("what moved where", () => {
  test("Practice: My asanas is the first row, and Back returns to Practice", async () => {
    await launch();
    await today();
    await go("practice");
    await screen.findByRole("button", { name: "🏅 Badges" });

    const rows = screen.getAllByRole("button").filter((b) => b.className === "row-button");
    expect(rows[0]).toHaveAccessibleName("🧘 My asanas");
    fireEvent.click(rows[0] as HTMLElement);

    await heading("My asanas");
    expect(bar()).toBeNull();
    back();
    expect(await practice()).toBeInTheDocument();
  });

  test("Shala: My schedule is the first row for a shala member", async () => {
    myShalas = [myShala("student")];
    await launch();
    await today();
    await go("shala");

    const row = await screen.findByRole("button", { name: "🗓 My schedule" });
    const rows = screen.getAllByRole("button").filter((b) => b.className === "row-button");
    expect(rows[0]).toBe(row);
    fireEvent.click(row);

    await heading(/^🗓 My schedule/);
    back();
    expect(await shala()).toBeInTheDocument();
  });

  test("Shala: no My schedule row outside a shala", async () => {
    links = { teachers: [LENA], students: [] };
    await launch();
    await today();
    await go("shala");
    await screen.findByText("Лена");

    expect(screen.queryByRole("button", { name: "🗓 My schedule" })).toBeNull();
  });

  test("Shala: My students opens from the students card, and Back returns to Shala", async () => {
    links = { teachers: [], students: [SHIVA] };
    await launch();
    await today();
    await go("shala");

    fireEvent.click(await screen.findByRole("button", { name: "👥 My students" }));

    await heading((n: string) => plain(n) === "👥 My students (1)");
    expect(bar()).toBeNull();
    back();
    expect(await shala()).toBeInTheDocument();
    expect(await screen.findByText("Shiva")).toBeInTheDocument();
  });

  test("Today's moon row opens the whole moon card", async () => {
    await launch();
    await today();

    const row = await screen.findByRole("button", { name: "🌑 Next moon day" });
    expect(row).toHaveAccessibleDescription(/^New moon · /);
    fireEvent.click(row);

    await heading((n: string) => plain(n) === "🌙 Moon days · 📍 mysuru");
    expect(screen.getByText(/follow your teacher/)).toBeInTheDocument();
  });
});

describe("Today: one next step, each leading to its place", () => {
  const asked = (path: string) => seen.some((r) => new URL(r.url).pathname === path);

  test("no step, no card; people in no shala ask for no schedule", async () => {
    await launch();
    await today();
    await screen.findByRole("heading", { level: 2, name: /^Today, / });

    await waitFor(() => {
      expect(asked("/api/v1/me/next-steps")).toBe(true);
    });
    expect(screen.queryByRole("button", { name: "Not now" })).toBeNull();
    expect(asked("/api/v1/me/schedule")).toBe(false);
  });

  test("with no zone yet, the reminder step opens the reminder setting; Back returns to Today", async () => {
    nextSteps = [
      { kind: "reminder", shala_id: null },
      { kind: "position", shala_id: null },
    ];
    await launch();
    await today();

    fireEvent.click(await screen.findByRole("button", { name: "Yes, remind me" }));

    // The Reminders page, not the five rows; it says once why the times wait.
    expect(await heading("🔔 Reminders")).toHaveFocus();
    expect(await screen.findByRole("checkbox", { name: "🔔 Ask me once a day" })).toBeChecked();
    expect(screen.getAllByText(/once your time zone is known/)).toHaveLength(1);
    expect(screen.queryByRole("heading", { level: 1, name: "Settings" })).toBeNull();
    back();
    expect(await today()).toBeInTheDocument();
    expect(sdk.backShown).toBe(false);
  });

  test("with a zone, the reminder step turns the reminder on right there, in one tap", async () => {
    account = { ...ME, timezone: "Asia/Almaty" };
    nextSteps = [{ kind: "reminder", shala_id: null }];
    await launch();
    await today();

    fireEvent.click(await screen.findByRole("button", { name: "Yes, remind me" }));

    // The stub's settings: 20:00. My own zone, so no offset.
    expect(plain((await screen.findByText(/once a day at/)).textContent)).toBe(
      "🔔 I'll ask once a day at 20:00 Almaty.",
    );
    const patch = seen.find((r) => r.method === "PATCH");
    expect(new URL(patch?.url ?? "").pathname).toBe("/api/v1/me/notification-settings");
    expect(await patch?.json()).toEqual({ practice: { on: true } });
    expect(screen.queryByRole("heading", { level: 1, name: "Settings" })).toBeNull();
    expect(bar()).not.toBeNull(); // still on Today

    fireEvent.click(screen.getByRole("button", { name: "⏰ Change the time" }));

    await heading("🔔 Reminders");
    expect(plain((await screen.findByText(/^🕐 Times:/)).textContent)).toBe("🕐 Times: Almaty");
    expect(await screen.findByRole("button", { name: "20:00", pressed: true })).toBeVisible();
    back();
    expect(await today()).toBeVisible();
  });

  test("Not now shows the next step, which opens My asanas", async () => {
    nextSteps = [
      { kind: "reminder", shala_id: null },
      { kind: "position", shala_id: null },
    ];
    await launch();
    await today();

    fireEvent.click(await screen.findByRole("button", { name: "Not now" }));
    fireEvent.click(screen.getByRole("button", { name: "Open My asanas" }));

    await heading("My asanas");
    expect(bar()).toBeNull();
    back();
    expect(await today()).toBeInTheDocument();
  });

  test("the invite step lands on the Shala tab with the invite open", async () => {
    nextSteps = [{ kind: "invite_student", shala_id: null }];
    await launch();
    await today();

    fireEvent.click(await screen.findByRole("button", { name: "Open the invite" }));

    await shala();
    expect(current()).toEqual(["🏛 Shala"]);
    expect(await screen.findByRole("img", { name: "QR code for your invite link" })).toBeVisible();
    expect(sdk.backShown).toBe(false); // a tab root
  });

  // Where the work is: not the shala card, where the same row would have to be found again.
  test("add_class opens that shala's class form", async () => {
    myShalas = [{ ...myShala("staff"), owner: true }];
    ownedShala = true;
    nextSteps = [{ kind: "add_class", shala_id: SHALA }];
    await launch();
    await today();

    fireEvent.click(await screen.findByRole("button", { name: "Add a class" }));

    // UI-06 stage 4: the form is a layer of its own over the card; Telegram's main button
    // saves it.
    expect(await screen.findByRole("heading", { level: 1, name: "New class" })).toBeVisible();
    await waitFor(() => {
      expect(sdk.main).toContainEqual({ text: "Save the class", isVisible: true });
    });
    expect(screen.queryByRole("button", { name: "Save the class" })).toBeNull();
    expect(screen.queryByRole("button", { name: "➕ Add a class" })).toBeNull();
    expect(bar()).toBeNull(); // the form and the card are layers over the Shala root
    back(); // from the form: the shala's card, where the new class would show
    expect(await screen.findByRole("button", { name: "➕ Add a class" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Ashtanga Almaty");
    expect(bar()).toBeNull();
    back();
    expect(await shala()).toBeInTheDocument();
    expect(current()).toEqual(["🏛 Shala"]);
  });

  test("invite_shala_students opens that shala's student invite", async () => {
    myShalas = [{ ...myShala("staff"), owner: true }];
    ownedShala = true;
    nextSteps = [{ kind: "invite_shala_students", shala_id: SHALA }];
    await launch();
    await today();

    fireEvent.click(await screen.findByRole("button", { name: "Invite students" }));

    expect(await screen.findByRole("img", { name: "QR code for the shala's link" })).toBeVisible();
    expect(
      seen.filter((r) => new URL(r.url).pathname === `/api/v1/shalas/${SHALA}/join-link`),
    ).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Save the class" })).toBeNull(); // not the class form
  });

  test("today's class is one row for people in a shala; it opens My schedule", async () => {
    myShalas = [myShala("student")];
    classesToday = [
      {
        shala_id: SHALA,
        class_id: "00000000-0000-0000-0000-0000000000d1",
        key: "2026-11-07",
        on: "2026-11-07",
        type: "mysore",
        title: null,
        start: "07:00",
        end: "09:00",
        starts_at: "2026-11-07T02:00:00Z",
        zone: "Asia/Almaty",
        city: "almaty",
        cancelled: null,
        online: false,
      },
    ];
    await launch();
    await today();

    const row = await screen.findByRole("button", { name: "🗓 Today's class" });
    expect(row).toHaveAccessibleDescription("Mysore · 07:00 Almaty · Ashtanga Almaty");
    // One small card holds it and the moon row.
    expect(row.parentElement).toHaveClass("card", "list");
    expect(row.parentElement).toContainElement(
      screen.getByRole("button", { name: "🌑 Next moon day" }),
    );
    fireEvent.click(row);

    await heading("🗓 My schedule");
    expect(bar()).toBeNull();
  });
});

describe("the empty Shala tab", () => {
  test("nobody yet: one plain line and two starts in one small card, no empty cards", async () => {
    await launch();
    await today();
    await go("shala");

    expect(
      await screen.findByText(
        "Nobody here yet. To add a teacher or join a shala, open the link they send you.",
      ),
    ).toBeInTheDocument();
    // The two starts sit under the bot's name for that row, so a student skips them.
    const starts = screen.getByRole("heading", { level: 2, name: "For teachers and shalas" });
    const invite = screen.getByRole("button", { name: "Invite students" });
    expect(starts.compareDocumentPosition(invite)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    // Two list rows of one card.
    expect(invite.parentElement).toHaveClass("card", "list");
    expect(invite.parentElement).toContainElement(
      screen.getByRole("button", { name: "Shala and classes" }),
    );
    expect(screen.queryByText("No students on your list.")).toBeNull();
    expect(screen.queryByRole("heading", { name: "🏛 Shalas" })).toBeNull();
    expect(screen.queryByRole("button", { name: "🏛 Create a shala" })).toBeNull();
    expect(bar()).not.toBeNull();
  });

  test("Invite students opens the full layout with the invite card open", async () => {
    await launch();
    await today();
    await go("shala");

    fireEvent.click(await screen.findByRole("button", { name: "Invite students" }));

    expect(await screen.findByRole("button", { name: "Copy link" })).toBeInTheDocument();
    expect(screen.getByText("No students on your list.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "🏛 Create a shala" })).toBeInTheDocument();
    expect(seen.filter((r) => new URL(r.url).pathname === "/api/v1/me/invite")).toHaveLength(1);
  });

  test("Shala and classes opens the full layout with the create form, ready to type", async () => {
    await launch();
    await today();
    await go("shala");

    fireEvent.click(await screen.findByRole("button", { name: "Shala and classes" }));

    expect(await screen.findByLabelText("Name")).toHaveFocus();
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "I teach: invite students" })).toBeInTheDocument();
  });

  test("someone with a teacher sees the layout, not the empty line", async () => {
    links = { teachers: [LENA], students: [] };
    await launch();
    await today();
    await go("shala");

    await screen.findByText("Лена");
    expect(screen.queryByText(/Nobody here yet/)).toBeNull();
    expect(screen.getByRole("button", { name: "📣 Announcements" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "🏛 Create a shala" })).toBeInTheDocument();
  });
});

describe("opened by a bot button (?open=…)", () => {
  test("?open=practice opens the Practice root, with nothing to go back to", async () => {
    await launch("/?open=practice");

    expect(await practice()).toBeInTheDocument();
    expect(current()).toEqual(["📊 Practice"]);
    expect(sdk.backShown).toBe(false);
  });

  test("?open=new-shala opens the Shala root with the create form, ready to type the name", async () => {
    await launch("/?open=new-shala");

    const name = await screen.findByLabelText("Name");

    expect(name).toHaveFocus();
    expect(screen.getByRole("heading", { level: 1, name: "🏛 Shala" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "🏛 Create a shala" })).toBeNull();
    expect(screen.queryByText(/Nobody here yet/)).toBeNull();
    expect(sdk.backShown).toBe(false);
  });

  test("the create form is opened once: coming back to the tab finds it closed", async () => {
    myShalas = [myShala("staff")];
    await launch("/?open=new-shala");
    await screen.findByLabelText("Name");
    fireEvent.blur(screen.getByLabelText("Name"));

    await go("today");
    await go("shala");

    expect(await screen.findByRole("button", { name: "🏛 Create a shala" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Name")).toBeNull();
  });

  test("?open=announce opens the composer over the Shala tab; Back goes to the Shala root", async () => {
    await launch(`/?open=announce&shala=${SHALA}`);

    await heading("📣 Announcement");
    expect(bar()).toBeNull();
    back();

    expect(await shala()).toBeInTheDocument();
    expect(current()).toEqual(["🏛 Shala"]);
    expect(sdk.backShown).toBe(false);
  });

  // UI-06 stage 3 (QF): the bot's "⚙️ More in the app".
  test("?open=settings opens Settings over Today; Back lands on Today", async () => {
    await launch("/?open=settings");

    await settings();
    expect(screen.getByRole("button", { name: "More…" })).toBeInTheDocument();
    expect(bar()).toBeNull();
    expect(screen.queryByRole("button", { name: "Settings" })).toBeNull(); // no gear under it
    menuSettings(); // ⋯ Settings is the same route: no second screen
    back();

    expect(await today()).toBeVisible();
    expect(current()).toEqual(["📝 Today"]);
    expect(sdk.backShown).toBe(false);
  });

  test("?open=listing opens the directory line over the Shala tab; Back goes to the Shala root", async () => {
    await launch("/?open=listing");

    await heading("SYC directory listing");
    expect(bar()).toBeNull();
    back();

    expect(await shala()).toBeInTheDocument();
  });

  test.each(["/?open=somewhere-new", "/?open=", "/?open=new-shala%20"])(
    "an unknown value opens Today: %s",
    async (search) => {
      await launch(search);

      expect(await today()).toBeInTheDocument();
      expect(current()).toEqual(["📝 Today"]);
      expect(screen.queryByRole("heading", { name: "🏛 Shala" })).toBeNull();
      expect(screen.queryByRole("heading", { name: "My practice" })).toBeNull();
      expect(sdk.backShown).toBe(false);
    },
  );
});

describe("a chunk that fails to load", () => {
  test("Settings that fails to load still has Back, to the screen it was opened over", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined); // React reports the caught error
    vi.doMock("./screens/settings/Settings", () => {
      throw new Error("Failed to fetch dynamically imported module");
    });
    await launch();
    await today();
    await go("practice");

    menuSettings();

    expect(
      await screen.findByText("Couldn't load this. Check your connection and try again."),
    ).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: "My practice" })).toBeNull();
    expect(bar()).toBeNull();
    back();

    expect(await practice()).toBeVisible();
    expect(screen.queryByText(/Couldn't load this/)).toBeNull();
    expect(sdk.backShown).toBe(false);
    vi.mocked(console.error).mockRestore();
  });

  test("shows the retry line and keeps the bar; the other tabs still work", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined); // React reports the caught error
    vi.doMock("./screens/stats/Stats", () => {
      throw new Error("Failed to fetch dynamically imported module");
    });
    await launch();
    await today();

    fireEvent.click(tab("practice"));

    expect(
      await screen.findByText("Couldn't load this. Check your connection and try again."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(current()).toEqual(["📊 Practice"]);

    fireEvent.click(tab("today"));
    expect(await today()).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: /^Today, / })).toBeInTheDocument();
    vi.mocked(console.error).mockRestore();
  });
});
