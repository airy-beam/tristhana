import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";

import type { Stats as StatsData, StatsSummary } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import { saveShowLadies } from "./cells";
import Stats from "./Stats";

const backButton = vi.hoisted(() => ({ available: true }));

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => backButton.available),
}));

const TODAY = "2026-10-19";
const EMPTY: StatsSummary = {
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

/** The cell of an October 2026 day in a year that starts on Jan 1 (Oct 1 is day 273). */
const oct = (day: number) => 272 + day;

function stats(overrides: Partial<StatsData> = {}): StatsData {
  const days = 292; // Jan 1 … Oct 19
  const cells: StatsData["cells"] = Array.from({ length: days }, () => "none");
  cells[oct(17)] = "practiced";
  cells[oct(18)] = "ladies";
  const october: StatsSummary = {
    ...EMPTY,
    practiced: 1,
    possible: 1,
    unlogged: 16,
    rest: { ...EMPTY.rest, ladies: 1 },
    contexts: { ...EMPTY.contexts, mysore: 1 },
    series: [{ number: 2, practices: 1 }],
    duration: { total_min: 90, count: 1 },
  };
  const months = Array.from({ length: 12 }, (_, m) => (m === 9 ? october : EMPTY));
  return {
    today: TODAY,
    timezone_known: true,
    auto: [],
    year: 2026,
    first_year: 2025,
    cells,
    moon: { location: "mysuru", days: [{ date: "2026-10-25", phase: "purnima" }] },
    months,
    year_total: october,
    runs: { current: 1, longest: 12 },
    ...overrides,
  };
}

/** Mid-January: one step back is last year. */
function january(overrides: Partial<StatsData> = {}): StatsData {
  return stats({
    today: "2026-01-15",
    cells: Array.from({ length: 15 }, () => "none"),
    months: Array.from({ length: 12 }, () => EMPTY),
    year_total: EMPTY,
    moon: { location: "mysuru", days: [] },
    ...overrides,
  });
}

/** Another year of the same account: complete, with nothing logged. */
const otherYear = (data: StatsData, year: number): StatsData => ({
  ...data,
  year,
  cells: Array.from({ length: 365 }, () => "none"),
  auto: [],
  months: Array.from({ length: 12 }, () => EMPTY),
  year_total: EMPTY,
  moon: { location: "mysuru", days: [] },
});

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

const NOTIFY = {
  moon: { offsets: [1, 7], at: "19:00:00" },
  quiet: { start: "22:00:00", end: "07:00:00" },
  daily_cap: 3,
  practice: { on: true, at: "10:00:00", days: [1, 2, 3, 4, 5, 7] },
  timezone: "Asia/Almaty",
};
let dayOff: number[] | null = [6];
let question: { weekday: number; reminders_on: boolean } | null = null;
/** What GET /me/days answers with for the opened day. */
let logged: unknown[] = [];
/** A year whose answer waits until the test lets it go. */
let held: { year: number; release: () => void } | null = null;

function stubApi(data: StatsData = stats()): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      seen.push(request);
      const url = new URL(request.url);
      if (url.pathname === "/api/v1/me/stats") {
        const year = url.searchParams.get("year");
        if (!year) return json(data);
        const answer = json(otherYear(data, Number(year)));
        if (held?.year !== Number(year)) return answer;
        return new Promise<Response>((resolve) => {
          (held as { release: () => void }).release = () => {
            resolve(answer);
          };
        });
      }
      if (url.pathname === "/api/v1/moon/cities") {
        return json([
          { slug: "mysuru", name_en: "Mysuru", name_ru: "Майсур", timezone: "Asia/Kolkata" },
        ]);
      }
      if (url.pathname === "/api/v1/me/days") {
        return json({
          today: data.today,
          timezone_known: true,
          auto: [],
          moon_location: "mysuru",
          days: logged,
        });
      }
      if (request.method === "PUT") return new Response(null, { status: 204 });
      if (url.pathname === "/api/v1/me/day-off-question")
        return new Response(null, { status: 204 });
      if (url.pathname === "/api/v1/me") return json({ day_off: dayOff });
      if (url.pathname === "/api/v1/me/notification-settings")
        return json({ ...NOTIFY, day_off_question: question });
      if (url.pathname === "/api/v1/me/badges") return json({ badges: [] });
      if (url.pathname === "/api/v1/me/check-in-trends")
        return json({
          from: "2025-12-01",
          to: "2026-11-11",
          total: 0,
          enough: false,
          min_total: 10,
          min_bucket: 5,
          months: [],
          weekdays: null,
          moon: null,
        });
      if (url.pathname === "/api/v1/catalog")
        return json({ version: "v1", series: [], milestone_items: [], check_in_tags: [] });
      return json({});
    }),
  );
  return seen;
}

