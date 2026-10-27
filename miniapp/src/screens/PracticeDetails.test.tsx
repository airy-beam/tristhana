import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import type { Catalog, Days, PracticePresets } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import type { Locale } from "../i18n/negotiate";
import { zoneLabel } from "./practiceText";
import { TodayCard } from "./TodayCard";

vi.mock("../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
}));

const TODAY = "2026-10-19";

const CATALOG: Catalog = {
  version: "v1",
  check_in_tags: [],
  series: [
    {
      slug: "primary",
      number: 1,
      name_en: "Primary series",
      name_ru: "Первая серия",
      halves_split: "navasana",
      stops: [
        { key: "navasana", latin: "Navasana", ru: "Навасана" },
        { key: "setu-bandhasana", latin: "Setu Bandhasana", ru: "Сету Бандхасана" },
      ],
    },
    {
      slug: "intermediate",
      number: 2,
      name_en: "Intermediate series",
      name_ru: "Вторая серия",
      halves_split: null,
      stops: [
        { key: "pasasana", latin: "Pasasana", ru: "Пашасана" },
        { key: "karandavasana", latin: "Karandavasana", ru: "Карандавасана" },
      ],
    },
  ],
};

const PRESETS: PracticePresets = {
  last: {
    slot: 1,
    context: "led",
    online: false,
    length: { series: ["primary"], end: null, first_part: null },
    duration_min: 90,
    start_time: null,
    timezone: "Asia/Almaty",
  },
  presets: [
    { kind: "short", length: { series: [], end: null, first_part: null } },
    { kind: "half_primary", length: { series: ["primary"], end: "navasana", first_part: null } },
    { kind: "full_primary", length: { series: ["primary"], end: null, first_part: null } },
    {
      kind: "recent",
      length: { series: ["primary", "intermediate"], end: "pasasana", first_part: null },
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// Default: echo a valid practice built from the PUT body.
const echo = async (request: Request) =>
  json({ slot: 1, timezone: null, ...((await request.json()) as object) });
let putResponse: (request: Request) => Response | Promise<Response> = echo;

/** A fake server that remembers the last saved practice (GET /me/days reflects it). */
function stubApi(days: Days): Request[] {
  const seen: Request[] = [];
  let saved: unknown = null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request);
      const path = new URL(request.url).pathname;
      if (request.method === "PUT") {
        const response = await putResponse(request.clone());
        saved = await response.clone().json();
        return response;
      }
      if (path === "/api/v1/catalog") return json(CATALOG);
      if (path === "/api/v1/me/moon-days")
        return json({ location: { slug: "mysuru", explicit: false }, today: TODAY, days: [] });
      if (path === "/api/v1/moon/cities") return json([]);
      if (path.endsWith("/practice-presets")) return json(PRESETS);
      if (!saved) return json(days);
      return json({
        ...days,
        days: days.days.map((d) => (d.date === TODAY ? { ...d, practices: [saved] } : d)),
      });
    }),
  );
  return seen;
}

const practicedToday: Days = {
  periods: [], // WH-01 part 2
  practice_on: false,
  today: TODAY,
  timezone_known: true,
  auto: [],
  moon_location: "mysuru",
  days: [{ date: TODAY, status: "practiced", practices: [], check_ins: [] }],
};

