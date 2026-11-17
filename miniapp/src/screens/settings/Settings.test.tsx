import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";

import { useMe, type City, type Me, type NotificationSettings } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import type { SettingsFocus } from "../../shell/nav";
import { useShowLadies } from "../stats/cells";
import Settings from "./Settings";
import { TravelPrompt } from "./TravelPrompt";

// UI-06 stage 3 (spec §4, §10): Settings is the bot's five rows, each carrying its value, and
// five short pages. The rows are drawn from the cached account and ask the server nothing; a
// page reads what it shows. Every control of the former one long screen is found on its page.

const tg = vi.hoisted(() => ({ back: true }));

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  openLink: vi.fn(),
  confirmDestructive: vi.fn(() => Promise.resolve(false)),
  useBackButton: vi.fn(),
  // Without Telegram's own Back a screen draws a "‹ Back" link: the tests' way to go back.
  backButtonAvailable: vi.fn(() => tg.back),
}));

const ME: Me = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Ash",
  locale: "en",
  timezone: "Asia/Almaty",
  name_from_telegram: true,
  locale_from_telegram: true,
  hide_ladies: false,
  offer_check_in: true, // WH-01 part 2
  home_city_chosen: true,
};
const ALMATY: City = {
  slug: "almaty",
  name_en: "Almaty",
  name_ru: "Алматы",
  timezone: "Asia/Almaty",
};
const ASTANA: City = {
  slug: "astana",
  name_en: "Astana",
  name_ru: "Астана",
  timezone: "Asia/Almaty",
};
const SOCHI: City = { slug: "sochi", name_en: "Sochi", name_ru: "Сочи", timezone: "Europe/Moscow" };
const CITIES: City[] = [
  { slug: "mysuru", name_en: "Mysuru", name_ru: "Майсур", timezone: "Asia/Kolkata" },
  ALMATY,
  { slug: "bangkok", name_en: "Bangkok", name_ru: "Бангкок", timezone: "Asia/Bangkok" },
  SOCHI,
  { slug: "moscow", name_en: "Moscow", name_ru: "Москва", timezone: "Europe/Moscow" },
];
const SETTINGS: NotificationSettings = {
  moon: { offsets: [1, 7], at: "19:00:00" },
  quiet: { start: "22:00:00", end: "07:00:00" },
  daily_cap: 3,
  announcements: true,
  practice: { on: true, at: "20:00:00", days: [1, 2, 3, 4, 5, 7] },
  timezone: "Asia/Almaty",
};

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

let dayOffFails = false;
let meFails = false;
let teachers: unknown[] = [];
let settings: NotificationSettings = SETTINGS;
let feed: unknown = {};

function stubApi(): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request);
      const path = new URL(request.url).pathname;
      if (request.method === "PATCH" && path === "/api/v1/me") {
        if (meFails) return new Response(JSON.stringify({ code: "unavailable" }), { status: 503 });
        return json({ ...ME, ...(await request.clone().json()) });
      }
      if (request.method === "PATCH") return json(settings);
      if (path === "/api/v1/me/day-off") {
        if (dayOffFails)
          return new Response(JSON.stringify({ code: "unavailable" }), { status: 503 });
        const { day_off } = (await request.clone().json()) as { day_off: number[] };
        return json({
          day_off,
          practice_days: [1, 2, 3, 4, 5, 6, 7].filter((d) => !day_off.includes(d)),
        });
      }
      if (path === "/api/v1/me") return json({ ...ME, day_off: null });
      if (path === "/api/v1/moon/cities") return json(CITIES);
      if (path === "/api/v1/me/notification-settings") return json(settings);
      if (path === "/api/v1/me/moon-days") {
        return json({
          location: { slug: "mysuru", explicit: false },
          today: "2026-10-19",
          days: [],
        });
      }
      if (path === "/api/v1/me/links") return json({ teachers, students: [] });
      if (path === "/api/v1/me/shalas") return json([]); // SC-01
      if (path === "/api/v1/me/calendar-feed") return json(feed); // SC-06
      return json({});
    }),
  );
  return seen;
}

function renderWith(node: React.ReactNode, locale: Locale = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>{node}</L10nProvider>
    </QueryClientProvider>,
  );
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");

interface Mounted {
  client: QueryClient;
  onBack: ReturnType<typeof vi.fn<() => void>>;
}

/** Settings as the shell shows it: over the cached account, which a save updates at once. */
function mount(me: Me, options: { locale?: Locale; focus?: SettingsFocus } = {}): Mounted {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["me"], me);
  const onBack = vi.fn<() => void>();
  function Live() {
    return <Settings me={useMe().data ?? me} onBack={onBack} focus={options.focus} />;
  }
  render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={options.locale ?? me.locale}>
        <Live />
      </L10nProvider>
    </QueryClientProvider>,
  );
  return { client, onBack };
}

