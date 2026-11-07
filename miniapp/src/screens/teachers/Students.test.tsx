import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import appSource from "../../App.tsx?raw";
import homeSource from "../Home.tsx?raw";
import linksSource from "../settings/Links.tsx?raw";

// The app's tsconfig has no Node types, and Vitest blanks CSS imports, `?raw` included.
declare const process: {
  env: { TZ?: string };
  cwd: () => string;
  getBuiltinModule: (id: "node:fs") => {
    readFileSync: (path: string, encoding: "utf8") => string;
  };
};

// ST-06 (spec §2, §5, §8): the neutral Home row, the list (name and today's mark, nothing else),
// the card (7 days, last asana, one quiet note), Show more, a 404 falling back to the list, and
// Remove dropping the cache. Driven through App, so the file doesn't care how the screen is
// reached. App keeps one QueryClient per module, so each test imports a fresh App.

const telegram = vi.hoisted(() => ({
  openSettings: vi.fn() as () => void,
  back: vi.fn() as () => void,
  confirmDestructive: vi.fn<(message: string, ok: string, cancel: string) => Promise<boolean>>(),
}));
const { confirmDestructive } = telegram;

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: (onBack: () => void) => {
    telegram.back = onBack;
  },
  backButtonAvailable: vi.fn(() => true),
  markReady: vi.fn(),
  useMainButton: vi.fn(),
  useSettingsButton: (open: () => void) => {
    telegram.openSettings = open;
  },
  enableClosingConfirmation: vi.fn(),
  disableClosingConfirmation: vi.fn(),
  confirmDestructive: telegram.confirmDestructive,
  allowBotMessages: vi.fn(() => Promise.resolve(false)),
  closeApp: vi.fn(),
  openTelegramLink: vi.fn(),
}));

const TODAY = "2026-11-07";
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
const ANNA = "00000000-0000-0000-0000-0000000000a1";
const BORIS = "00000000-0000-0000-0000-0000000000a2";
const MARIA = "00000000-0000-0000-0000-0000000000a3";
const CATALOG = {
  version: "v1",
  check_in_tags: [],
  milestone_items: [],
  series: [
    {
      slug: "primary",
      number: 1,
      name_en: "Primary series",
      name_ru: "Первая серия",
      halves_split: "navasana",
      stops: [{ key: "navasana", latin: "Navasana", ru: "Навасана" }],
    },
    {
      slug: "intermediate",
      number: 2,
      name_en: "Intermediate series",
      name_ru: "Вторая серия",
      halves_split: null,
      stops: [{ key: "kapotasana", latin: "Kapotasana", ru: "Капотасана" }],
    },
  ],
};

type State = "practiced" | "rest" | null;
interface Row {
  id: string;
  name: string | null;
  today: State;
}
interface Day {
  date: string;
  state: State;
  length: { series: string[]; end: string | null; first_part: null } | null;
}
interface Card {
  id: string;
  name: string | null;
  days: Day[];
  last_asana: { series: string | null; last: string | null } | null;
  quiet: boolean;
}

const row = (id: string, name: string | null, today: State = null): Row => ({ id, name, today });
const ROWS = [row(ANNA, "Anna", "practiced"), row(BORIS, "Dmitry"), row(MARIA, "Maria", "rest")];
const linked = (id: string, name: string | null) => ({
  id,
  name,
  linked_at: "2026-11-02T06:00:00Z",
});

/** Seven days ending on `last`, all blank but for the ones given. */
function week(last = TODAY, over: Record<string, Partial<Day>> = {}): Day[] {
  const end = Date.parse(`${last}T00:00:00Z`);
  return [6, 5, 4, 3, 2, 1, 0].map((back) => {
    const date = new Date(end - back * 86_400_000).toISOString().slice(0, 10);
    return { date, state: null, length: null, ...over[date] };
  });
}

