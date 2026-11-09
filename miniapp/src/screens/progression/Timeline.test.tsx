import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { Catalog, Timeline as TimelineValue, TimelineEntry } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import Progression from "./Progression";
import Timeline from "./Timeline";

// ST-04 (spec §2, §8): the read-only timeline. Year headings; series lines above the give in
// practice order; one series or both named on a jump; the quiet line for an asana given again;
// who marked it; Share only on given entries; muted corrections and removals (Q227 wording);
// both empty states; the truncated line; dates never shift with the device zone.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
}));

vi.mock("../share/ShareButton", () => ({
  ShareButton: ({ label }: { label?: string }) => (
    <button type="button" data-testid="share">
      {label}
    </button>
  ),
}));

const CATALOG: Catalog = {
  version: "v1",
  check_in_tags: [],
  milestone_items: [{ key: "drop-backs", latin: "Drop-backs", ru: "Дроп-бэки" }],
  series: [
    {
      slug: "primary",
      number: 1,
      name_en: "Primary series",
      name_ru: "Первая серия",
      halves_split: "navasana",
      traditional: { key: "primary", latin: "Yoga Chikitsa", ru: "Йога Чикитса" },
      stops: [
        { key: "navasana", latin: "Navasana", ru: "Навасана" },
        { key: "bhujapidasana", latin: "Bhujapidasana", ru: "Бхуджапидасана" },
        { key: "kurmasana", latin: "Kurmasana", ru: "Курмасана" },
        { key: "setu-bandhasana", latin: "Setu Bandhasana", ru: "Сету Бандхасана" },
      ],
    },
    {
      slug: "intermediate",
      number: 2,
      name_en: "Intermediate series",
      name_ru: "Вторая серия",
      halves_split: null,
      traditional: { key: "intermediate", latin: "Nadi Shodhana", ru: "Нади Шодхана" },
      stops: [
        { key: "pasasana", latin: "Pasasana", ru: "Пашасана" },
        { key: "krounchasana", latin: "Krounchasana", ru: "Краунчасана" },
      ],
    },
  ],
};

const P = (series: string | null, last: string | null) => ({ series, last });

function entry(over: Partial<TimelineEntry> & Pick<TimelineEntry, "id" | "kind">): TimelineEntry {
  return {
    occurred_on: "2026-03-01",
    from: null,
    to: null,
    item: null,
    by: "self",
    by_name: null,
    celebrations: [],
    length: null,
    ...over,
  };
}

const START = entry({
  id: 1,
  kind: "start",
  occurred_on: "2025-12-31",
  to: P("primary", "navasana"),
  length: { series: ["primary"], end: "navasana", first_part: null },
});

const FULL: TimelineValue = {
  set: true,
  truncated: false,
  entries: [
    entry({ id: 8, kind: "item_removed", item: "drop-backs", occurred_on: "2026-06-01" }),
    // Given again after the correction below: quiet, no markers.
    entry({
      id: 7,
      kind: "given",
      from: P("primary", "setu-bandhasana"),
      to: P("intermediate", "pasasana"),
      occurred_on: "2026-05-01",
    }),
    entry({
      id: 6,
      kind: "changed",
      from: P("intermediate", "pasasana"),
      to: P("primary", "setu-bandhasana"),
      occurred_on: "2026-04-01",
    }),
    // A teacher's jump across the boundary; the server's order puts "begins" first here, the
    // screen must still show Full Primary first.
    entry({
      id: 5,
      kind: "given",
      by: "teacher",
      by_name: "Anna",
      from: P("primary", "kurmasana"),
      to: P("intermediate", "pasasana"),
      occurred_on: "2026-03-01",
      celebrations: [
        {
          kind: "new_asana",
          series: "intermediate",
          key: "pasasana",
          first: P("primary", "setu-bandhasana"),
        },
        { kind: "series_begins", series: "intermediate", key: null, first: null },
        { kind: "series_complete", series: "primary", key: null, first: null },
      ],
    }),
    entry({
      id: 4,
      kind: "item_given",
      item: "drop-backs",
      occurred_on: "2026-02-01",
      celebrations: [{ kind: "item", series: null, key: "drop-backs", first: null }],
    }),
    // A deleted or unlinked teacher: "a teacher"; a jump within one series.
    entry({
      id: 3,
      kind: "given",
      by: "teacher",
      by_name: null,
      from: P("primary", "navasana"),
      to: P("primary", "kurmasana"),
      occurred_on: "2026-01-01",
      celebrations: [
        {
          kind: "new_asana",
          series: "primary",
          key: "kurmasana",
          first: P("primary", "bhujapidasana"),
        },
      ],
    }),
    START,
  ],
};

