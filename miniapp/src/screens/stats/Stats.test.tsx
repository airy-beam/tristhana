import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { Stats as StatsData, StatsSummary } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import Stats from "./Stats";

const backButton = vi.hoisted(() => ({ available: true }));

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => backButton.available),
}));

const TODAY = "2026-10-19";
const EMPTY: StatsSummary = {
  practiced: 0,
  possible: 0,
  skipped: 0,
  unlogged: 0,
  rest: { rest: 0, moon: 0, ladies: 0, sick: 0, travel: 0 },
  contexts: { mysore: 0, led: 0, private: 0, self: 0 },
  online: 0,
  series: [],
  unspecified: 0,
  duration: { total_min: 0, count: 0 },
};

function stats(overrides: Partial<StatsData> = {}): StatsData {
  const days = 292; // Jan 1 … Oct 19
  const cells: StatsData["cells"] = Array.from({ length: days }, () => "none");
  cells[days - 3] = "practiced"; // Oct 17
  cells[days - 2] = "ladies"; // Oct 18
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

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

function stubApi(data: StatsData = stats()): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      seen.push(request);
      const url = new URL(request.url);
      if (url.pathname === "/api/v1/me/stats") {
        const year = url.searchParams.get("year");
        return json(year ? { ...data, year: Number(year), cells: [] } : data);
      }
      if (url.pathname === "/api/v1/moon/cities") {
        return json([
          { slug: "mysuru", name_en: "Mysuru", name_ru: "Майсур", timezone: "Asia/Kolkata" },
        ]);
      }
      if (url.pathname === "/api/v1/me/days") {
        return json({ today: TODAY, timezone_known: true, days: [] });
      }
      if (request.method === "PUT") return new Response(null, { status: 204 });
      return json({});
    }),
  );
  return seen;
}

function renderStats(locale: Locale = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <Stats locale={locale} zone="Asia/Almaty" onBack={vi.fn()} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const plain = (text: string) => text.replace(/[⁨⁩]/g, "");
const byText = (text: string) => (_: string, el: Element | null) =>
  el?.tagName === "P" && plain(el.textContent) === text;

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  backButton.available = true;
});

