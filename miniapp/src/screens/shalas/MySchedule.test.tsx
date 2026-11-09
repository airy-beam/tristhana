import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { MyRow, MySchedule as Week } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import MySchedule from "./MySchedule";

// SC-03 "My schedule": every shala I'm in, in my zone, with the class's own time when the
// offsets differ; my moon day 🌙 on the day; the row marks; the ⚠ shift line; filters and
// shala chips on the same answer; a row opens its shala. API and Telegram SDK mocked.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  confirmDestructive: vi.fn(),
}));

const ALMATY = "00000000-0000-0000-0000-0000000000c1";
const BERLIN = "00000000-0000-0000-0000-0000000000c2";
const ME = "00000000-0000-0000-0000-000000000001";
const ANNA = { id: "00000000-0000-0000-0000-0000000000a1", name: "Anna" };
const DANA = { id: "00000000-0000-0000-0000-0000000000a2", name: "Dana" };
const BORIS = { id: "00000000-0000-0000-0000-0000000000a3", name: "Boris" };

const row = (over: Partial<MyRow> = {}): MyRow => ({
  class_id: "00000000-0000-0000-0000-0000000000d1",
  key: "2026-11-09",
  on: "2026-11-09",
  start: "06:00",
  end: "09:30",
  starts_at: "2026-11-09T01:00:00Z",
  type: "mysore",
  title: null,
  online: false,
  teacher: ANNA,
  substitute: false,
  cancelled: null,
  moved: false,
  swapped_from: null,
  held: false,
  usual_teacher: ANNA,
  moon: false,
  swapped_to: null,
  shala_id: ALMATY,
  zone: "Asia/Almaty",
  city: "almaty",
  role: null,
  my_teacher: true,
  planned: "06:00",
  attendance: null,
  can_claim: false,
  attendance_counts: null,
  ...over,
});

const days = (from: number, moon: number[] = []) =>
  Array.from({ length: 7 }, (_, i) => {
    const d = `2026-11-${String(from + i).padStart(2, "0")}`;
    return { date: d, my_moon: moon.includes(from + i) };
  });

const WEEK: Week = {
  zone: "Asia/Almaty",
  zone_known: true,
  today: "2026-11-09",
  moon_city: "mysuru",
  days: days(9, [12]),
  shalas: [
    { id: ALMATY, name: "Ashtanga Almaty", city: "almaty", zone: "Asia/Almaty", staff: false },
    { id: BERLIN, name: "Yoga Berlin", city: "berlin", zone: "Europe/Berlin", staff: true },
  ],
  has_teachers: true,
  is_staff: true,
  shifts: [],
  occurrences: [
    row(),
    row({
      class_id: "00000000-0000-0000-0000-0000000000d9",
      shala_id: BERLIN,
      zone: "Europe/Berlin",
      city: "berlin",
      type: "led",
      title: "Primary",
      start: "17:30",
      end: "19:00",
      starts_at: "2026-11-09T16:30:00Z",
      teacher: BORIS,
      usual_teacher: BORIS,
      my_teacher: false,
    }),
    row({
      key: "2026-11-10",
      on: "2026-11-10",
      starts_at: "2026-11-10T01:00:00Z",
      teacher: DANA,
      substitute: true,
    }),
    row({
      key: "2026-11-13",
      on: "2026-11-13",
      starts_at: "2026-11-13T01:00:00Z",
      cancelled: "moon",
      moon: true,
      swapped_to: "2026-11-14",
    }),
    row({
      key: "2026-11-13",
      on: "2026-11-14",
      starts_at: "2026-11-14T01:00:00Z",
      swapped_from: "2026-11-13",
    }),
    row({
      class_id: "00000000-0000-0000-0000-0000000000d3",
      key: "2026-11-11",
      on: "2026-11-11",
      starts_at: "2026-11-11T04:00:00Z",
      start: "09:00",
      end: "10:00",
      type: "pranayama",
      moon: true,
      teacher: { id: ME, name: "Ash" },
      usual_teacher: { id: ME, name: "Ash" },
      role: "teaching",
      my_teacher: false,
    }),
    row({
      class_id: "00000000-0000-0000-0000-0000000000d4",
      key: "2026-11-12",
      on: "2026-11-12",
      starts_at: "2026-11-12T01:00:00Z",
      cancelled: "closure",
    }),
  ],
};

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

let requests: string[] = [];

function stubApi(week: Week) {
  requests = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      await Promise.resolve();
      const url = new URL(request.url);
      if (url.pathname === "/api/v1/me/schedule") {
        requests.push(url.search);
        return json(week);
      }
      if (url.pathname === "/api/v1/me")
        return json({
          id: ME,
          display_name: "Ash",
          locale: "en",
          timezone: "Asia/Almaty",
          home_city: null,
        });
      return json({});
    }),
  );
}