function renderStats(
  locale: Locale = "en",
  props: { onAsanas?: () => void; onDayOff?: () => void } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <Stats
          locale={locale}
          zone="Asia/Almaty"
          onAsanas={props.onAsanas ?? vi.fn()}
          onDayOff={props.onDayOff ?? vi.fn()}
        />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const plain = (text: string) => text.replace(/[⁨⁩]/g, "");
const byText = (text: string) => (_: string, el: Element | null) =>
  el?.tagName === "P" && plain(el.textContent) === text;
/** The day of the month calendar whose accessible name has this date ("Oct 18"). */
const day = (date: string) => screen.findByRole("button", { name: (n) => plain(n).includes(date) });
const dayName = (cell: HTMLElement) => plain(cell.getAttribute("aria-label") ?? "");
const month = (name: string) => screen.findByRole("heading", { level: 2, name });
const previous = () => screen.getByRole("button", { name: "Previous month" });
const next = () => screen.getByRole("button", { name: "Next month" });
const fold = () => screen.getByRole("button", { name: "The month in numbers" });
const legend = (label = "What the marks mean") =>
  within(screen.getByRole("list", { name: label }))
    .getAllByRole("listitem")
    .map((item) => plain(item.textContent));
const statsRequests = (seen: Request[]) =>
  seen
    .filter((r) => new URL(r.url).pathname === "/api/v1/me/stats")
    .map((r) => new URL(r.url).searchParams.get("year"));

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  backButton.available = true;
  dayOff = [6];
  question = null;
  logged = [];
  held = null;
});