function stubApi(timeline: TimelineValue) {
  const seen: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      const path = new URL(request.url).pathname;
      seen.push(path);
      const body =
        path === "/api/v1/catalog"
          ? CATALOG
          : path === "/api/v1/me/progression/timeline"
            ? timeline
            : path === "/api/v1/me/progression"
              ? {
                  set: true,
                  position: P("primary", "navasana"),
                  length: { series: ["primary"], end: "navasana", first_part: null },
                  by_series: [],
                  items: [],
                  next: null,
                  later: [],
                  suggested: null,
                  suggested_length: null,
                  events: [],
                  last_event_id: 1,
                  today: "2026-06-01",
                  marked: null,
                }
              : {};
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
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

const text = (el: Element | undefined) => (el?.textContent ?? "").replace(/[⁨⁩]/g, "");

afterEach(() => {
  vi.unstubAllGlobals();
});

test("entries sit under year headings, newest first", async () => {
  stubApi(FULL);
  renderWith(<Timeline locale="en" onBack={vi.fn()} />);

  const years = await screen.findAllByRole("heading", { level: 2 });
  expect(years.map(text)).toEqual(["2026", "2025"]);
  const items = screen.getAllByRole("listitem").map(text);
  expect(items).toHaveLength(7);
  expect(items[6]).toMatch(/Dec 31.*Record begins: /);
});

test("a jump across series names both series, with Full Primary before Intermediate begins", async () => {
  stubApi(FULL);
  renderWith(<Timeline locale="en" onBack={vi.fn()} />);

  const crossing = text((await screen.findAllByRole("listitem"))[3]);
  expect(crossing).toContain("Setu Bandhasana (Primary) → Pasasana (Intermediate)");
  expect(crossing.match(/🎉/g)).toHaveLength(2);
  expect(crossing).toContain("· Anna");
  expect(crossing.indexOf("Full Primary")).toBeGreaterThanOrEqual(0);
  expect(crossing.indexOf("Full Primary")).toBeLessThan(crossing.indexOf("Intermediate begins"));
  expect(crossing.indexOf("Intermediate begins")).toBeLessThan(crossing.indexOf("Setu Bandhasana"));
});

test("a jump within one series shows the range, the series and 'a teacher'", async () => {
  stubApi(FULL);
  renderWith(<Timeline locale="en" onBack={vi.fn()} />);

  const jump = text((await screen.findAllByRole("listitem"))[5]);
  expect(jump).toContain("🎉 Bhujapidasana → Kurmasana");
  expect(jump).toContain("· Primary");
  expect(jump).toContain("· a teacher");
});

test("an asana given again is quiet: no 🎉, no series lines", async () => {
  stubApi(FULL);
  renderWith(<Timeline locale="en" onBack={vi.fn()} />);

  const quiet = text((await screen.findAllByRole("listitem"))[1]);
  expect(quiet).toContain("Pasasana again");
  expect(quiet).not.toContain("🎉");
  expect(quiet).not.toContain("begins");
});

test("corrections and removals are muted; removal uses the gentle wording", async () => {
  stubApi(FULL);
  renderWith(<Timeline locale="en" onBack={vi.fn()} />);

  const items = await screen.findAllByRole("listitem");
  const muted = items.map((li) => li.classList.contains("muted"));
  expect(text(items[0])).toContain("Drop-backs: set aside");
  expect(text(items[2])).toContain("Changed to Setu Bandhasana");
  expect(muted).toEqual([true, false, true, false, false, false, false]);
  expect(text(items[4])).toContain("🎉 Drop-backs");
});

test("Share appears on given entries only, and there is no Undo", async () => {
  stubApi(FULL);
  renderWith(<Timeline locale="en" onBack={vi.fn()} />);

  await screen.findAllByRole("listitem");
  expect(screen.getAllByTestId("share")).toHaveLength(3);
  expect(screen.queryByText(/Undo/)).toBeNull();
});

test("unset: an explanation and a way back", async () => {
  stubApi({ set: false, truncated: false, entries: [] });
  const onBack = vi.fn();
  renderWith(<Timeline locale="en" onBack={onBack} />);

  expect(await screen.findByText(/your timeline starts from there/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /My asanas/ }));
  expect(onBack).toHaveBeenCalled();
});