const title = (name: string) => screen.findByRole("heading", { level: 1, name });
/** The rows of the first screen, top to bottom, as they read. */
const rows = () =>
  within(screen.getByRole("main"))
    .getAllByRole("button")
    .map((b) => plain(b.textContent));
const row = (text: string) =>
  screen.getByRole("button", { name: (name) => plain(name).startsWith(text) });

/** Opens a page by its row and waits for its heading. */
async function open(me: Me, rowText: string, heading: string, locale?: Locale): Promise<Mounted> {
  const mounted = mount(me, locale ? { locale } : {});
  fireEvent.click(row(rowText));
  await title(heading);
  return mounted;
}
const openLanguage = (me: Me = ME) => open(me, "🗣 Language", "Language");
const openCity = (me: Me = ME) => open(me, me.home_city ? "🏙 My city" : "🕐 My time", "🏙 My city");
const openDayOff = (me: Me = ME) => open(me, "😌", "Day off");
const openReminders = (me: Me = ME) => open(me, "🔔 Reminders", "🔔 Reminders");
const openMore = (me: Me = ME) => open(me, "More…", "⚙️ More settings");

async function bodies(seen: Request[], method: string, path: string): Promise<unknown[]> {
  await vi.waitFor(() => {
    expect(seen.some((r) => r.method === method && new URL(r.url).pathname === path)).toBe(true);
  });
  return Promise.all(
    seen
      .filter((r) => r.method === method && new URL(r.url).pathname === path)
      .map((r) => r.clone().json() as Promise<unknown>),
  );
}
const asked = (seen: Request[]) => seen.map((r) => `${r.method} ${new URL(r.url).pathname}`);

function deviceZoneIs(zone: string) {
  const Real = Intl.DateTimeFormat;
  // A regular function, so it works with and without `new` like the real constructor.
  function Fake(locale?: string | string[], options?: Intl.DateTimeFormatOptions) {
    const format = new Real(locale, options);
    if (options === undefined) {
      const resolved = format.resolvedOptions();
      format.resolvedOptions = () => ({ ...resolved, timeZone: zone });
    }
    return format;
  }
  vi.spyOn(Intl, "DateTimeFormat").mockImplementation(
    Fake as unknown as typeof Intl.DateTimeFormat,
  );
}

// The rows prefetch their five pages; loading them once here keeps every test's first open
// quick (the transform cache outlives a test).
beforeAll(async () => {
  await Promise.all([
    import("./pages/Language"),
    import("./pages/City"),
    import("./pages/DayOff"),
    import("./pages/Reminders"),
    import("./pages/More"),
  ]);
}, 60_000);

/** The page's scroll (jsdom has none). */
const scrollTo = vi.fn();

beforeEach(() => {
  scrollTo.mockClear();
  vi.stubGlobal("scrollTo", scrollTo);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
  tg.back = true;
  dayOffFails = false;
  meFails = false;
  teachers = [];
  settings = SETTINGS;
  feed = {};
});