describe("the month comes first (UI-06 stage 3)", () => {
  it("opens on the current month, by the server's today; no year on the tab", async () => {
    stubApi();
    renderStats();

    const title = await month("October 2026");
    const headings = screen.getAllByRole("heading").map((h) => plain(h.textContent));
    expect(headings).toEqual(["My practice", "October 2026"]);
    expect(title.closest("section")).toHaveAccessibleName("October 2026");
    expect(screen.queryByRole("button", { name: "Previous year" })).toBeNull();
    expect(screen.queryByRole("button", { name: "September" })).toBeNull(); // no mini-months
  });

  it("the current month is the server's, also when the device is in another month", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2027-03-03T10:00:00Z") });
    try {
      stubApi();
      renderStats();

      expect(await month("October 2026")).toBeInTheDocument();
      expect(next()).toBeDisabled();
      expect(await day("Oct 19")).toHaveAttribute("aria-current", "date");
    } finally {
      vi.useRealTimers();
    }
  });

  it("steps by month inside a year without another read", async () => {
    const seen = stubApi();
    renderStats();
    await month("October 2026");
    expect(next()).toBeDisabled(); // the current month is the last one

    fireEvent.click(previous());

    expect(await month("September 2026")).toBeInTheDocument();
    expect(next()).toBeEnabled();
    fireEvent.click(next());
    expect(await month("October 2026")).toBeInTheDocument();
    expect(statsRequests(seen)).toEqual([null]);
  });

  it("crosses a year; the month on screen stays while the other year loads", async () => {
    held = { year: 2025, release: () => undefined };
    const seen = stubApi(january());
    renderStats();
    await month("January 2026");

    fireEvent.click(previous());

    await vi.waitFor(() => {
      expect(statsRequests(seen)).toEqual([null, "2025"]);
    });
    expect(screen.getByRole("heading", { level: 2, name: "January 2026" })).toBeVisible();
    expect(screen.getByRole("main")).not.toHaveAttribute("aria-busy");
    act(() => {
      held?.release();
    });

    expect(await month("December 2025")).toBeInTheDocument();
    expect(next()).toBeEnabled();
    fireEvent.click(next());
    // The current year is cached as "current": coming back reads nothing.
    expect(await month("January 2026")).toBeInTheDocument();
    expect(statsRequests(seen)).toEqual([null, "2025"]);
  });

  it("stops at January of the first year with anything logged", async () => {
    stubApi(january());
    renderStats();
    await month("January 2026");

    for (let i = 0; i < 12; i++) fireEvent.click(previous());

    expect(await month("January 2025")).toBeInTheDocument();
    expect(previous()).toBeDisabled();
  });

  it("stops at this January when nothing was logged before this year", async () => {
    stubApi(january({ first_year: null }));
    renderStats();
    await month("January 2026");

    expect(previous()).toBeDisabled();
    expect(next()).toBeDisabled();
  });

  it("names the arrows in Russian", async () => {
    stubApi();
    renderStats("ru");

    expect(await screen.findByRole("button", { name: "Предыдущий месяц" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Следующий месяц" })).toBeDisabled();
    expect(screen.getByRole("heading", { level: 2, name: "октябрь 2026 г." })).toBeVisible();
  });
});

describe("four marks", () => {
  it("has exactly four legend items, in order, and no 'Not logged'", async () => {
    stubApi();
    renderStats();
    await month("October 2026");

    expect(legend()).toEqual(["Practice", "Rest", "🌙 Moon day", "🌱 No practice"]);
    expect(screen.queryByText("Not logged")).toBeNull();
    const swatches = [...document.querySelectorAll(".legend .swatch")].map((s) => s.className);
    expect(swatches).toEqual(["swatch practiced", "swatch rest", "swatch ring", "swatch skipped"]);
  });

  it("has the same four in Russian", async () => {
    stubApi();
    renderStats("ru");
    await screen.findByRole("heading", { level: 2, name: "октябрь 2026 г." });

    expect(legend("Что означают отметки")).toEqual([
      "Практика",
      "Отдых",
      "🌙 Лунный день",
      "🌱 Без практики",
    ]);
  });

  it("draws every kind of rest in one colour, and an empty past day in none", async () => {
    const s = stats({
      auto: [
        { date: "2026-10-10", kind: "day_off", also_day_off: false },
        { date: "2026-10-03", kind: "moon", also_day_off: true },
      ],
    });
    s.cells[oct(1)] = "sick";
    s.cells[oct(2)] = "travel";
    s.cells[oct(5)] = "moon";
    s.cells[oct(6)] = "rest";
    s.cells[oct(7)] = "skipped";
    stubApi(s);
    renderStats();

    for (const date of ["Oct 1:", "Oct 2:", "Oct 5:", "Oct 6:", "Oct 18:", "Oct 10:", "Oct 3:"]) {
      expect((await day(date)).className).toBe("day rest");
    }
    expect((await day("Oct 17:")).className).toBe("day practiced");
    expect((await day("Oct 7:")).className).toBe("day skipped");
    // Nothing logged: a plain number, the same whether the day is long past or yesterday.
    expect((await day("Oct 12:")).className).toBe("day");
    expect((await day("Oct 19:")).className).toBe("day today");
    expect((await day("Oct 20")).className).toBe("day future");
    // The reason is in the day's name, one tap away.
    expect(dayName(await day("Oct 1:"))).toBe("Thu, Oct 1: 🤒 Sick / injury");
    expect(dayName(await day("Oct 5:"))).toBe("Mon, Oct 5: 🌙 Moon day");
    expect(dayName(await day("Oct 12:"))).toBe("Mon, Oct 12: Not logged");
  });

  it("marks a moon day with a ring: on a coming day of this month and on a practice", async () => {
    stubApi(
      stats({
        moon: {
          location: "mysuru",
          days: [
            { date: "2026-10-17", phase: "amavasya" },
            { date: "2026-10-25", phase: "purnima" },
            { date: "2026-11-09", phase: "amavasya" },
          ],
        },
      }),
    );
    renderStats();

    const oct25 = await day("Oct 25");
    expect(oct25.className).toBe("day future moon-marker");
    expect(oct25).toBeDisabled(); // to come: nothing to log yet
    expect(dayName(oct25)).toBe("Sun, Oct 25: full or new moon");
    // A practice on a moon day is a practice with the ring, and no remark.
    const oct17 = await day("Oct 17");
    expect(oct17.className).toBe("day practiced moon-marker");
    expect(dayName(oct17)).toBe("Sat, Oct 17: 🧘 Practiced, full or new moon");
  });

  it("a day logged 'Moon day' that the followed city does not mark is rest, no ring", async () => {
    const s = stats();
    s.cells[oct(5)] = "moon";
    stubApi(s);
    renderStats();

    expect((await day("Oct 5:")).className).toBe("day rest");
  });

  it("names today for screen readers", async () => {
    stubApi();
    renderStats();

    expect(await day("Oct 19")).toHaveAttribute("aria-current", "date");
    expect(await day("Oct 18")).not.toHaveAttribute("aria-current");
  });
});

describe("a ladies' holiday on the calendar (WH-01, QB)", () => {
  it("is rest, named 'Rest day', while the device switch is off; no switch on the tab", async () => {
    stubApi();
    renderStats();
    const oct18 = await day("Oct 18");

    expect(oct18.className).toBe("day rest");
    expect(dayName(oct18)).toBe("Sun, Oct 18: 😌 Rest day");
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByText(/🌸/)).toBeNull();
    fireEvent.click(fold());
    expect(screen.getByText("😌 Rest day").parentElement).toHaveTextContent(/1$/);
  });

  it("keeps the rest fill and gets its mark and name with the switch on; still four marks", async () => {
    localStorage.setItem("stats.showLadies", "1");
    stubApi();
    renderStats();
    const oct18 = await day("Oct 18");

    expect(oct18.className).toBe("day rest flower");
    expect(dayName(oct18)).toBe("Sun, Oct 18: 🌸 Ladies' holiday");
    expect(legend()).toEqual(["Practice", "Rest", "🌙 Moon day", "🌱 No practice"]);
    fireEvent.click(fold());
    expect(screen.getByText("🌸 Ladies' holiday").parentElement).toHaveTextContent(/1$/);
    expect(screen.queryByText("😌 Rest day")).toBeNull();
  });

  it("follows the switch as Settings changes it, while the tab stays mounted", async () => {
    stubApi();
    renderStats();
    const oct18 = await day("Oct 18");

    act(() => {
      saveShowLadies(true);
    });
    expect(oct18.className).toBe("day rest flower");
    act(() => {
      saveShowLadies(false);
    });
    expect(oct18.className).toBe("day rest");
    expect(dayName(oct18)).toBe("Sun, Oct 18: 😌 Rest day");
  });
});

describe("one number, the rest folded", () => {
  it("shows the month's practices; the summary waits in a closed fold", async () => {
    stubApi();
    renderStats();

    expect(await screen.findByText(byText("1 practice"))).toBeInTheDocument();
    expect(fold()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("By series")).toBeNull();
    expect(screen.queryByText(/in total/)).toBeNull();
    expect(screen.queryByText(/Most in a row/)).toBeNull();

    fireEvent.click(fold());

    expect(fold()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("By series")).toBeInTheDocument();
    expect(
      screen.getByText(byText("⏱ 1 h 30 min in total · about 90 min per practice")),
    ).toBeInTheDocument();
    expect(screen.getByText(byText("Most in a row this year: 12"))).toBeInTheDocument();
    expect(screen.getByText(/Days you haven't logged are left out/)).toBeInTheDocument();
    // The number is said once: not again inside.
    expect(screen.getAllByText(byText("1 practice"))).toHaveLength(1);
  });

  it("counts 'of' only in the fold, once a 'No practice' day exists", async () => {
    const s = stats();
    s.months[9] = { ...(s.months[9] as StatsSummary), practiced: 18, skipped: 2, possible: 20 };
    stubApi(s);
    renderStats();

    expect(await screen.findByText(byText("18 practices"))).toBeInTheDocument();
    expect(screen.queryByText(/ of /)).toBeNull();
    fireEvent.click(fold());

    expect(screen.getByText(byText("Practice on 18 of 20 days"))).toBeInTheDocument();
    expect(screen.getByText("🌱 No practice", { selector: ".counts span" })).toBeInTheDocument();
  });

  it("is quiet at zero: no 'of' for a month with 'No practice' and no practice", async () => {
    const s = stats({ runs: { current: 0, longest: 0 } });
    s.months[9] = { ...EMPTY, skipped: 2, possible: 2, unlogged: 16 };
    stubApi(s);
    renderStats();
    await month("October 2026");
    fireEvent.click(fold());

    expect(screen.getByText("🌱 No practice", { selector: ".counts span" })).toBeInTheDocument();
    expect(screen.queryByText(/ of /)).toBeNull();
    expect(screen.queryByText(/Days you haven't logged/)).toBeNull(); // nothing to explain
  });

  it("says an empty month is empty, with no fold and nothing to share", async () => {
    stubApi();
    renderStats();
    await month("October 2026");

    fireEvent.click(previous());

    expect(await screen.findByText(byText("Nothing logged this month yet."))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "The month in numbers" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Share/ })).toBeNull();
  });

  it("shows what is in a row and what is not logged on the current month only", async () => {
    const s = stats({ runs: { current: 5, longest: 12 } });
    s.months[8] = { ...EMPTY, practiced: 3, possible: 3, unlogged: 4, unspecified: 3 };
    stubApi(s);
    renderStats();

    expect(await screen.findByText(byText("🌿 5 practices in a row"))).toBeInTheDocument();
    expect(screen.getByText(byText("16 days not logged: tap a day to add it"))).toBeInTheDocument();

    fireEvent.click(previous());

    expect(await screen.findByText(byText("3 practices"))).toBeInTheDocument();
    expect(screen.queryByText(/in a row/)).toBeNull();
    expect(screen.queryByText(/not logged/)).toBeNull();
  });

  it("shows no run under two, and invites to fill in an empty current month", async () => {
    const s = stats();
    s.months[9] = { ...EMPTY, unlogged: 18 };
    stubApi(s);
    renderStats();

    expect(
      await screen.findByText(byText("18 days not logged: tap a day to add it")),
    ).toBeInTheDocument();
    expect(screen.queryByText(/in a row$/)).toBeNull(); // the current run is 1
  });

  it("leaves 'Most in a row this year' out of another year's month", async () => {
    const data = january({ runs: { current: 0, longest: 12 } });
    const seen = stubApi(data);
    vi.mocked(fetch).mockImplementation((request: Request | URL | string) => {
      const r = request as Request;
      seen.push(r);
      const url = new URL(r.url);
      if (url.pathname === "/api/v1/me/stats") {
        const december = { ...EMPTY, practiced: 2, possible: 2, unspecified: 2 };
        const last = otherYear(data, 2025);
        return Promise.resolve(
          json(
            url.searchParams.get("year")
              ? { ...last, months: last.months.map((m, i) => (i === 11 ? december : m)) }
              : data,
          ),
        );
      }
      return Promise.resolve(json(url.pathname === "/api/v1/me" ? { day_off: [6] } : []));
    });
    renderStats();
    await month("January 2026");
    fireEvent.click(previous());

    expect(await screen.findByText(byText("2 practices"))).toBeInTheDocument();
    fireEvent.click(fold());
    expect(screen.getByText("By series")).toBeInTheDocument();
    expect(screen.queryByText(/Most in a row/)).toBeNull();
  });

  it("uses Russian plurals and «подряд»", async () => {
    const s = stats({ runs: { current: 21, longest: 21 } });
    s.year_total = { ...EMPTY, practiced: 5 };
    stubApi(s);
    renderStats("ru");

    expect(await screen.findByText(byText("🌿 21 практика подряд"))).toBeInTheDocument();
    expect(screen.getByText(byText("1 практика"))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: (n) => plain(n) === "📅 2026 · 5 практик" }));
  });
});

describe("the day card under the month", () => {
  it("opens on a tap, takes the focus, and logs a past day", async () => {
    const seen = stubApi();
    renderStats();
    const oct16 = await day("Oct 16");
    fireEvent.click(oct16);

    const editor = await screen.findByRole("region", { name: (n) => plain(n).includes("Oct 16") });
    expect(within(editor).getByRole("heading", { level: 2 })).toHaveFocus();
    // The day is named at once; its choices follow the read of that day.
    fireEvent.click(await within(editor).findByRole("button", { name: "😌 Rest day" }));

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PUT")).toBe(true);
    });
    const put = seen.find((r) => r.method === "PUT");
    expect(new URL(put?.url ?? "").pathname).toBe("/api/v1/me/days/2026-10-16");

    fireEvent.click(within(editor).getByRole("button", { name: "Done" }));

    expect(screen.queryByRole("region", { name: (n) => plain(n).includes("Oct 16") })).toBeNull();
    expect(oct16).toHaveFocus(); // back on the day that was tapped
  });

  it("sits between the calendar and the legend", async () => {
    stubApi();
    renderStats();
    fireEvent.click(await day("Oct 16"));

    const editor = await screen.findByRole("region", { name: (n) => plain(n).includes("Oct 16") });
    const after = (a: Element, b: Element) =>
      (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
    expect(after(await day("Oct 31"), editor)).toBe(true);
    expect(after(editor, screen.getByRole("list", { name: "What the marks mean" }))).toBe(true);
  });

  it("shows the moon line, with the phase and the city, on a moon day", async () => {
    stubApi(
      stats({
        moon: { location: "mysuru", days: [{ date: "2026-10-10", phase: "amavasya" }] },
      }),
    );
    renderStats();
    fireEvent.click(await day("Oct 10"));

    const editor = await screen.findByRole("region", { name: (n) => plain(n).includes("Oct 10") });
    expect(await within(editor).findByText(byText("🌑 New moon · 📍 Mysuru"))).toBeInTheDocument();

    fireEvent.click(await day("Oct 16")); // another day: another card, and no moon line
    const other = await screen.findByRole("region", { name: (n) => plain(n).includes("Oct 16") });
    await within(other).findByRole("button", { name: "😌 Rest day" });
    expect(screen.queryByText(/New moon/)).toBeNull();
  });

  it("closes when the month changes", async () => {
    stubApi();
    renderStats();
    fireEvent.click(await day("Oct 16"));
    await screen.findByRole("region", { name: (n) => plain(n).includes("Oct 16") });

    fireEvent.click(previous());

    await month("September 2026");
    expect(screen.queryByRole("region", { name: (n) => plain(n).includes("Oct 16") })).toBeNull();
  });

  // QB: the device switch is about the calendar. The card of a day tells its owner the truth,
  // as Today and the bot do; with the switch off (the default) the day still says rest above.
  it("tells its owner the truth: 🌸 with the private note, while the calendar says rest", async () => {
    logged = [{ date: "2026-10-18", status: "ladies", practices: [] }];
    const seen = stubApi();
    renderStats();
    const oct18 = await day("Oct 18");
    expect(dayName(oct18)).toBe("Sun, Oct 18: 😌 Rest day");
    fireEvent.click(oct18);

    const editor = await screen.findByRole("region", { name: (n) => plain(n).includes("Oct 18") });
    const change = await within(editor).findByRole("button", { name: "Change" });
    expect(change).toHaveAccessibleDescription("🌸 Ladies' holiday");
    expect(
      within(editor).getByText("Only you see this. Others see “Rest day”."),
    ).toBeInTheDocument();
    fireEvent.click(change);
    fireEvent.click(within(editor).getByRole("button", { name: "Other…" }));
    const own = within(editor).getByRole("button", { name: "🌸 Ladies' holiday", pressed: true });
    fireEvent.click(own);
    expect(seen.some((r) => r.method === "PUT")).toBe(false); // the same answer saves nothing
  });

  it("offers 🌸 for a past day with the switch off: it can be logged from the month", async () => {
    const seen = stubApi();
    renderStats();
    fireEvent.click(await day("Oct 16"));

    const editor = await screen.findByRole("region", { name: (n) => plain(n).includes("Oct 16") });
    fireEvent.click(await within(editor).findByRole("button", { name: "Other…" }));
    fireEvent.click(within(editor).getByRole("button", { name: "🌸 Ladies' holiday" }));

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PUT")).toBe(true);
    });
    const put = seen.find((r) => r.method === "PUT");
    expect(await put?.json()).toEqual({ status: "ladies" });
  });
});

