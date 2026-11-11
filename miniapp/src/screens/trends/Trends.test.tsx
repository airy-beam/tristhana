import { FluentBundle, FluentResource } from "@fluent/bundle";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";

import type { CheckInTrends, TrendScales } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import enTrends from "../../locales/en/trends.ftl?raw";
import ruTrends from "../../locales/ru/trends.ftl?raw";
import TrendsScreen from "./Trends";

// ST-05 (spec §2, §8): the empty and too-few states show no figure; dots only for months that
// have an average and nothing drawn between them; "—" cells and their note only when one is on
// screen; the weekday and moon sections are absent on null; what is read aloud; RU plurals and
// the decimal comma; the city in the moon note; load failure; the avoid-word grep; en/ru parity.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
}));

const NONE: TrendScales = { mood: null, energy: null, effort: null };
const MONTHS = [
  "2025-12",
  ...Array.from({ length: 11 }, (_, i) => `2026-${String(i + 1).padStart(2, "0")}`),
];

function trends(over: Partial<CheckInTrends> = {}): CheckInTrends {
  return {
    from: "2025-12-01",
    to: "2026-11-11",
    total: 40,
    enough: true,
    min_total: 10,
    min_bucket: 5,
    months: MONTHS.map((month) => ({
      month,
      ...NONE,
      ...(month === "2026-10" ? { energy: { mean: 3.4, n: 21 } } : {}),
      ...(month === "2026-09" ? { energy: { mean: 2, n: 5 }, mood: { mean: 4.5, n: 5 } } : {}),
    })),
    weekdays: [
      { ...NONE, energy: { mean: 3.4, n: 6 } },
      NONE,
      { ...NONE, energy: { mean: 4, n: 5 } },
      NONE,
      NONE,
      NONE,
      NONE,
    ],
    moon: {
      location: "almaty",
      full: { ...NONE, energy: { mean: 2.5, n: 5 } },
      new: NONE,
      other: { ...NONE, energy: { mean: 3.4, n: 22 } },
    },
    ...over,
  };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

function stubApi(body: CheckInTrends | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/me/check-in-trends")
        return Promise.resolve(body ? json(body) : json({ code: null }, 503));
      if (path === "/api/v1/moon/cities")
        return Promise.resolve(
          json([{ slug: "almaty", name_en: "Almaty", name_ru: "Алматы", timezone: "Asia/Almaty" }]),
        );
      return Promise.resolve(json({}));
    }),
  );
}