describe("the first screen: the bot's five rows, each with its value", () => {
  it("is five rows and a quiet Guide, drawn from the account without asking the server", async () => {
    const seen = stubApi();
    mount({ ...ME, home_city: ALMATY, day_off: [7] });

    expect(await title("Settings")).toBeInTheDocument();
    expect(rows()).toEqual([
      "🗣 Language: As in Telegram",
      "🏙 My city: Almaty", // my own city: no offset (ADR-0044)
      "😌 Day off: Sunday",
      "🔔 Reminders",
      "More…",
      "📖 Guide",
    ]);
    expect(screen.getAllByRole("heading")).toHaveLength(1);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    await act(async () => {
      await new Promise((done) => setTimeout(done, 20));
    });
    expect(asked(seen)).toEqual([]);
  });

  it("asks only once a page opens, and only what that page shows", async () => {
    const seen = stubApi();
    await openReminders();

    await screen.findByRole("checkbox", { name: "🔔 Ask me once a day" });
    expect([...new Set(asked(seen))].sort()).toEqual([
      "GET /api/v1/me/links",
      "GET /api/v1/me/notification-settings",
      "GET /api/v1/me/shalas",
    ]);
  });

  it.each([
    ["Telegram's language", { locale_from_telegram: true }, "🗣 Language: As in Telegram"],
    ["a chosen language", { locale_from_telegram: false }, "🗣 Language: English"],
    ["a city", { home_city: ASTANA }, "🏙 My city: Astana"],
    ["no city yet", { home_city_chosen: false }, "🏙 My city? 🕐 Almaty (UTC+5)"],
    ["a city that isn't listed", { home_city_chosen: true }, "🕐 My time: Almaty (UTC+5)"],
    ["no clock yet", { timezone: null, home_city_chosen: false }, "🏙 My city? 🕐 not known yet"],
    ["one day off", { day_off: [6] }, "😌 Day off: Saturday"],
    ["two days off", { day_off: [7, 6] }, "😌 Days off: Saturday, Sunday"],
    ["no fixed day off", { day_off: [] }, "😌 No fixed day off"],
    ["a day off not chosen", { day_off: null }, "😌 Day off: not chosen"],
  ] as [string, Partial<Me>, string][])("says %s on its row", (_name, patch, text) => {
    stubApi();
    mount({ ...ME, ...patch });

    expect(rows()).toContain(text);
    expect(rows()).toHaveLength(6);
  });

  it("reads the same in Russian, in the bot's words", () => {
    stubApi();
    mount({
      ...ME,
      locale: "ru",
      locale_from_telegram: false,
      home_city: ALMATY,
      day_off: [6, 7],
    });

    expect(rows()).toEqual([
      "🗣 Язык: Русский",
      "🏙 Мой город: Алматы",
      "😌 Выходные: суббота, воскресенье",
      "🔔 Напоминания",
      "Ещё…",
      "📖 Справка",
    ]);
  });

  // UI-06 stage 2: the tour is retired (Q332), and teachers, students and shalas are the
  // Shala tab (Q300). Neither has a row here.
  it("has no quick tour row and no Teachers and students row", () => {
    stubApi();
    mount(ME);

    expect(screen.queryByRole("button", { name: /tour/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Teachers and students/ })).toBeNull();
  });

  it.each([
    ["en", "📖 Guide", "https://tristhana.app/"],
    ["ru", "📖 Справка", "https://tristhana.app/ru/"],
  ] as const)(
    "opens the guide in the person's language from the last row (UI-05, %s)",
    async (locale, label, url) => {
      stubApi();
      const { openLink } = await import("../../telegram");
      mount({ ...ME, locale });

      expect(rows().at(-1)).toBe(label);
      fireEvent.click(screen.getByRole("button", { name: label }));
      expect(openLink).toHaveBeenLastCalledWith(url);
    },
  );
});

describe("a page is a layer over the rows", () => {
  it("takes the place of the rows and the focus; Back returns to the row that opened it", async () => {
    tg.back = false; // the pages draw their own "‹ Back"
    stubApi();
    const { onBack } = mount(ME);
    const opener = row("🔔 Reminders");

    fireEvent.click(opener);

    expect(await title("🔔 Reminders")).toHaveFocus();
    expect(screen.queryByRole("heading", { level: 1, name: "Settings" })).toBeNull();
    expect(opener).not.toBeVisible(); // hidden, not gone
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 0 });
    fireEvent.click(screen.getByRole("button", { name: "‹ Back" }));

    expect(await title("Settings")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "🔔 Reminders" })).toBeNull();
    expect(opener).toHaveFocus();
    expect(onBack).not.toHaveBeenCalled(); // Settings stays open
  });

  it.each([
    ["day-off", "Day off"],
    ["remind", "🔔 Reminders"],
  ] as const)("focus=%s opens its page, and Back there closes Settings", async (focus, heading) => {
    tg.back = false;
    stubApi();
    const { onBack } = mount(ME, { focus });

    expect(await title(heading)).toHaveFocus();
    expect(screen.queryByRole("heading", { level: 1, name: "Settings" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "‹ Back" }));

    expect(onBack).toHaveBeenCalledOnce();
    expect(screen.queryByRole("heading", { level: 1, name: "Settings" })).toBeNull();
  });

  it("a saved value shows on its row as soon as the page closes", async () => {
    tg.back = false;
    stubApi();
    await openDayOff({ ...ME, day_off: null });

    fireEvent.click(screen.getByRole("button", { name: (n) => plain(n) === "Sun" }));
    await screen.findByRole("button", { name: (n) => plain(n) === "Sun", pressed: true });
    fireEvent.click(screen.getByRole("button", { name: "‹ Back" }));

    await title("Settings");
    expect(rows()).toContain("😌 Day off: Sunday");
  });
});