describe("Stats", () => {
  it("shows a count without 'of' when nothing is marked 'No practice'", async () => {
    stubApi();
    renderStats();

    expect(await screen.findByText(byText("This month: 1 practice"))).toBeInTheDocument();
    expect(screen.getByText(byText("Most in a row this year: 12"))).toBeInTheDocument();
    expect(screen.queryByText(/in a row$/)).not.toBeInTheDocument(); // current run < 2
    expect(screen.getByText(byText("1 practice in 2026"))).toBeInTheDocument();
  });

  it("shows 'of' once a 'No practice' day exists, and the current run from 2", async () => {
    const s = stats({ runs: { current: 5, longest: 12 } });
    const oct = s.months[9] as StatsSummary;
    s.months[9] = { ...oct, practiced: 18, skipped: 2, possible: 20 };
    stubApi(s);
    renderStats();

    expect(
      await screen.findByText(byText("This month: practice on 18 of 20 days")),
    ).toBeInTheDocument();
    expect(screen.getByText(byText("🌿 5 practices in a row"))).toBeInTheDocument();
  });

  it("draws a ladies' holiday as rest until shown on this device", async () => {
    stubApi();
    renderStats();
    const oct18 = await screen.findByRole("button", { name: (n) => plain(n).includes("Oct 18") });

    expect(plain(oct18.getAttribute("aria-label") ?? "")).toMatch(/: 😌 Rest day$/);
    expect(oct18).toHaveClass("rest");
    expect(screen.queryByText("🌸 Ladies' holiday")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox"));

    expect(oct18).toHaveClass("ladies");
    expect(plain(oct18.getAttribute("aria-label") ?? "")).toMatch(/Ladies' holiday$/);
    expect(localStorage.getItem("stats.showLadies")).toBe("1");
  });

  it("marks moon days with a ring, also later this month", async () => {
    stubApi();
    renderStats();

    const oct25 = await screen.findByRole("button", { name: (n) => plain(n).includes("Oct 25") });
    expect(oct25).toHaveClass("moon-marker");
    expect(oct25).toBeDisabled(); // future: nothing to log yet
  });

  it("summarises the month and counts unmarked days only for this month", async () => {
    stubApi();
    renderStats();

    expect(
      await screen.findByText(byText("16 days not logged: tap a day to add it")),
    ).toBeInTheDocument();
    expect(screen.getByText("By series")).toBeInTheDocument();
    expect(
      screen.getByText(byText("⏱ 1 h 30 min in total · about 90 min per practice")),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: (n) => plain(n).startsWith("September") }));
    expect(
      await screen.findByText(
        byText("Nothing logged this month yet. Days you log will show up here."),
      ),
    ).toBeInTheDocument();
  });

  it("opens the day editor and logs a past day", async () => {
    const seen = stubApi();
    renderStats();
    fireEvent.click(
      await screen.findByRole("button", { name: (n) => plain(n).includes("Oct 16") }),
    );

    const editor = await screen.findByRole("region", { name: (n) => plain(n).includes("Oct 16") });
    fireEvent.click(within(editor).getByRole("button", { name: "😌 Rest day" }));

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PUT")).toBe(true);
    });
    const put = seen.find((r) => r.method === "PUT");
    expect(new URL(put?.url ?? "").pathname).toBe("/api/v1/me/days/2026-10-16");
  });

  it("bounds the year arrows by the first year with data", async () => {
    const seen = stubApi();
    renderStats();
    const next = await screen.findByRole("button", { name: "Next year" });
    expect(next).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Previous year" }));

    await vi.waitFor(() => {
      expect(seen.some((r) => new URL(r.url).searchParams.get("year") === "2025")).toBe(true);
    });
    expect(await screen.findByRole("button", { name: "Previous year" })).toBeDisabled();
  });

  it("uses Russian plurals and «подряд»", async () => {
    const s = stats({ runs: { current: 21, longest: 21 } });
    s.year_total = { ...EMPTY, practiced: 5 };
    stubApi(s);
    renderStats("ru");

    expect(await screen.findByText(byText("🌿 21 практика подряд"))).toBeInTheDocument();
    expect(screen.getByText(byText("2026: 5 практик"))).toBeInTheDocument();
  });

  it("keeps 'No practice' in the summary without rest days, and is quiet at zero", async () => {
    const s = stats();
    s.months[9] = { ...EMPTY, practiced: 0, skipped: 2, possible: 2, unlogged: 16 };
    stubApi(s);
    renderStats();

    expect(await screen.findByText("🌱 No practice")).toBeInTheDocument();
    expect(screen.queryByText(/^This month/)).not.toBeInTheDocument(); // nothing practised yet
  });

  it("invites to fill in an empty current month", async () => {
    const s = stats();
    s.months[9] = { ...EMPTY, unlogged: 18 };
    stubApi(s);
    renderStats();

    expect(
      await screen.findByText(byText("18 days not logged: tap a day to add it")),
    ).toBeInTheDocument();
  });

  it("names moon days and today for screen readers", async () => {
    stubApi();
    renderStats();

    const oct25 = await screen.findByRole("button", { name: (n) => plain(n).includes("Oct 25") });
    expect(plain(oct25.getAttribute("aria-label") ?? "")).toMatch(/: full or new moon$/);
    const today = screen.getByRole("button", { name: (n) => plain(n).includes("Oct 19") });
    expect(today).toHaveAttribute("aria-current", "date");
  });

  it("the editor keeps a ladies' holiday as rest while the switch is off", async () => {
    const seen = stubApi();
    vi.stubGlobal(
      "fetch",
      vi.fn((request: Request) => {
        seen.push(request);
        const url = new URL(request.url);
        if (url.pathname === "/api/v1/me/days") {
          return json({
            today: TODAY,
            timezone_known: true,
            days: [{ date: "2026-10-18", status: "ladies", practices: [] }],
          });
        }
        if (url.pathname === "/api/v1/me/stats") return json(stats());
        return json([]);
      }),
    );
    renderStats();
    fireEvent.click(
      await screen.findByRole("button", { name: (n) => plain(n).includes("Oct 18") }),
    );

    const editor = await screen.findByRole("region", { name: (n) => plain(n).includes("Oct 18") });
    const rest = await within(editor).findByRole("button", { name: "😌 Rest day", pressed: true });
    expect(
      within(editor).queryByRole("button", { name: "🌸 Ladies' holiday" }),
    ).not.toBeInTheDocument();
    fireEvent.click(rest);
    expect(seen.some((r) => r.method === "PUT")).toBe(false); // never downgraded to rest
  });

  it("has its own back link when Telegram's is unavailable", async () => {
    backButton.available = false;
    stubApi();
    renderStats();

    expect(await screen.findByRole("button", { name: "‹ Back" })).toBeInTheDocument();
  });
});