const card = (over: Partial<Card> = {}): Card => ({
  id: ANNA,
  name: "Anna",
  days: week(TODAY, {
    [TODAY]: {
      state: "practiced",
      length: { series: ["primary"], end: "navasana", first_part: null },
    },
    "2026-11-06": { state: "rest" },
  }),
  last_asana: { series: "intermediate", last: "kapotasana" },
  quiet: false,
  ...over,
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let accountLocale: "en" | "ru" = "en";

function background(path: string): unknown {
  if (path === "/api/v1/me" || path === "/api/v1/me/device-timezone") {
    return { ...ME, locale: accountLocale };
  }
  if (path === "/api/v1/health") return { version: "1", commit: "abcdef0" };
  if (path === "/api/v1/moon/cities") return [];
  if (path === "/api/v1/catalog") return CATALOG;
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

type Answer = (request: Request) => Response | undefined | Promise<Response | undefined>;

interface Api {
  rows?: () => Row[];
  total?: () => number;
  card?: (id: string) => Card;
  answer?: Answer;
}

/** Serves the links from `rows`, the list and the card. Every API request lands in the result. */
function stubApi({ rows = () => ROWS, total, card: found = () => card(), answer }: Api = {}) {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request.clone());
      const custom = await answer?.(request);
      if (custom) return custom;
      const url = new URL(request.url);
      const path = url.pathname;
      if (path === "/api/v1/me/links") {
        return json({ teachers: [], students: rows().map((r) => linked(r.id, r.name)) });
      }
      if (path === "/api/v1/me/students") {
        const offset = Number(url.searchParams.get("offset") ?? 0);
        const limit = Number(url.searchParams.get("limit") ?? 20);
        const all = rows();
        return json({
          students: all.slice(offset, offset + limit),
          total: total?.() ?? all.length,
        });
      }
      if (request.method === "DELETE") return new Response(null, { status: 204 });
      const one = /^\/api\/v1\/me\/students\/(.+)$/.exec(path);
      if (one?.[1]) return json(found(one[1]));
      return json(background(path));
    }),
  );
  return seen;
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
const pageText = () => plain(document.body.textContent);
const calls = (seen: Request[], method: string, path: string) =>
  seen.filter((r) => r.method === method && new URL(r.url).pathname === path);
const heading = () => plain(screen.getByRole("heading", { level: 1 }).textContent);
const labelled = (end: string) => screen.queryAllByLabelText((label) => plain(label).endsWith(end));

const homeLoaded = () => screen.findByRole("button", { name: /^⚙️ / });
const homeRow = (locale: "en" | "ru" = "en") =>
  screen.findByRole("button", { name: locale === "en" ? "👥 My students" : "👥 Мои ученики" });

async function renderApp(locale: "en" | "ru" = "en") {
  accountLocale = locale;
  vi.resetModules();
  const { App } = await import("../../App");
  render(<App locale={locale} firstName="Ash" inTelegram />);
  await homeLoaded();
}

async function openList(locale: "en" | "ru" = "en") {
  await renderApp(locale);
  fireEvent.click(await homeRow(locale));
  await screen.findByText(locale === "en" ? /own time zone/ : /часовому поясу каждого ученика/);
}