describe("the rows under the month", () => {
  // UI-06 stage 2 (ADR-0047): My practice is the Practice tab's root.
  it("is a root: no Back layer, and no back link where Telegram has no Back button", async () => {
    backButton.available = false;
    stubApi();
    const { useBackButton } = await import("../../telegram");
    vi.mocked(useBackButton).mockClear();
    renderStats();
    await month("October 2026");

    expect(screen.queryByRole("button", { name: "‹ Back" })).toBeNull();
    expect(useBackButton).not.toHaveBeenCalled();
  });

  it("has My asanas, the year, Badges and Check-ins after the month, in this order", async () => {
    stubApi();
    const onAsanas = vi.fn();
    renderStats("en", { onAsanas });
    const card = (await month("October 2026")).closest("section") as HTMLElement;

    const rows = [...document.querySelectorAll(".row-button")];
    expect(rows.map((r) => plain(r.textContent))).toEqual([
      "🧘 My asanas",
      "📅 2026 · 1 practice",
      "🏅 Badges",
      "✨ Check-ins over time",
    ]);
    for (const row of rows) {
      expect(card.contains(row)).toBe(false);
      expect(card.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    fireEvent.click(rows[0] as HTMLElement);

    expect(onAsanas).toHaveBeenCalledOnce();
  });

  it("keeps the heading and the rows that need no stats when the stats fail to load", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("{}", { status: 500 }))),
    );
    renderStats();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "My practice" })).toBeInTheDocument();
    expect([...document.querySelectorAll(".row-button")].map((r) => r.textContent)).toEqual([
      "🧘 My asanas",
      "🏅 Badges",
      "✨ Check-ins over time",
    ]);
  });

  it("has the rows while the stats load", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );
    renderStats();

    expect(screen.getByRole("main")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "🧘 My asanas" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "🏅 Badges" })).toBeInTheDocument();
  });

  it("names the year row 'the whole year' while the year has no practice", async () => {
    stubApi(stats({ year_total: EMPTY, months: Array.from({ length: 12 }, () => EMPTY) }));
    renderStats();

    expect(
      await screen.findByRole("button", { name: (n) => plain(n) === "📅 2026 · the whole year" }),
    ).toBeInTheDocument();
  });
});