describe("Language", () => {
  it("is three choices, one per row, with the chosen one marked", async () => {
    stubApi();
    await openLanguage();

    const group = screen.getByRole("group", { name: "Language" });
    expect(
      within(group)
        .getAllByRole("button")
        .map((b) => [b.textContent, b.getAttribute("aria-pressed")]),
    ).toEqual([
      ["As in Telegram", "true"],
      ["English", "false"],
      ["Русский", "false"],
    ]);
  });

  it("switches the language and back to Telegram's", async () => {
    const seen = stubApi();
    await openLanguage({ ...ME, locale_from_telegram: false });

    expect(screen.getByRole("button", { name: "English", pressed: true })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "As in Telegram" }));

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ locale: null }]);
  });

  it("says so when the save fails", async () => {
    meFails = true;
    stubApi();
    await openLanguage();

    fireEvent.click(screen.getByRole("button", { name: "Русский" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't save");
  });
});

describe("TravelPrompt", () => {
  it("offers to switch when the phone's offset differs, and remembers Keep", async () => {
    deviceZoneIs("Asia/Bangkok");
    stubApi();
    const { unmount } = renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" />);

    expect(
      await screen.findByText(
        (_, el) =>
          el?.tagName === "P" &&
          plain(el.textContent) ===
            "Your phone is on Bangkok (UTC+7) time. Reminders use Almaty (UTC+5).",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: (n) => plain(n) === "Keep Almaty" }));
    unmount();

    renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("switches the zone on request", async () => {
    deviceZoneIs("Asia/Bangkok");
    const seen = stubApi();
    renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" />);

    fireEvent.click(
      await screen.findByRole("button", { name: (n) => plain(n) === "Switch to Bangkok" }),
    );

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ timezone: "Asia/Bangkok" }]);
  });

  it("names the home city as 'here'", async () => {
    deviceZoneIs("Asia/Bangkok");
    stubApi();
    const astana: City = {
      slug: "astana",
      name_en: "Astana",
      name_ru: "Астана",
      timezone: "Asia/Almaty",
    };
    renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" home={astana} />);

    expect(
      await screen.findByRole("button", { name: (n) => plain(n) === "Keep Astana" }),
    ).toBeInTheDocument();
  });

  it("stays quiet for the same clock under another name", () => {
    deviceZoneIs("Europe/Kiev");
    stubApi();
    renderWith(<TravelPrompt zone="Europe/Kyiv" locale="en" />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("says nothing when the phone reports UTC", () => {
    deviceZoneIs("UTC");
    stubApi();
    renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps the prompt and explains when the switch fails", async () => {
    deviceZoneIs("Asia/Bangkok");
    stubApi();
    vi.stubGlobal(
      "fetch",
      vi.fn((request: Request) =>
        request.method === "PATCH"
          ? new Response(JSON.stringify({ code: "unavailable" }), { status: 503 })
          : json(new URL(request.url).pathname === "/api/v1/moon/cities" ? CITIES : {}),
      ),
    );
    renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" />);

    fireEvent.click(
      await screen.findByRole("button", { name: (n) => plain(n) === "Switch to Bangkok" }),
    );

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});

describe("My city (MD-04)", () => {
  const select = () => screen.findByRole("combobox", { name: "Which city do you live in?" });

  it("lists every city, plus 'not listed' that offers the phone's time or UTC", async () => {
    deviceZoneIs("Asia/Bangkok");
    const seen = stubApi();
    await openCity({ ...ME, home_city: ALMATY });
    const cities = await select();
    expect([...cities.querySelectorAll("option")].map((o) => o.value)).toEqual([
      "",
      "almaty",
      "bangkok",
      "moscow",
      "mysuru",
      "sochi",
      "-",
    ]);
    expect(screen.queryByRole("button", { name: /Use my phone's time/ })).not.toBeInTheDocument();

    fireEvent.change(cities, { target: { value: "-" } });
    expect(cities).toHaveValue("-"); // stays on "not listed" while the chips are shown
    expect(screen.getByRole("button", { name: "UTC (no daylight saving)" })).toBeInTheDocument();
    fireEvent.click(
      await screen.findByRole("button", {
        name: (n) => plain(n).startsWith("Use my phone's time: Bangkok (UTC+7)"),
      }),
    );

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([
      { home_city: null, timezone: "Asia/Bangkok" },
    ]);
  });

  it("marks the stored city, not another one in its zone, and saves the slug", async () => {
    const seen = stubApi();
    await openCity({ ...ME, timezone: "Europe/Moscow", home_city: SOCHI });
    const cities = await select();

    expect(cities).toHaveValue("sochi"); // the bug: Moscow used to be marked
    fireEvent.change(cities, { target: { value: "moscow" } });

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ home_city: "moscow" }]);
  });

  it("labels the time with the city's name", async () => {
    stubApi();
    await openCity({ ...ME, home_city: ASTANA });

    // My own city: its name, no offset (ADR-0044).
    expect(
      screen.getByText(
        (_, el) => el?.tagName === "P" && /^\d\d:\d\d Astana$/.test(plain(el.textContent)),
      ),
    ).toBeInTheDocument();
  });

  it("says what the clock is, offset and all, while no city is chosen", async () => {
    stubApi();
    await openCity();

    expect(
      screen.getByText(
        (_, el) =>
          el?.tagName === "P" && /^\d\d:\d\d Almaty \(UTC\+5\)$/.test(plain(el.textContent)),
      ),
    ).toBeInTheDocument();
  });

  // The nudge and its "Not now" are gone (UI-06 stage 3): the row asks, as in the bot.
  it("has no nudge: the row asks, and picking a city answers", async () => {
    const seen = stubApi();
    const unanswered = { ...ME, home_city_chosen: false };
    await open(unanswered, "🏙 My city? 🕐 Almaty (UTC+5)", "🏙 My city");
    const cities = await select();

    expect(screen.queryByText(/Pick your city if you like/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Not now" })).toBeNull();
    expect(cities).toHaveValue(""); // nothing chosen, and "not listed" is not assumed
    fireEvent.change(cities, { target: { value: "almaty" } });

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ home_city: "almaty" }]);
  });

  it("explains the clock, and credits the map where the location is talked about", async () => {
    stubApi();
    await openCity();

    expect(screen.getByText(/Reminders and times follow your city's clock/)).toBeInTheDocument();
    expect(screen.getByText(/© OpenStreetMap contributors \(ODbL\)/)).toBeInTheDocument();
  });

  it("shows the old city again when the save fails", async () => {
    meFails = true;
    stubApi();
    const { client } = await openCity({ ...ME, home_city: SOCHI, timezone: "Europe/Moscow" });
    const cities = await select();

    fireEvent.change(cities, { target: { value: "almaty" } });

    expect(await screen.findAllByRole("alert")).not.toHaveLength(0);
    expect(client.getQueryData<Me>(["me"])?.home_city?.slug).toBe("sochi");
    expect(cities).toHaveValue("sochi");
  });
});

describe("Day off (PR-09)", () => {
  it("starts with nothing pressed and takes up to two days off", async () => {
    const seen = stubApi();
    await openDayOff({ ...ME, day_off: null });
    const group = screen.getByRole("group", { name: "Day off" });
    const chip = (name: string) =>
      within(group).getByRole("button", { name: (n) => plain(n) === name });
    expect(within(group).getAllByRole("button")).toHaveLength(8); // seven days and "no fixed"
    expect(within(group).queryAllByRole("button", { pressed: true })).toHaveLength(0);
    expect(screen.getByText(/Past weeks show them too/)).toBeInTheDocument();

    fireEvent.click(chip("Sun"));
    await vi.waitFor(() => {
      expect(chip("Sun")).toHaveAttribute("aria-pressed", "true");
    });
    fireEvent.click(chip("Sat"));
    await vi.waitFor(() => {
      expect(chip("Sat")).toHaveAttribute("aria-pressed", "true");
    });

    expect(chip("Mon")).toBeDisabled(); // a third day off waits until one is unpressed
    expect(await bodies(seen, "PUT", "/api/v1/me/day-off")).toEqual([
      { day_off: [7] },
      { day_off: [6, 7] },
    ]);
  });

  it("says in two short sentences what a day off does", async () => {
    stubApi();
    await openDayOff({ ...ME, day_off: [7] });

    expect(plain(screen.getByText(/Pick one or two/).textContent)).toBe(
      "Pick one or two. They show as rest, and practice reminders skip them. A change applies from today.",
    );
  });

  it("takes 'No fixed day off'", async () => {
    const seen = stubApi();
    await openDayOff({ ...ME, day_off: [7] });

    fireEvent.click(screen.getByRole("button", { name: "No fixed day off" }));

    expect(await bodies(seen, "PUT", "/api/v1/me/day-off")).toEqual([{ day_off: [] }]);
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "No fixed day off" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    });
  });

  it("rolls back when the save fails", async () => {
    dayOffFails = true;
    stubApi();
    await openDayOff({ ...ME, day_off: null });
    const group = screen.getByRole("group", { name: "Day off" });
    fireEvent.click(within(group).getByRole("button", { name: "No fixed day off" }));

    expect(await screen.findAllByText("Couldn't save. Try again in a moment.")).not.toHaveLength(0);
    expect(within(group).queryAllByRole("button", { pressed: true })).toHaveLength(0);
  });
});

describe("Reminders", () => {
  it("names the place of its times once, at the top (ADR-0044)", async () => {
    stubApi();
    await openReminders({ ...ME, home_city: ASTANA });
    await screen.findByRole("button", { name: "20:00", pressed: true });

    // My own zone: the place, no offset; no other line on the page repeats it.
    expect(
      screen.getAllByText((_, el) => /Astana/.test(el?.textContent ?? "") && el?.tagName === "P"),
    ).toHaveLength(1);
    expect(plain(screen.getByText(/^🕐 Times:/).textContent)).toBe("🕐 Times: Astana");
  });

  it("has the practice reminder first: a switch, the time, the days it comes on", async () => {
    const seen = stubApi();
    await openReminders();

    const toggle = await screen.findByRole("checkbox", { name: "🔔 Ask me once a day" });
    expect(toggle).toBeChecked();
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "🧘 Practice reminder",
      "🌙 Moon day",
    ]);
    expect(
      screen.getByText(
        (t) =>
          plain(t) ===
          "On your practice days: Mon, Tue, Wed, Thu, Fri, Sun. Change them under Day off.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "18:00" }));
    fireEvent.click(toggle);

    expect(await bodies(seen, "PATCH", "/api/v1/me/notification-settings")).toEqual([
      { practice: { at: "18:00:00" } },
      { practice: { on: false } },
    ]);
  });

  it("has the moon reminders: days before and the time, a tap sends only what was tapped", async () => {
    const seen = stubApi();
    await openReminders();
    const before = await screen.findByRole("group", { name: "Remind me before" });

    expect(
      within(before)
        .getAllByRole("button")
        .map((b) => [plain(b.textContent), b.getAttribute("aria-pressed")]),
    ).toEqual([
      ["7 days", "true"],
      ["3 days", "false"],
      ["1 day", "true"],
    ]);
    fireEvent.click(within(before).getByRole("button", { name: (n) => plain(n) === "3 days" }));
    // 19:00 is the moon reminder's own time; 21:00 is free, 07:00 would fall in quiet hours.
    const moon = screen.getByRole("region", { name: "🌙 Moon day" });
    expect(within(moon).getByRole("button", { name: "19:00" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(moon).getByRole("button", { name: "07:00" })).toBeEnabled(); // quiet ends at 07:00
    fireEvent.click(within(moon).getByRole("button", { name: "21:00" }));

    expect(await bodies(seen, "PATCH", "/api/v1/me/notification-settings")).toEqual([
      { moon: { offsets: [1, 7, 3] } },
      { moon: { at: "21:00:00" } },
    ]);
  });

  it("keeps quiet hours and the daily limit in a fold that says what is set", async () => {
    const seen = stubApi();
    await openReminders();
    const fold = await screen.findByRole("button", { name: "Quiet hours" });

    expect(fold).toHaveAttribute("aria-expanded", "false");
    expect(plain(fold.textContent)).toBe(
      "Quiet hours🔕 Quiet hours 22:00–07:00 · at most 3 messages a day",
    );
    expect(screen.queryByRole("combobox")).toBeNull();
    fireEvent.click(fold);

    // It won't let quiet hours swallow an active reminder.
    const from = screen.getByRole("combobox", { name: "Quiet from" });
    const option = (h: string) => from.querySelector(`option[value="${h}"]`) as HTMLOptionElement;
    expect(from).toHaveValue("22:00");
    expect(screen.getByRole("combobox", { name: "Quiet until" })).toHaveValue("07:00");
    expect(option("19:00").disabled).toBe(true); // 19:00 moon and 20:00 practice
    expect(option("21:00").disabled).toBe(false);
    fireEvent.change(from, { target: { value: "21:00" } });
    const cap = screen.getByRole("group", { name: (n) => plain(n) === "At most 3 messages a day" });
    fireEvent.click(within(cap).getByRole("button", { name: "2" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "No quiet hours" }));

    expect(await bodies(seen, "PATCH", "/api/v1/me/notification-settings")).toEqual([
      { quiet: { start: "21:00:00", end: "07:00:00" } },
      { daily_cap: 2 },
      { quiet: { start: "00:00:00", end: "00:00:00" } },
    ]);
  });

  it("says 'No quiet hours' on the closed fold when there are none", async () => {
    settings = { ...SETTINGS, quiet: { start: "00:00:00", end: "00:00:00" }, daily_cap: 1 };
    stubApi();
    await openReminders();
    const fold = await screen.findByRole("button", { name: "Quiet hours" });

    expect(plain(fold.textContent)).toBe("Quiet hours🔕 No quiet hours · at most 1 message a day");
    fireEvent.click(fold);
    expect(screen.getByRole("checkbox", { name: "No quiet hours" })).toBeChecked();
  });

  it("says once that reminders wait for a time zone, and shows no times", async () => {
    stubApi();
    await open({ ...ME, timezone: null }, "🔔 Reminders", "🔔 Reminders");
    await screen.findByRole("checkbox", { name: "🔔 Ask me once a day" });

    expect(screen.getAllByText(/once your time zone is known/)).toHaveLength(1);
    expect(screen.queryByText(/^🕐 Times:/)).toBeNull();
    expect(screen.queryByRole("button", { name: /^\d\d:00$/ })).toBeNull();
    expect(
      screen.queryByRole("button", { name: (name) => /^\d+ days?$/.test(plain(name)) }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Quiet hours" })).toBeNull();
  });

  it("has the NT-03 announcements switch once there is a teacher, off = false, on = null", async () => {
    teachers = [{ id: "t1", name: "Anna", primary: true, primary_chosen: false, linked_at: "x" }];
    const seen = stubApi();
    await openReminders();

    const toggle = await screen.findByRole("checkbox", {
      name: "📣 Announcements from teachers and shalas",
    });
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);
    expect(await bodies(seen, "PATCH", "/api/v1/me/notification-settings")).toContainEqual({
      announcements: false,
    });
    fireEvent.click(toggle);
    await vi.waitFor(async () => {
      expect(await bodies(seen, "PATCH", "/api/v1/me/notification-settings")).toEqual([
        { announcements: false },
        { announcements: null },
      ]);
    });
    expect(toggle).toBeChecked();
  });

  it("has no announcements switch with no teacher or shala", async () => {
    stubApi();
    await openReminders();
    await screen.findByRole("checkbox", { name: "🔔 Ask me once a day" });

    expect(
      screen.queryByRole("checkbox", { name: "📣 Announcements from teachers and shalas" }),
    ).not.toBeInTheDocument();
  });
});

describe("More", () => {
  it("has the name as its first field, then Your log and Privacy", async () => {
    stubApi();
    await openMore();
    await screen.findByRole("combobox");

    const main = screen.getByRole("main");
    expect(main.querySelector("input, select, button")).toBe(
      screen.getByRole("textbox", { name: "Name" }),
    );
    expect(
      within(main)
        .getAllByRole("heading")
        .map((h) => h.textContent),
    ).toEqual(["⚙️ More settings", "Your log", "Privacy", "📦 My data"]);
  });

  it("saves a name on blur, and blank goes back to the Telegram name", async () => {
    const seen = stubApi();
    await openMore();
    const name = screen.getByRole("textbox", { name: "Name" });
    expect(name).toHaveAttribute("placeholder", "Ash");
    expect(name).toHaveAccessibleDescription(/Leave it empty to use your Telegram name/);

    fireEvent.change(name, { target: { value: "  Anna 🧘 " } });
    fireEvent.blur(name);

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ display_name: "Anna 🧘" }]);
  });

  it("offers 'Same as my city' first in the moon calendar picker, with where the city comes from", async () => {
    const seen = stubApi();
    await openMore({ ...ME, home_city: ALMATY });
    const select = await screen.findByRole("combobox", {
      name: (n) => plain(n) === "🌙 Moon days · 📍 Mysuru",
    });

    const first = select.querySelector("option");
    expect(first?.textContent && plain(first.textContent)).toBe("Same as my city (Almaty)");
    expect(screen.queryByText(/lunar day at sunrise/)).toBeNull(); // that note is on the Moon screen
    fireEvent.change(select, { target: { value: "almaty" } });

    expect(await bodies(seen, "PUT", "/api/v1/me/moon-location")).toEqual([{ slug: "almaty" }]);
  });

  it("keeps what others see in a closed fold: the two privacy texts", async () => {
    stubApi();
    await openMore();
    const fold = screen.getByRole("button", { name: "🔒 What others see" });

    expect(fold).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/stored encrypted/)).toBeNull();
    fireEvent.click(fold);

    expect(screen.getByText(/stored encrypted/)).toBeInTheDocument();
    expect(screen.getByText(/^Your log is yours\./)).toBeInTheDocument();
    expect(screen.queryByText(/OpenStreetMap/)).toBeNull(); // on the My city page
  });

  it("keeps the calendar subscription in a fold, absent when the server offers no links", async () => {
    feed = { on: false, available: true, url: null, google_url: null, subscribe_url: null };
    const seen = stubApi();
    await openMore();
    const fold = await screen.findByRole("button", { name: "📅 Add to calendar" });

    expect(fold).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "📅 Create my link" })).toBeNull();
    fireEvent.click(fold);
    fireEvent.click(screen.getByRole("button", { name: "📅 Create my link" }));

    await vi.waitFor(() => {
      expect(asked(seen)).toContain("POST /api/v1/me/calendar-feed");
    });
    await screen.findByRole("button", { name: "📅 Create my link" }); // settled
  });

  it("has no calendar fold when the server offers no links", async () => {
    stubApi();
    await openMore();
    await screen.findByRole("combobox");

    expect(screen.queryByRole("button", { name: "📅 Add to calendar" })).toBeNull();
  });

  it("ends with My data: download and delete", async () => {
    stubApi();
    await openMore();

    const data = screen.getByRole("region", { name: "📦 My data" });
    expect(within(data).getByRole("button", { name: "⬇️ Download my data" })).toBeInTheDocument();
    expect(within(data).getByRole("button", { name: /Delete/ })).toBeInTheDocument();
    expect(screen.getByRole("main").lastElementChild).toBe(data);
  });
});