async function openCard(name: RegExp | string = /Anna/, locale: "en" | "ru" = "en") {
  await openList(locale);
  fireEvent.click(await screen.findByRole("button", { name }));
  await screen.findByText(locale === "en" ? "Last 7 days" : "Последние 7 дней");
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("onboard.tour", "1");
  confirmDestructive.mockReset();
  confirmDestructive.mockResolvedValue(false);
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

describe("the Home row", () => {
  test("is there with students, and carries no figure", async () => {
    stubApi();

    await renderApp();

    const entry = await homeRow();
    expect(entry.textContent).not.toMatch(/\d/);
    expect(plain(entry.textContent)).toBe("👥 My students");
  });

  test("is absent with no students", async () => {
    const seen = stubApi({ rows: () => [] });

    await renderApp();

    await waitFor(() => {
      expect(calls(seen, "GET", "/api/v1/me/links")).toHaveLength(1);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByRole("button", { name: /students/i })).toBeNull();
  });

  test("never holds Home back: it arrives after first paint", async () => {
    let release: (response: Response) => void = () => undefined;
    stubApi({
      answer: (request) =>
        new URL(request.url).pathname === "/api/v1/me/links"
          ? new Promise<Response>((r) => {
              release = r;
            })
          : undefined,
    });

    await renderApp();

    expect(screen.queryByRole("button", { name: "👥 My students" })).toBeNull();
    release(json({ teachers: [], students: [linked(ANNA, "Anna")] }));
    await homeRow();
  });

  test("reads no one's activity until it's opened", async () => {
    const seen = stubApi();

    await renderApp();
    await homeRow();

    expect(calls(seen, "GET", "/api/v1/me/students")).toHaveLength(0);
  });

  test("shares useLinks with the Settings screen, so nothing is fetched twice", async () => {
    const seen = stubApi();
    await renderApp();
    await homeRow();

    act(() => {
      telegram.openSettings();
    });
    fireEvent.click(await screen.findByRole("button", { name: "👥 Teachers and students" }));

    await screen.findByRole("heading", { name: "👥 Teachers and students" });
    expect(calls(seen, "GET", "/api/v1/me/links")).toHaveLength(1);
  });
});

describe("the list", () => {
  test("shows each name with today's mark, and a blank has no mark", async () => {
    stubApi();

    await openList();

    const practiced = await screen.findByRole("button", { name: /Anna/ });
    const blank = screen.getByRole("button", { name: /Dmitry/ });
    const rest = screen.getByRole("button", { name: /Maria/ });
    expect(plain(practiced.textContent)).toBe("🧘 Anna");
    expect(plain(blank.textContent)).toBe("Dmitry");
    expect(plain(rest.textContent)).toBe("😌 Maria");
  });

  test("marks have labels from the status words", async () => {
    stubApi();

    await openList();

    await screen.findByRole("button", { name: /Maria/ });
    expect(screen.getAllByLabelText("🧘 Practiced")).toHaveLength(1);
    expect(screen.getAllByLabelText("😌 Rest day")).toHaveLength(1);
  });

  test("has the title and the time zone note", async () => {
    stubApi();

    await openList();

    await screen.findByRole("button", { name: /Maria/ });
    expect(heading()).toBe("👥 My students (3)");
    expect(pageText()).toContain("Days follow each student's own time zone.");
  });

  test("carries no dates and no week, and opens no card by itself", async () => {
    const seen = stubApi();

    await openList();

    await screen.findByRole("button", { name: /Anna/ });
    expect(pageText()).not.toMatch(/Nov|Last 7 days|Today|Yesterday/);
    expect(seen.filter((r) => new URL(r.url).pathname.startsWith("/api/v1/me/students/"))).toEqual(
      [],
    );
  });

  test("keeps the server's order and adds no sort, filter or count over activity", async () => {
    stubApi();

    await openList();

    await screen.findByRole("button", { name: /Anna/ });
    const names = ROWS.map((r) => pageText().indexOf(r.name ?? ""));
    expect(names).toEqual([...names].sort((a, b) => a - b));
    expect(pageText()).not.toMatch(/practiced today/i);
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  test("a student without a name shows the fallback", async () => {
    stubApi({ rows: () => [row(ANNA, null, "rest")] });

    await openList();

    await screen.findByRole("button", { name: /\(no name\)/ });
  });

  test("Show more asks for the next page, and goes away at the end", async () => {
    const all = Array.from({ length: 25 }, (_, n) =>
      row(`00000000-0000-0000-0000-0000000001${String(n).padStart(2, "0")}`, `S${String(n)}`),
    );
    const seen = stubApi({ rows: () => all });
    await openList();
    await screen.findByRole("button", { name: "S19" });
    expect(screen.queryByRole("button", { name: "S20" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Show more" }));

    await screen.findByRole("button", { name: "S24" });
    expect(screen.getByRole("button", { name: "S0" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
    const offsets = calls(seen, "GET", "/api/v1/me/students").map((r) =>
      new URL(r.url).searchParams.get("offset"),
    );
    expect(offsets).toContain("20");
  });

  test("no Show more when everyone is on the page", async () => {
    stubApi();

    await openList();

    await screen.findByRole("button", { name: /Anna/ });
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  test("an empty list says so", async () => {
    let rows = ROWS;
    stubApi({ rows: () => rows });
    await renderApp();
    const entry = await homeRow();
    rows = [];

    fireEvent.click(entry);

    await screen.findByText("No students on your list.");
  });

  test("a failed load says so instead of an empty screen", async () => {
    stubApi({
      answer: (request) =>
        new URL(request.url).pathname === "/api/v1/me/students"
          ? json({ code: "unavailable" }, 503)
          : undefined,
    });
    await renderApp();

    fireEvent.click(await homeRow());

    await screen.findByRole("alert", {}, { timeout: 4000 });
    expect(pageText()).toContain("Couldn't load your students. Try again in a moment.");
  });

  test("opens from the Students part of Teachers and students too", async () => {
    stubApi();
    await renderApp();
    await homeRow();
    act(() => {
      telegram.openSettings();
    });
    fireEvent.click(await screen.findByRole("button", { name: "👥 Teachers and students" }));
    await screen.findByRole("heading", { name: "👥 Teachers and students" });

    fireEvent.click(await screen.findByRole("button", { name: /^👥 My students/ }));

    await screen.findByRole("button", { name: /Maria/ });
    expect(pageText()).toContain("Days follow each student's own time zone.");
  });
});

describe("the card", () => {
  test("shows the name, the last asana, seven days and the blank note", async () => {
    const seen = stubApi();

    await openCard();

    expect(pageText()).toContain("Anna");
    expect(pageText()).toContain("Last asana, as marked in their log: Kapotasana (Intermediate)");
    expect(pageText()).toContain(
      "Not every day gets logged, rest days included. A blank says nothing about the practice.",
    );
    expect(pageText()).toContain("Primary → Navasana");
    expect(calls(seen, "GET", `/api/v1/me/students/${ANNA}`)).toHaveLength(1);
  });

  test("every one of the seven days has a labelled row", async () => {
    stubApi();

    await openCard();

    expect(labelled(": nothing to show")).toHaveLength(5);
    expect(screen.getAllByLabelText(/🧘 Practiced/)).toHaveLength(1);
    expect(screen.getAllByLabelText(/😌 Rest day/)).toHaveLength(1);
  });

  test("all blanks share one class", async () => {
    stubApi();

    await openCard();

    const classes = new Set(labelled(": nothing to show").map((r) => r.className));
    expect(classes.size).toBe(1);
    expect([...classes][0]).not.toBe("");
  });

  test("a blank's label says nothing of why", async () => {
    stubApi();

    await openCard();

    const [first = ""] = labelled(": nothing to show").map((r) =>
      plain(r.getAttribute("aria-label")),
    );
    expect(first).toMatch(/^[^:]+: nothing to show$/);
  });

  test("no moon, 🌸, sick, travel or No practice word is on the screen", async () => {
    stubApi();

    await openCard();

    expect(pageText()).not.toMatch(/🌙|🌸|🤒|✈|🌱|Moon|Ladies|Sick|Travel|No practice/);
  });

  test("the quiet note shows only when the card says so", async () => {
    stubApi({ card: () => card({ quiet: true, days: week() }) });

    await openCard();

    expect(pageText()).toContain("Nothing shared for a while");
  });

  test("no quiet note without the flag", async () => {
    stubApi({ card: () => card({ quiet: false, days: week() }) });

    await openCard();

    expect(pageText()).not.toContain("Nothing shared for a while");
  });

  test("the last asana line: standing only", async () => {
    stubApi({ card: () => card({ last_asana: { series: null, last: null } }) });

    await openCard();

    expect(pageText()).toContain("As marked in their log: sun salutations and standing");
    expect(pageText()).not.toContain("Last asana");
  });

  test("the last asana line: null omits it", async () => {
    stubApi({ card: () => card({ last_asana: null }) });

    await openCard();

    expect(pageText()).not.toContain("Last asana");
    expect(pageText()).not.toContain("As marked in their log");
  });

  test("the last asana line: a stale key stays readable", async () => {
    stubApi({ card: () => card({ last_asana: { series: "intermediate", last: "gone-asana" } }) });

    await openCard();

    expect(pageText()).toContain("Last asana, as marked in their log: gone-asana (Intermediate)");
  });

  test("the last asana line: a stale series prints the raw value", async () => {
    stubApi({ card: () => card({ last_asana: { series: "gone-series", last: "gone-asana" } }) });

    await openCard();

    expect(pageText()).toContain("Last asana, as marked in their log: gone-asana (gone-series)");
  });

  test("Back returns to the list without a new read of it", async () => {
    const seen = stubApi();
    await openCard();

    act(() => {
      telegram.back();
    });

    await screen.findByRole("button", { name: /Maria/ });
    expect(calls(seen, "GET", "/api/v1/me/students")).toHaveLength(1);
  });

  test("the same card twice within 60 s is one read", async () => {
    const seen = stubApi();
    await openCard();
    act(() => {
      telegram.back();
    });

    fireEvent.click(await screen.findByRole("button", { name: /Anna/ }));

    await screen.findByText("Last 7 days");
    expect(calls(seen, "GET", `/api/v1/me/students/${ANNA}`)).toHaveLength(1);
  });

  test("a 404 silently returns to the list and refetches it", async () => {
    let gone = false;
    const seen = stubApi({
      rows: () => (gone ? ROWS.slice(1) : ROWS),
      answer: (request) => {
        if (new URL(request.url).pathname !== `/api/v1/me/students/${ANNA}`) return undefined;
        if (request.method !== "GET") return undefined;
        gone = true;
        return json({ code: "not_linked" }, 404);
      },
    });
    await openList();

    fireEvent.click(await screen.findByRole("button", { name: /Anna/ }));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /Anna/ })).toBeNull();
    });
    await screen.findByRole("button", { name: /Maria/ });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(calls(seen, "GET", "/api/v1/me/students").length).toBeGreaterThan(1);
  });
});

describe("Remove", () => {
  test("Cancel sends nothing and stays on the card", async () => {
    const seen = stubApi();
    await openCard();

    fireEvent.click(screen.getByRole("button", { name: "Remove…" }));

    await waitFor(() => {
      expect(confirmDestructive).toHaveBeenCalledOnce();
    });
    expect(seen.filter((r) => r.method === "DELETE")).toHaveLength(0);
    expect(pageText()).toContain("Last 7 days");
  });

  test("asks in the student's words through confirmDestructive", async () => {
    stubApi();
    await openCard();

    fireEvent.click(screen.getByRole("button", { name: "Remove…" }));

    await waitFor(() => {
      expect(confirmDestructive).toHaveBeenCalledOnce();
    });
    const [message, ok, cancel] = confirmDestructive.mock.calls[0] ?? [];
    expect(plain(message)).toBe("Remove Anna from your students? They won't get a message.");
    expect((ok ?? "").trim()).toBe("Remove");
    expect((cancel ?? "").trim()).toBe("Cancel");
  });

  test("confirming deletes, returns to the list and drops the cache", async () => {
    confirmDestructive.mockResolvedValue(true);
    let removed = false;
    const seen = stubApi({
      rows: () => (removed ? ROWS.slice(1) : ROWS),
      answer: (request) => {
        if (request.method !== "DELETE") return undefined;
        removed = true;
        return new Response(null, { status: 204 });
      },
    });
    await openCard();

    fireEvent.click(screen.getByRole("button", { name: "Remove…" }));

    await waitFor(() => {
      expect(calls(seen, "DELETE", `/api/v1/me/students/${ANNA}`)).toHaveLength(1);
    });
    await screen.findByRole("button", { name: /Maria/ });
    expect(screen.queryByRole("button", { name: /Anna/ })).toBeNull();
    expect(calls(seen, "GET", "/api/v1/me/students").length).toBeGreaterThan(1);
  });

  test("removing from the Teachers and students screen drops the list's cache too", async () => {
    confirmDestructive.mockResolvedValue(true);
    let removed = false;
    stubApi({
      rows: () => (removed ? ROWS.slice(1) : ROWS),
      answer: (request) => {
        if (request.method !== "DELETE") return undefined;
        removed = true;
        return new Response(null, { status: 204 });
      },
    });
    await openList();
    await screen.findByRole("button", { name: /Anna/ });
    act(() => {
      telegram.back();
    });
    await homeRow();
    act(() => {
      telegram.openSettings();
    });
    fireEvent.click(await screen.findByRole("button", { name: "👥 Teachers and students" }));
    await screen.findByRole("heading", { name: "👥 Teachers and students" });
    const person = (await screen.findByText("Anna")).closest(".link-person") as HTMLElement;

    fireEvent.click(within(person).getByRole("button", { name: "Remove…" }));

    await waitFor(() => {
      expect(removed).toBe(true);
    });
    fireEvent.click(await screen.findByRole("button", { name: /^👥 My students/ }));
    await screen.findByRole("button", { name: /Maria/ });
    expect(screen.queryByRole("button", { name: /Anna/ })).toBeNull();
  });
});

describe("dates", () => {
  const zone = process.env.TZ;

  afterEach(() => {
    if (zone === undefined) delete process.env.TZ;
    else process.env.TZ = zone;
    vi.useRealTimers();
  });

  test.each(["UTC", "Pacific/Honolulu", "Pacific/Kiritimati"])(
    "don't shift with the teacher's device in %s",
    async (deviceZone) => {
      process.env.TZ = deviceZone;
      expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe(deviceZone);
      stubApi();

      await openCard();

      const rows = labelled(": nothing to show").map((r) => plain(r.getAttribute("aria-label")));
      expect(rows.join(" ")).toContain("Nov 5");
      expect(rows.join(" ")).toContain("Nov 1");
      expect(rows.join(" ")).not.toContain("Oct 31");
      expect(rows.join(" ")).not.toContain("Nov 6");
      expect(pageText()).toContain("Nov 7");
      expect(pageText()).not.toContain("Nov 8");
    },
  );

  test("Today is the last day the server sent, never the device's date", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-20T12:00:00Z") });
    stubApi();

    await openCard();

    const today = screen.getByLabelText(/🧘 Practiced/);
    const yesterday = screen.getByLabelText(/😌 Rest day/);
    expect(plain(today.textContent)).toContain("Today");
    expect(plain(today.textContent)).toContain("Nov 7");
    expect(plain(yesterday.textContent)).toContain("Yesterday");
    expect(plain(yesterday.textContent)).toContain("Nov 6");
  });

  test("a student a day ahead of the device still reads as Today", async () => {
    stubApi({
      card: () => card({ days: week("2026-11-08", { "2026-11-08": { state: "rest" } }) }),
    });

    await openCard();

    expect(plain(screen.getByLabelText(/😌 Rest day/).textContent)).toContain("Today");
    expect(pageText()).toContain("Nov 8");
  });
});

describe("Russian", () => {
  test("the list", async () => {
    stubApi();

    await openList("ru");

    await screen.findByRole("button", { name: /Maria/ });
    expect(heading()).toBe("👥 Мои ученики (3)");
    expect(pageText()).toContain("Дни считаются по часовому поясу каждого ученика.");
    expect(screen.getAllByLabelText("🧘 Практика")).toHaveLength(1);
    expect(screen.getAllByLabelText("😌 День отдыха")).toHaveLength(1);
  });

  test("the card", async () => {
    stubApi({ card: () => card({ quiet: true }) });

    await openCard(/Anna/, "ru");

    expect(pageText()).toContain(
      "Последняя асана по отметкам в журнале: Капотасана (вторая серия)",
    );
    expect(pageText()).toContain("Последние 7 дней");
    expect(pageText()).toContain("Какое-то время показать нечего");
    expect(pageText()).toContain("Первая → Навасана");
    expect(labelled(": показать нечего")).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Убрать…" })).toBeInTheDocument();
  });

  test("the standing-only line", async () => {
    stubApi({ card: () => card({ last_asana: { series: null, last: null } }) });

    await openCard(/Anna/, "ru");

    expect(pageText()).toContain("По отметкам в журнале: Сурья Намаскар и стоячие");
  });

  test("a long name stays on one line at 320 px: its class ellipsizes", async () => {
    // jsdom has no layout, so this pins the mechanism; the owner checks a real phone (spec §8).
    const long = "Я".repeat(64);
    stubApi({ rows: () => [row(ANNA, long, "practiced")] });

    await openList("ru");

    const name = await screen.findByText(long);
    const { readFileSync } = process.getBuiltinModule("node:fs");
    const tokens = readFileSync(`${process.cwd()}/src/theme/tokens.css`, "utf8");
    const css = tokens.replace(/\/\*[\s\S]*?\*\//g, "");
    const rules = [...css.matchAll(/([^{}]+)\{([^}]*text-overflow:\s*ellipsis[^}]*)\}/g)];
    const selectors = rules.map((rule) => (rule[1] ?? "").trim()).filter(Boolean);
    expect(selectors.some((selector) => name.matches(selector))).toBe(true);
  });
});

describe("the chunk", () => {
  test("Students is lazy, so initial JS gains only the Home row", () => {
    expect(appSource).toMatch(/lazy\(\(\) => import\("\.\/screens\/teachers\/Students"\)\)/);
  });

  test.each([
    ["App.tsx", appSource],
    ["Home.tsx", homeSource],
    ["Links.tsx", linksSource],
  ])("%s has no static import of it", (_, source) => {
    expect(source).not.toMatch(/^import .*teachers\/Students/m);
  });
});