describe("the year behind its row (QD)", () => {
  const openYear = async () => {
    fireEvent.click(
      await screen.findByRole("button", { name: (n) => plain(n).startsWith("📅 2026") }),
    );
    return screen.findByRole("heading", { level: 1, name: "2026" });
  };

  it("opens a lazy layer: the year's total, twelve months, the legend", async () => {
    vi.stubGlobal("scrollTo", vi.fn());
    stubApi();
    renderStats();
    await month("October 2026");

    const heading = await openYear();

    expect(heading).toHaveFocus();
    expect(screen.queryByRole("heading", { level: 1, name: "My practice" })).toBeNull(); // hidden
    expect(screen.getByText(byText("1 practice in 2026"))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: (n) => plain(n) === "Share: 2026" })).toBeVisible();
    const months = [...document.querySelectorAll(".mini-month")];
    expect(months).toHaveLength(12);
    expect(months.map((m) => m.getAttribute("aria-label")).slice(0, 2)).toEqual([
      "January",
      "February",
    ]);
    expect(legend()).toEqual(["Practice", "Rest", "🌙 Moon day", "🌱 No practice"]);
    // The month the tab shows is marked; the months to come can't be opened.
    expect(screen.getByRole("button", { name: "October" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "September" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: "November" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next year" })).toBeDisabled();
  });

  it("draws the year in the month's three fills, and never marks a ladies' holiday", async () => {
    localStorage.setItem("stats.showLadies", "1"); // even so
    vi.stubGlobal("scrollTo", vi.fn());
    const s = stats({ auto: [{ date: "2026-10-10", kind: "day_off", also_day_off: false }] });
    s.cells[oct(1)] = "sick";
    s.cells[oct(7)] = "skipped";
    stubApi(s);
    renderStats();
    await month("October 2026");
    await openYear();

    const october = screen.getByRole("button", { name: "October" });
    const cells = [...october.querySelectorAll("rect")];
    const cell = (d: number) => cells[d - 1] as SVGRectElement;
    expect(cell(1).getAttribute("class")).toBe("cell rest"); // sick
    expect(cell(10).getAttribute("class")).toBe("cell rest"); // an unlogged day off
    expect(cell(18).getAttribute("class")).toBe("cell rest"); // 🌸
    expect(plain(cell(18).textContent)).toBe("Sun, Oct 18: 😌 Rest day");
    expect(cell(17).getAttribute("class")).toBe("cell practiced");
    expect(cell(7).getAttribute("class")).toBe("cell skipped");
    // Nothing logged and the days to come look the same: no past day is singled out.
    expect(cell(12).getAttribute("class")).toBe("cell");
    expect(cell(30).getAttribute("class")).toBe("cell");
    expect(october.querySelectorAll("circle.moon-ring")).toHaveLength(1); // Oct 25
  });

  it("a tap on a month closes the layer on that month", async () => {
    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);
    vi.stubGlobal("scrollY", 300);
    stubApi();
    renderStats();
    await month("October 2026");
    await openYear();

    fireEvent.click(screen.getByRole("button", { name: "September" }));

    const title = await month("September 2026");
    expect(title).toBeVisible();
    expect(title).toHaveFocus();
    expect(screen.queryByRole("heading", { level: 1, name: "2026" })).toBeNull();
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 0 }); // the month is at the top
  });

  it("Back returns to the month that was shown, where it was left", async () => {
    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);
    vi.stubGlobal("scrollY", 300);
    backButton.available = false; // so the layer shows its own back link
    stubApi();
    renderStats();
    await month("October 2026");
    fireEvent.click(previous());
    await month("September 2026");
    await openYear();
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 0 });

    fireEvent.click(screen.getByRole("button", { name: /Back/ }));

    expect(screen.getByRole("heading", { level: 2, name: "September 2026" })).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: "2026" })).toBeNull();
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 300 });
    expect(
      screen.getByRole("button", { name: (n) => plain(n).startsWith("📅 2026") }),
    ).toHaveFocus();
  });

  it("pages by year down to the first one; a month of another year opens too", async () => {
    vi.stubGlobal("scrollTo", vi.fn());
    const seen = stubApi();
    renderStats();
    await month("October 2026");
    await openYear();
    expect(statsRequests(seen)).toEqual([null]); // the year on the tab is already there

    fireEvent.click(screen.getByRole("button", { name: "Previous year" }));

    expect(await screen.findByRole("heading", { level: 1, name: "2025" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous year" })).toBeDisabled();
    expect(screen.getByText(byText("0 practices in 2025"))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Share/ })).toBeNull(); // nothing to share
    expect(screen.getByRole("button", { name: "December" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "March" }));

    expect(await month("March 2025")).toBeVisible();
    expect(statsRequests(seen)).toEqual([null, "2025"]); // read once, by the layer
    expect(next()).toBeEnabled();
  });

  it("is «2026: 5 практик» in Russian", async () => {
    vi.stubGlobal("scrollTo", vi.fn());
    const s = stats();
    s.year_total = { ...EMPTY, practiced: 5 };
    stubApi(s);
    renderStats("ru");
    fireEvent.click(
      await screen.findByRole("button", { name: (n) => plain(n) === "📅 2026 · 5 практик" }),
    );

    expect(await screen.findByText(byText("2026: 5 практик"))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Предыдущий год" })).toBeEnabled();
  });
});