describe("Show 🌸 on my calendar (the device switch, QB)", () => {
  const toggle = () => screen.getByRole("checkbox", { name: "Show 🌸 on my calendar" });

  it("lives in More only, is off until chosen, and the Practice tab follows it at once", async () => {
    stubApi();
    function Probe() {
      return <output>{useShowLadies() ? "marked" : "rest"}</output>;
    }
    render(<Probe />);
    mount(ME);
    expect(screen.queryByRole("checkbox")).toBeNull(); // not on the first screen
    fireEvent.click(row("More…"));
    await title("⚙️ More settings");

    expect(toggle()).not.toBeChecked();
    expect(toggle()).toHaveAccessibleDescription(
      "On this phone only. While it's off, these days look like rest.",
    );
    expect(screen.getByRole("status")).toHaveTextContent("rest");
    fireEvent.click(toggle());

    expect(toggle()).toBeChecked();
    expect(localStorage.getItem("stats.showLadies")).toBe("1");
    expect(screen.getByRole("status")).toHaveTextContent("marked");
  });

  it("reads the stored choice, and sends nothing to the server", async () => {
    localStorage.setItem("stats.showLadies", "1");
    const seen = stubApi();
    await openMore();

    expect(toggle()).toBeChecked();
    fireEvent.click(toggle());

    expect(localStorage.getItem("stats.showLadies")).toBe("0");
    expect(seen.filter((r) => r.method !== "GET")).toEqual([]);
  });
});