test("only the start: the start row and a hint", async () => {
  stubApi({ set: true, truncated: false, entries: [START] });
  renderWith(<Timeline locale="en" onBack={vi.fn()} />);

  expect(await screen.findByText(/New asanas will appear here/)).toBeInTheDocument();
  expect(screen.getAllByRole("listitem")).toHaveLength(1);
});

test("a standing-only start reads as standing", async () => {
  const standing = entry({ id: 1, kind: "start", to: P(null, null) });
  stubApi({ set: true, truncated: false, entries: [standing] });
  renderWith(<Timeline locale="en" onBack={vi.fn()} />);

  const row = text(await screen.findByRole("listitem"));
  expect(row).toMatch(/Record begins: .*standing/i);
});

test("a cut history says so", async () => {
  stubApi({ ...FULL, truncated: true });
  renderWith(<Timeline locale="en" onBack={vi.fn()} />);

  expect(await screen.findByText("Showing the newest 7 entries.")).toBeInTheDocument();
});

test("Russian: both series named with «серия»", async () => {
  stubApi(FULL);
  renderWith(<Timeline locale="ru" onBack={vi.fn()} />, "ru");

  const crossing = text((await screen.findAllByRole("listitem"))[3]);
  expect(crossing).toContain("Сету Бандхасана (Первая серия) → Пашасана (Вторая серия)");
  const removal = text(screen.getAllByRole("listitem")[0]);
  expect(removal).toContain("Дроп-бэки: отложено");
});

test("dates are the logged day, whatever the device zone", async () => {
  stubApi(FULL);
  renderWith(<Timeline locale="en" onBack={vi.fn()} />);

  const items = await screen.findAllByRole("listitem");
  expect(text(items[5])).toMatch(/^Jan 1 /);
  expect(text(items[6])).toMatch(/^Dec 31 /);
});

test("My asanas opens the timeline and comes back", async () => {
  const seen = stubApi(FULL);
  renderWith(<Progression locale="en" onBack={vi.fn()} />);

  fireEvent.click(await screen.findByRole("button", { name: "🗓 Timeline" }));
  expect(await screen.findByRole("heading", { name: "🗓 My asanas over time" })).toBeInTheDocument();
  await waitFor(() => {
    expect(seen).toContain("/api/v1/me/progression/timeline");
  });
});

test("a give that ends a series: the Full line above a range that keeps its 🎉", async () => {
  const ending = entry({
    id: 2,
    kind: "given",
    from: P("primary", "bhujapidasana"),
    to: P("primary", "setu-bandhasana"),
    celebrations: [
      {
        kind: "new_asana",
        series: "primary",
        key: "setu-bandhasana",
        first: P("primary", "kurmasana"),
      },
      { kind: "series_complete", series: "primary", key: null, first: null },
    ],
  });
  stubApi({ set: true, truncated: false, entries: [ending, START] });
  renderWith(<Timeline locale="en" onBack={vi.fn()} />);

  const row = text((await screen.findAllByRole("listitem"))[0]);
  expect(row).toContain("🎉 Full Primary: Yoga Chikitsa.");
  expect(row).toContain("🎉 Kurmasana → Setu Bandhasana");
  expect(row).toContain("· Primary");
  expect(row.indexOf("Full Primary")).toBeLessThan(row.indexOf("Kurmasana"));
});