describe("Stats auto-rest and the day-off question (PR-09)", () => {
  it("draws an unlogged day off as rest, named with the city for a moon day", async () => {
    stubApi(
      stats({
        auto: [
          { date: "2026-10-10", kind: "day_off", also_day_off: false },
          { date: "2026-10-03", kind: "moon", also_day_off: true },
        ],
      }),
    );
    renderStats();

    const moonDay = await screen.findByRole("button", {
      name: (n) => plain(n).startsWith("Sat, Oct 3:"),
    });
    await vi.waitFor(() => {
      // The city name comes with the cities list.
      expect(dayName(moonDay)).toBe(
        "Sat, Oct 3: 🌙 moon day (📍 Mysuru), also your day off, not logged",
      );
    });
    expect(moonDay.className).toBe("day rest");
    const dayOffCell = screen.getByRole("button", {
      name: (n) => plain(n).startsWith("Sat, Oct 10:"),
    });
    expect(dayName(dayOffCell)).toBe("Sat, Oct 10: 😌 day off, not logged");
    expect(screen.queryByText(/Day off or moon day/)).toBeNull(); // no legend item of its own
  });

  it("asks once under the month; Not now leaves a quiet link", async () => {
    dayOff = null;
    question = { weekday: 6, reminders_on: true };
    const seen = stubApi();
    const onDayOff = vi.fn();
    renderStats("en", { onDayOff });

    expect(
      await screen.findByText(
        (t) =>
          plain(t) ===
          "😌 Practice reminders don't come on Saturdays. Is that your weekly day off?",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Other…" }));
    expect(onDayOff).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));

    expect(
      await screen.findByRole("button", { name: "😌 Set your weekly day off" }),
    ).toBeInTheDocument();
    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "DELETE")).toBe(true);
    });
  });

  it("has the day-off link on the current month only", async () => {
    dayOff = null;
    stubApi();
    renderStats();

    expect(
      await screen.findByRole("button", { name: "😌 Set your weekly day off" }),
    ).toBeInTheDocument();
    fireEvent.click(previous());

    await month("September 2026");
    expect(screen.queryByRole("button", { name: "😌 Set your weekly day off" })).toBeNull();
  });

  it("shows nothing once a day off is chosen", async () => {
    stubApi();
    renderStats();
    await month("October 2026");
    expect(screen.queryByText("😌 Set your weekly day off")).not.toBeInTheDocument();
  });

  it("still renders against an API without auto-rest", async () => {
    const old: Partial<StatsData> = stats({
      months: Array.from({ length: 12 }, () => ({ ...EMPTY })),
    });
    delete old.auto;
    for (const m of old.months ?? []) delete (m as Partial<StatsSummary>).auto;
    stubApi(old as StatsData);
    renderStats();
    expect(
      await screen.findByRole("button", { name: (n) => plain(n).startsWith("Sat, Oct 3:") }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Nothing logged this month yet/)).toBeInTheDocument();
  });
});