describe("Hide the 🌸 button (WH-01 part 2)", () => {
  const shown = { ...ME, hide_ladies: false } as Me;
  const toggle = () =>
    screen.getByRole("checkbox", {
      name: (n) => plain(n) === "Show the 🌸 Ladies' holiday button",
    });

  it("is on by default, explains itself, and saves at once", async () => {
    const seen = stubApi();
    await openMore(shown);

    const box = toggle();
    expect(box).toBeChecked();
    expect(box).toHaveAccessibleDescription(
      "In the bot and here. Days you already logged stay as they are.",
    );
    fireEvent.click(box);

    expect(box).not.toBeChecked(); // optimistic
    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ hide_ladies: true }]);
  });

  it("reads the stored choice", async () => {
    stubApi();
    await openMore({ ...ME, hide_ladies: true });

    expect(toggle()).not.toBeChecked();
  });

  it("rolls back when the save fails", async () => {
    meFails = true;
    stubApi();
    await openMore(shown);
    const box = toggle();

    fireEvent.click(box);

    await vi.waitFor(() => {
      expect(box).toBeChecked();
    });
  });

  it("is separate from the device-only 🌸 days switch", async () => {
    stubApi();
    await openMore(shown);
    fireEvent.click(toggle());

    expect(screen.getByRole("checkbox", { name: "Show 🌸 on my calendar" })).not.toBeChecked();
    expect(localStorage.getItem("stats.showLadies")).not.toBe("1");
  });
});