function renderTrends(locale: Locale = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <TrendsScreen locale={locale} onBack={vi.fn()} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
const says = (text: string) => (_: string, el: Element | null) => plain(el?.textContent) === text;
const section = (name: string) =>
  screen.getByRole("heading", { name }).closest("section") as HTMLElement;
/** What a screen reader says for each figure: real text in the cell, not an `aria-label`. */
const labels = (root: HTMLElement) =>
  [...root.querySelectorAll("td > .visually-hidden")].map((el) => plain(el.textContent));
/** What a sighted person sees in each cell. */
const shown = (row: Element | null | undefined) =>
  [...(row?.querySelectorAll("td > [aria-hidden='true']") ?? [])].map((el) => el.textContent);

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Check-ins over time", () => {
  it("says so when there is nothing yet, and shows no figure", async () => {
    stubApi(trends({ total: 0, enough: false, months: [], weekdays: null, moon: null }));
    const { container } = renderTrends();

    expect(
      await screen.findByText(
        "Nothing here yet. Averages of the check-ins you add after practice will show up on this screen.",
      ),
    ).toBeVisible();
    expect(container.querySelector("table, svg")).toBeNull();
  });

  it("names the minimum when there are too few, never how many are left", async () => {
    stubApi(trends({ total: 7, enough: false, months: [], weekdays: null, moon: null }));
    const { container } = renderTrends();

    expect(await screen.findByText(says("Averages appear here from 10 check-ins."))).toBeVisible();
    expect(container.querySelector("table, svg")).toBeNull();
    expect(screen.queryByText(/7/)).toBeNull();
  });

  it("draws a dot only for a month with an average, and nothing between dots", async () => {
    stubApi(trends());
    renderTrends();
    await screen.findByRole("heading", { name: "By month" });
    const months = section("By month");

    const [mood, energy, effort] = [...months.querySelectorAll("svg")] as [
      SVGSVGElement,
      SVGSVGElement,
      SVGSVGElement,
    ];
    expect(mood.querySelectorAll("circle")).toHaveLength(1);
    expect(energy.querySelectorAll("circle")).toHaveLength(2);
    expect(effort.querySelectorAll("circle")).toHaveLength(0);
    expect(months.querySelector("path, polyline")).toBeNull();
    expect(energy.querySelectorAll("line")).toHaveLength(3); // the faint 1, 3 and 5 lines only
    expect(energy).toHaveAttribute("aria-hidden", "true");
    // A higher average sits higher on the fixed 1-5 axis.
    const heights = [...energy.querySelectorAll("circle")].map((c) => Number(c.getAttribute("cy")));
    const [september = 0, october = 0] = heights;
    expect(heights).toHaveLength(2);
    expect(october).toBeLessThan(september);
  });

  it("gives the months as a table to a screen reader", async () => {
    stubApi(trends());
    renderTrends();
    await screen.findByRole("heading", { name: "By month" });

    const table = within(section("By month")).getByRole("table", { name: "By month" });
    expect(table.parentElement).toHaveClass("visually-hidden");
    expect(labels(table)).toContain("Energy, October 2026: 3.4 on average, 21 check-ins");
    expect(labels(table)).toContain("Mood, September 2026: 4.5 on average, 5 check-ins");
    expect(labels(table)).toContain("Effort, October 2026: no average");
  });

  it("shows weekdays Monday first, each figure with its count", async () => {
    stubApi(trends());
    renderTrends();
    await screen.findByRole("heading", { name: "By weekday" });
    const table = within(section("By weekday")).getByRole("table");

    const heads = within(table)
      .getAllByRole("columnheader")
      .map((th) => th.textContent);
    expect(heads).toEqual(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
    const energy = within(table).getByRole("rowheader", { name: "Energy" }).closest("tr");
    expect(shown(energy)).toEqual(["3.46", "—", "4.05", "—", "—", "—", "—"]);
    expect(labels(table)).toContain("Energy, Monday: 3.4 on average, 6 check-ins");
  });

  it("sets days near a full or new moon beside the others, naming the city", async () => {
    stubApi(trends());
    renderTrends();
    await screen.findByRole("heading", { name: "Near full and new moon" });
    const moon = section("Near full and new moon");

    expect(
      within(moon)
        .getAllByRole("columnheader")
        .map((th) => th.textContent),
    ).toEqual(["🌕 Near full moon", "🌑 Near new moon", "Other days"]);
    expect(labels(moon)).toContain("Energy, Near full moon: 2.5 on average, 5 check-ins");
    expect(
      await within(moon).findByText(
        says(
          '"Near" is the day of the full or new moon, the day before and the day after. Dates for 📍 Almaty.',
        ),
      ),
    ).toBeVisible();
  });

  it("reads each figure aloud from text in the cell, without emoji", async () => {
    stubApi(trends());
    const { container } = renderTrends();
    await screen.findByRole("heading", { name: "Near full and new moon" });

    // `aria-label` on a plain cell is ignored by several screen readers (Q294).
    expect(container.querySelector("td[aria-label]")).toBeNull();
    const cells = [...container.querySelectorAll("tbody td")];
    expect(cells.length).toBeGreaterThan(0);
    for (const td of cells) {
      expect(td.querySelector(":scope > [aria-hidden='true']")).not.toBeNull();
      expect(td.querySelector(":scope > .visually-hidden")).not.toBeNull();
    }
    for (const label of labels(container)) expect(label).not.toMatch(/\p{Extended_Pictographic}/u);
    for (const th of container.querySelectorAll("th")) {
      expect(th.getAttribute("aria-label")).not.toMatch(/\p{Extended_Pictographic}/u);
    }
    const moon = section("Near full and new moon");
    expect(within(moon).getByRole("columnheader", { name: "Near full moon" })).toHaveTextContent(
      "🌕 Near full moon",
    );
  });

  it("explains the dash only when one is on screen", async () => {
    stubApi(trends());
    renderTrends();
    await screen.findByRole("heading", { name: "By weekday" });
    expect(screen.getByText(says('"—" means fewer than 5 check-ins there.'))).toBeVisible();
  });

  it("leaves the dash note out when every shown cell has a figure", async () => {
    const full: TrendScales = {
      mood: { mean: 3, n: 5 },
      energy: { mean: 3, n: 5 },
      effort: { mean: 3, n: 5 },
    };
    stubApi(trends({ weekdays: Array.from({ length: 7 }, () => full), moon: null }));
    renderTrends();
    await screen.findByRole("heading", { name: "By weekday" });

    expect(screen.queryByText(/fewer than/)).toBeNull();
    expect(screen.getByText(/small number/)).toBeVisible();
  });

  it("leaves the weekday and moon sections out when the server sends none", async () => {
    stubApi(trends({ weekdays: null, moon: null }));
    renderTrends();
    await screen.findByRole("heading", { name: "By month" });

    expect(screen.queryByRole("heading", { name: "By weekday" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Near full and new moon" })).toBeNull();
    expect(screen.queryByText(/fewer than/)).toBeNull();
    expect(screen.queryByText(/small number/)).toBeNull();
  });

  it("labels each strip with the ends of its axis", async () => {
    stubApi(trends());
    renderTrends();
    await screen.findByRole("heading", { name: "By month" });

    const captions = [...section("By month").querySelectorAll("figcaption")].map((c) =>
      plain(c.textContent),
    );
    expect(captions).toEqual([
      "💭 Mood: 1 😔 → 5 😊",
      "⚡ Energy: 1 low → 5 high",
      "🔥 Effort: 1 easy → 5 hard",
    ]);
  });

  it("renders a payload from an older server that has no moon field", async () => {
    const older: Partial<CheckInTrends> = trends();
    delete older.moon;
    stubApi(older as CheckInTrends);
    renderTrends();

    expect(await screen.findByRole("heading", { name: "By weekday" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Near full and new moon" })).toBeNull();
  });

  it("always closes with the note that the app draws no conclusions", async () => {
    stubApi(trends());
    renderTrends();

    expect(
      await screen.findByText(
        "These are averages of your own check-ins. The app draws no conclusions from them. Teachers and shalas don't see them.",
      ),
    ).toBeVisible();
  });

  it("says so when loading fails", async () => {
    stubApi(null);
    renderTrends();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't load this. Try again in a moment.",
    );
  });

  it("uses the decimal comma, Russian names and the city in Russian", async () => {
    stubApi(trends());
    renderTrends("ru");
    await screen.findByRole("heading", { name: "По дням недели" });

    const table = within(section("По дням недели")).getByRole("table");
    expect(labels(table)).toContain("Энергия, понедельник: в среднем 3,4, 6 отметок");
    expect(
      await screen.findByText(
        says("«Около» — день полнолуния или новолуния, день до и день после. Даты для 📍 Алматы."),
      ),
    ).toBeVisible();
  });
});

describe("trends.ftl", () => {
  const bundle = (locale: Locale, source: string) => {
    const b = new FluentBundle(locale, { useIsolating: false });
    expect(b.addResource(new FluentResource(source))).toEqual([]);
    return b;
  };
  const en = bundle("en", enTrends);
  const ru = bundle("ru", ruTrends);
  const keys = (source: string) =>
    [...source.matchAll(/^([a-z][a-z0-9-]*) *=/gm)].map((m) => m[1]).sort();
  const say = (b: FluentBundle, id: string, args: Record<string, string | number>) => {
    const pattern = b.getMessage(id)?.value;
    return pattern ? b.formatPattern(pattern, args) : "";
  };

  it("has the same keys in both languages", () => {
    expect(keys(ruTrends)).toEqual(keys(enTrends));
  });

  it.each([
    [1, "1 отметка"],
    [2, "2 отметки"],
    [5, "5 отметок"],
    [21, "21 отметка"],
  ])("counts Russian check-ins through Fluent (%i)", (n, tail) => {
    const said = say(ru, "trends-cell-label", { scale: "S", where: "W", mean: "3,0", n });
    expect(said).toBe(`S, W: в среднем 3,0, ${tail}`);
  });

  it("counts one English check-in in the singular", () => {
    const args = { scale: "S", where: "W", mean: "3.0" };
    expect(say(en, "trends-cell-label", { ...args, n: 1 })).toBe(
      "S, W: 3.0 on average, 1 check-in",
    );
    expect(say(en, "trends-cell-label", { ...args, n: 2 })).toBe(
      "S, W: 3.0 on average, 2 check-ins",
    );
  });

  // Figures only (spec §2): no comparison, cause, advice, score or statistics word.
  const AVOID_EN =
    /streak|broken|missed|better|worse|lower|higher|because|affect|influence|depend|correlat|trend|\btend|pattern|normal|cycle|score|usually|should|\bbad\b|pain|\bonly\b/i;
  const AVOID_RU =
    /влия|завис|коррел|тренд|обычно|лучш|худш|хуже|выше|ниже|норм|цикл|из-за|потому|только|долж|плох|боль/i;
  const text = (source: string) =>
    source
      .split("\n")
      .filter((line) => !line.startsWith("#"))
      .map((line) => line.replace(/^[a-z][a-z0-9-]* *=/, ""))
      .join("\n");

  it("uses none of the words to avoid", () => {
    expect(text(enTrends)).not.toMatch(AVOID_EN);
    expect(text(ruTrends)).not.toMatch(AVOID_RU);
    expect(text(enTrends)).not.toMatch(/Purnima|Amavasya/i);
    expect(text(ruTrends)).not.toMatch(/Пурнима|Амавасья/i);
  });
});