describe("Share cards (ST-07)", () => {
  it("offers Share for a month with practice, named for what it shares", async () => {
    stubApi();
    renderStats();
    const card = (await month("October 2026")).closest("section") as HTMLElement;

    const share = within(card).getByRole("button", {
      name: (n) => plain(n) === "Share: October 2026",
    });
    expect(share).toBeVisible();
    // Beside the number it shares.
    expect(share.parentElement).toContainElement(screen.getByText(byText("1 practice")));

    fireEvent.click(previous());
    await month("September 2026");
    expect(screen.queryByRole("button", { name: /^Share/ })).toBeNull();
  });

  it("offers no Share for a month of rest only", async () => {
    const s = stats();
    s.months[9] = { ...EMPTY, rest: { ...EMPTY.rest, rest: 3 }, unlogged: 15 };
    stubApi(s);
    renderStats();

    expect(await screen.findByText(byText("0 practices"))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Share/ })).toBeNull();
  });
});

describe("Check-ins over time entry (ST-05)", () => {
  it("opens the lazy screen from My practice and comes back to the same month", async () => {
    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);
    vi.stubGlobal("scrollY", 300);
    backButton.available = false; // so the screen shows its own back link
    const seen = stubApi();
    renderStats();
    await month("October 2026");
    fireEvent.click(previous());
    await month("September 2026");
    expect(seen.some((r) => r.url.includes("/me/check-in-trends"))).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "✨ Check-ins over time" }));

    expect(await screen.findByRole("heading", { name: "Check-ins over time" })).toBeVisible();
    expect(await screen.findByText(/Nothing here yet/)).toBeVisible();
    expect(seen.some((r) => r.url.includes("/me/check-in-trends"))).toBe(true);
    expect(screen.queryByRole("heading", { name: "September 2026" })).toBeNull(); // hidden

    fireEvent.click(screen.getByRole("button", { name: /Back/ }));

    expect(screen.queryByRole("heading", { name: "Check-ins over time" })).toBeNull();
    expect(screen.getByRole("heading", { name: "September 2026" })).toBeVisible();
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 300 });
  });
});