describe("Show “How do you feel?” after practice (PR-06, Q313)", () => {
  const offered = { ...ME, offer_check_in: true } as Me;
  const toggle = () =>
    screen.getByRole("checkbox", { name: "Show “How do you feel?” after practice" });

  it("is on by default, explains itself, and saves at once", async () => {
    const seen = stubApi();
    await openMore(offered);

    const box = toggle();
    expect(box).toBeChecked();
    expect(box).toHaveAccessibleDescription(
      "Mood, energy and effort on a day you practiced. A check-in you already made stays and can be changed.",
    );
    fireEvent.click(box);

    expect(box).not.toBeChecked(); // optimistic
    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ offer_check_in: false }]);
  });

  it("reads the stored choice and turns it back on", async () => {
    const seen = stubApi();
    await openMore({ ...offered, offer_check_in: false });

    const box = toggle();
    expect(box).not.toBeChecked();
    fireEvent.click(box);

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ offer_check_in: true }]);
  });

  it("rolls back when the save fails", async () => {
    meFails = true;
    stubApi();
    await openMore(offered);
    const box = toggle();

    fireEvent.click(box);

    await vi.waitFor(() => {
      expect(box).toBeChecked();
    });
  });

  it("is in Russian too", async () => {
    stubApi();
    await open({ ...offered, locale: "ru" }, "Ещё…", "⚙️ Ещё настройки");

    expect(
      screen.getByRole("checkbox", { name: "Показывать «Как самочувствие?» после практики" }),
    ).toBeChecked();
  });
});
