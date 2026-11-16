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
    mainButton: { mount: safe(), setParams: safe(), onClick: () => () => undefined },
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
const QR = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkAAAACklEQVR4AQ==";

/** Who this person is, per test. Nobody by default: no teacher, no student, no shala. */
let myShalas: unknown[] = [];
let links: { teachers: unknown[]; students: unknown[] } = { teachers: [], students: [] };
let seen: Request[] = [];
/** What GET /me/next-steps offers, and today's classes in My schedule (UI-06). */
let nextSteps: { kind: string; shala_id: string | null }[] = [];
let classesToday: unknown[] = [];
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
  if (path === "/api/v1/me" || path === "/api/v1/me/device-timezone") return json(ME);
  if (path === "/api/v1/me/stats") return json(STATS);
  if (path === "/api/v1/me/badges") return json({ badges: [] });
  if (path === "/api/v1/health") return json({ version: "1", commit: "abcdef0" });
  if (path === "/api/v1/moon/cities") return json([]);
  if (path === "/api/v1/me/next-steps") return json({ steps: nextSteps });
  if (path === "/api/v1/me/links") return json(links);
  if (path === "/api/v1/me/shalas") return json(myShalas);
  if (path === "/api/v1/me/invite")
    return json({ url: "https://t.me/tristhana_bot?start=t_a", qr: QR });
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

beforeEach(() => {
  localStorage.clear();
  myShalas = [];
  links = { teachers: [], students: [] };
  seen = [];
  nextSteps = [];
  classesToday = [];
  sdk.haptic.length = 0;
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

  test("the day-off link on Practice opens Settings, and Back returns to Practice", async () => {
    await launch();
    await today();
    await go("practice");

    fireEvent.click(await screen.findByRole("button", { name: "😌 Set your weekly day off" }));

    await settings();
    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalled();
    });
    back();
    expect(await practice()).toBeInTheDocument();
  });
});

describe("Back or tabs, never both", () => {
  test("the bar is absent inside a pushed screen and returns on the root", async () => {
    await launch();
    await today();

    fireEvent.click(await screen.findByRole("button", { name: /New moon/ }));

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
    fireEvent.click(await screen.findByRole("button", { name: "Add a note" }));
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

    fireEvent.click(await screen.findByRole("button", { name: /New moon \(Amavasya\)/ }));

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

  test("the reminder step opens the reminder setting; Back returns to Today", async () => {
    nextSteps = [
      { kind: "reminder", shala_id: null },
      { kind: "position", shala_id: null },
    ];
    await launch();
    await today();

    fireEvent.click(await screen.findByRole("button", { name: "Set the reminder" }));

    await settings();
    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalled(); // the reminder card, once it is there
    });
    expect(scrollIntoView.mock.contexts[0]).toHaveProperty("id", "remind");
    back();
    expect(await today()).toBeInTheDocument();
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

  test.each(["add_class", "invite_shala_students"])(
    "%s opens that shala's card on the Shala tab",
    async (kind) => {
      myShalas = [{ ...myShala("staff"), owner: true }];
      nextSteps = [{ kind, shala_id: SHALA }];
      await launch();
      await today();

      fireEvent.click(
        await screen.findByRole("button", {
          name: kind === "add_class" ? "Add a class" : "Invite students",
        }),
      );

      await waitFor(() => {
        expect(asked(`/api/v1/shalas/${SHALA}`)).toBe(true);
      });
    },
  );

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

    const row = await screen.findByRole("button", { name: /Mysore/ });
    expect(plain(row.textContent)).toBe("🗓 07:00 Almaty · Mysore · Ashtanga Almaty");
    fireEvent.click(row);

    await heading("🗓 My schedule");
    expect(bar()).toBeNull();
  });
});

describe("the empty Shala tab", () => {
  test("nobody yet: one plain line and two quiet starts, no empty cards", async () => {
    await launch();
    await today();
    await go("shala");

    expect(
      await screen.findByText(
        "Nobody here yet. To add a teacher or join a shala, open the link they send you.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Invite students" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Shala and classes" })).toBeInTheDocument();
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
  test("shows the retry line and keeps the bar; the other tabs still work", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined); // React reports the caught error
    vi.doMock("./screens/stats/Stats", () => {
      throw new Error("Failed to fetch dynamically imported module");
    });
    await launch();
    await today();

    fireEvent.click(tab("practice"));

    expect(
      await screen.findByText("Couldn't load this screen. Check your connection and try again."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(current()).toEqual(["📊 Practice"]);

    fireEvent.click(tab("today"));
    expect(await today()).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: /^Today, / })).toBeInTheDocument();
    vi.mocked(console.error).mockRestore();
  });
});