describe("Badges entry (GM-02)", () => {
  it("opens the lazy Badges screen from My practice", async () => {
    vi.stubGlobal("scrollTo", vi.fn());
    const seen = stubApi();
    renderStats();
    await month("October 2026");
    expect(seen.some((r) => r.url.includes("/me/badges"))).toBe(false); // nothing until opened

    fireEvent.click(screen.getByRole("button", { name: "🏅 Badges" }));

    expect(await screen.findByRole("heading", { name: "Badges" })).toBeVisible();
    expect(
      await screen.findByText("Badges appear here by themselves as you log your practice."),
    ).toBeVisible();
    expect(seen.some((r) => r.url.includes("/me/badges"))).toBe(true);
  });

  it("comes back to the same month and scroll position", async () => {
    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);
    vi.stubGlobal("scrollY", 420);
    backButton.available = false; // so Badges shows its own back link
    stubApi();
    renderStats();
    await month("October 2026");
    fireEvent.click(previous());
    expect(await month("September 2026")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "🏅 Badges" }));
    await screen.findByRole("heading", { name: "Badges" });
    expect(screen.queryByRole("heading", { name: "September 2026" })).toBeNull(); // hidden
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 0 });

    fireEvent.click(screen.getByRole("button", { name: /Back/ }));

    expect(screen.queryByRole("heading", { name: "Badges" })).toBeNull();
    expect(screen.getByRole("heading", { name: "September 2026" })).toBeVisible();
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 420 });
  });

  it("is «Значки» in Russian", async () => {
    stubApi();
    renderStats("ru");
    expect(await screen.findByRole("button", { name: "🏅 Значки" })).toBeVisible();
  });
});