function renderCard(zone: string | null = "Asia/Almaty", locale: Locale = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <TodayCard zone={zone} locale={locale} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

async function lastPut(seen: Request[]): Promise<unknown> {
  await vi.waitFor(() => {
    expect(seen.some((r) => r.method === "PUT")).toBe(true);
  });
  const puts = seen.filter((r) => r.method === "PUT");
  const put = puts[puts.length - 1];
  expect(new URL(put?.url ?? "").pathname).toBe(`/api/v1/me/days/${TODAY}/practices/1`);
  return put?.json();
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PracticeDetails", () => {
  it("is shown only on a practiced day", async () => {
    stubApi({
      ...practicedToday,
      days: [{ date: TODAY, status: "rest", practices: [], check_ins: [] }],
    });
    renderCard();

    await screen.findByRole("button", { name: /Rest day/, pressed: true });
    expect(screen.queryByRole("button", { name: "Mysore" })).not.toBeInTheDocument();
  });

  it("a context tap saves the whole practice", async () => {
    const seen = stubApi(practicedToday);
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: "Mysore" }));

    expect(await lastPut(seen)).toEqual({
      context: "mysore",
      online: false,
      length: null,
      duration_min: null,
      start_time: null,
    });
  });

  it("same as last time copies context, length and duration", async () => {
    const seen = stubApi(practicedToday);
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: "🔁 Same as last time" }));

    expect(await lastPut(seen)).toEqual({
      context: "led",
      online: false,
      length: { series: ["primary"], end: null, first_part: null },
      duration_min: 90,
      start_time: null,
    });
  });

  it("shows presets and recent lengths with their labels", async () => {
    stubApi(practicedToday);
    renderCard();

    expect(await screen.findByRole("button", { name: "Full Primary" })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Primary + Intermediate → Pasasana" }),
    ).toBeInTheDocument();
  });

  it("the custom picker offers half Primary + Intermediate", async () => {
    const seen = stubApi(practicedToday);
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "🎯 Other…" }));

    const [range, end] = screen.getAllByRole("combobox");
    fireEvent.change(range as HTMLElement, { target: { value: "12second_half" } });
    fireEvent.change(end as HTMLElement, { target: { value: "pasasana" } });

    expect(await lastPut(seen)).toMatchObject({
      length: { series: ["primary", "intermediate"], end: "pasasana", first_part: "second_half" },
    });
  });

  it("offers the start time with a zone label only when the zone is known", async () => {
    stubApi(practicedToday);
    const { unmount } = renderCard("Asia/Almaty");
    expect(await screen.findByText("Almaty (UTC+5)")).toBeInTheDocument();
    unmount();

    stubApi(practicedToday);
    renderCard(null);
    await screen.findByRole("button", { name: "Mysore" });
    expect(screen.queryByText(/Start time/)).not.toBeInTheDocument();
  });

  it("self-practice hides the online toggle", async () => {
    stubApi({
      ...practicedToday,
      days: [
        {
          date: TODAY,
          status: "practiced",
          practices: [{ slot: 1, context: "self", online: false, timezone: null }],
          check_ins: [],
        },
      ],
    });
    renderCard();

    await screen.findByRole("button", { name: "Self-practice", pressed: true });
    expect(screen.queryByRole("button", { name: "🌐 Online" })).not.toBeInTheDocument();
  });
});

describe("PracticeDetails server sync", () => {
  it("the server's normalised practice wins over the optimistic one", async () => {
    putResponse = () =>
      json({
        slot: 1,
        context: null,
        online: false,
        length: { series: ["primary"], end: null, first_part: null },
        duration_min: null,
        start_time: null,
        timezone: null,
      });
    stubApi(practicedToday);
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: "½ Primary → Navasana" }));

    // The fake server answers "full Primary": that's what ends up highlighted.
    expect(
      await screen.findByRole("button", { name: "Full Primary", pressed: true }),
    ).toBeInTheDocument();
    putResponse = echo;
  });

  it("saves the start time on blur, not on every keystroke", async () => {
    const seen = stubApi(practicedToday);
    renderCard();
    const input = await screen.findByLabelText(/Start time/);

    fireEvent.change(input, { target: { value: "06:3" } });
    fireEvent.change(input, { target: { value: "06:30" } });
    expect(seen.some((r) => r.method === "PUT")).toBe(false);
    fireEvent.blur(input);

    expect(await lastPut(seen)).toMatchObject({ start_time: "06:30" });
  });
});

describe("zoneLabel", () => {
  it.each([
    ["Asia/Almaty", "Almaty (UTC+5)"],
    ["Asia/Kolkata", "Kolkata (UTC+5:30)"],
    ["America/New_York", "New York (UTC-4)"],
    ["UTC", "UTC"],
  ])("%s -> %s", (zone, label) => {
    expect(zoneLabel(zone, "2026-10-19")).toBe(label);
  });
});