function renderWith(locale: Locale = "en") {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <L10nProvider locale={locale}>
        <MySchedule locale={locale} onBack={vi.fn()} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
const mains = () =>
  [...document.querySelectorAll(".my-schedule-row .link-person")].map((p) => plain(p.textContent));
const seconds = () =>
  [...document.querySelectorAll(".my-schedule-row .hint")].map((p) => plain(p.textContent));
const headings = () =>
  screen.getAllByRole("heading", { level: 3 }).map((h) => plain(h.textContent));

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("my schedule", () => {
  it("shows every shala in my zone, with the class's own time and the row marks", async () => {
    stubApi(WEEK);
    renderWith();

    expect(await screen.findByRole("heading", { name: "🗓 My schedule" })).toBeInTheDocument();
    expect(await screen.findByText("Times: Almaty (UTC+5)")).toBeInTheDocument();
    expect(mains()).toEqual([
      "06:00–09:30 Mysore · Anna 👤",
      "21:30–23:00 Led Primary · Boris",
      "06:00–09:30 Mysore · Dana (for Anna) 👤",
      "09:00–10:00 Pranayama · 🌙",
      "❌ 06:00–09:30 Mysore · Anna 👤 (shala closed)",
      `🌙 06:00–09:30 Mysore · Anna 👤 (moon day) · 🔁 Sat, Nov 14`,
      "06:00–09:30 Mysore · Anna 👤 · 🔁 instead of Fri, Nov 13",
    ]);
    expect(seconds()[1]).toBe("Yoga Berlin · 17:30 Berlin (UTC+1)");
    expect(seconds()[0]).toBe("Ashtanga Almaty");
  });

  it("marks my own moon day on the day row", async () => {
    stubApi(WEEK);
    renderWith();

    await screen.findByText("Times: Almaty (UTC+5)");
    expect(headings()).toContain("Thu, Nov 12 🌙");
    expect(screen.getByRole("heading", { name: /your moon day/ })).toBeInTheDocument();
  });

  it("filters on the same answer, and remembers the choice", async () => {
    stubApi(WEEK);
    renderWith();
    await screen.findByText("Times: Almaty (UTC+5)");

    fireEvent.click(screen.getByRole("button", { name: "🧑‍🏫 I teach" }));
    expect(mains()).toEqual(["09:00–10:00 Pranayama · 🌙"]);
    fireEvent.click(screen.getByRole("button", { name: "👤 My teachers" }));
    expect(mains()).not.toContain("21:30–23:00 Led Primary · Boris");
    fireEvent.click(screen.getByRole("button", { name: "Yoga Berlin" }));
    expect(screen.getByText("No classes with your teachers this week.")).toBeInTheDocument();
    expect(requests).toHaveLength(1);
    expect(localStorage.getItem("tristhana.my-schedule.filter")).toContain("teachers");
  });

  it("hides the filters that don't apply", async () => {
    stubApi({ ...WEEK, has_teachers: false, is_staff: false, shalas: WEEK.shalas.slice(0, 1) });
    renderWith();
    await screen.findByText("Times: Almaty (UTC+5)");

    expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "👤 My teachers" })).toBeNull();
    expect(screen.queryByRole("button", { name: "🧑‍🏫 I teach" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Ashtanga Almaty" })).toBeNull();
  });

  it("shows the ⚠ shift line and marks its day", async () => {
    stubApi({
      ...WEEK,
      shifts: [
        {
          zone: "Europe/Berlin",
          city: "berlin",
          shala_ids: [BERLIN],
          on: "2026-11-15",
          minutes: -60,
        },
      ],
      occurrences: [
        ...WEEK.occurrences,
        row({
          shala_id: BERLIN,
          zone: "Europe/Berlin",
          city: "berlin",
          on: "2026-11-15",
          key: "2026-11-15",
          starts_at: "2026-11-15T16:30:00Z",
        }),
      ],
    });
    renderWith();

    expect(
      await screen.findByText("⚠ From Sunday, 15 November, Yoga Berlin is 1 h later for you"),
    ).toBeInTheDocument();
    expect(headings().find((h) => h.startsWith("Sun"))).toContain("⚠");
  });

  it("names the fallback zone when mine is unknown", async () => {
    stubApi({ ...WEEK, zone_known: false });
    renderWith();

    expect(
      await screen.findByText("Times are in Almaty (UTC+5). Set your city to see your own time."),
    ).toBeInTheDocument();
  });

  it("pages a week ahead from my today", async () => {
    stubApi(WEEK);
    renderWith();
    await screen.findByText("Times: Almaty (UTC+5)");

    fireEvent.click(screen.getByRole("button", { name: "▶" }));

    await waitFor(() => {
      expect(requests).toContain("?from=2026-11-16&days=7");
    });
  });

  it("says a moved class was moved, and keeps my moon day under an empty filter", async () => {
    stubApi({
      ...WEEK,
      has_teachers: false,
      occurrences: [
        row({
          key: "2026-11-10",
          on: "2026-11-11",
          starts_at: "2026-11-11T02:30:00Z",
          start: "07:30",
          end: "11:00",
          moved: true,
          role: "teaching",
          my_teacher: false,
        }),
      ],
    });
    renderWith();
    await screen.findByText("Times: Almaty (UTC+5)");

    expect(mains()).toEqual(["07:30–11:00 Mysore · ↪ moved from Tue, Nov 10 06:00"]);
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(headings()).toContain("Thu, Nov 12 🌙");
  });

  it("speaks Russian", async () => {
    stubApi(WEEK);
    renderWith("ru");

    await screen.findByText("Время: Almaty (UTC+5)");
    expect(mains()).toContain("06:00–09:30 Майсор · Dana (за Anna) 👤");
    expect(screen.getByRole("button", { name: "🧑‍🏫 Веду" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "👤 Мои учителя" })).toBeInTheDocument();
  });
});
