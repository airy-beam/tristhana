import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import { L10nProvider } from "../i18n/L10nProvider";
import type { Locale } from "../i18n/negotiate";
import { haptics } from "../telegram";
import { ClassRow } from "./TodayRows";

// UI-06 stage 2 (spec §4, §9): today's class as one quiet row on Today, for people in a shala.
// Times are in my zone with the place and no offset (ADR-0044); a class on another clock adds
// its own time, with the offset. No class today: no row. No shala: no schedule request.

vi.mock("../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
}));

const TODAY = "2026-11-07"; // winter: Berlin is UTC+1, Almaty UTC+5
const ALMATY = { id: "00000000-0000-0000-0000-0000000000c1", name: "Ashtanga Almaty" };
const BERLIN = { id: "00000000-0000-0000-0000-0000000000c2", name: "Yoga Berlin" };

let n = 0;
/** A class of today; `at` is the instant it starts. */
const row = (at: string, over: Record<string, unknown> = {}) => ({
  shala_id: ALMATY.id,
  class_id: `00000000-0000-0000-0000-00000000d${String(n++).padStart(3, "0")}`,
  key: TODAY,
  on: TODAY,
  type: "mysore",
  title: null,
  start: "07:00",
  end: "09:00",
  starts_at: at,
  zone: "Asia/Almaty",
  city: "almaty",
  cancelled: null,
  online: false,
  ...over,
});

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

interface Stub {
  shalas?: { id: string; name: string }[];
  occurrences?: unknown[];
  zoneKnown?: boolean;
}

function stubApi({ shalas = [ALMATY], occurrences = [], zoneKnown = true }: Stub = {}): string[] {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      const path = new URL(request.url).pathname;
      asked.push(path);
      if (path === "/api/v1/me/shalas") return Promise.resolve(json(shalas));
      if (path === "/api/v1/me/schedule")
        return Promise.resolve(
          json({
            zone: "Asia/Almaty",
            zone_known: zoneKnown,
            today: TODAY,
            moon_city: "almaty",
            days: [],
            shalas,
            has_teachers: false,
            is_staff: false,
            shifts: [],
            occurrences,
          }),
        );
      return Promise.resolve(json({ timezone: "Asia/Almaty", home_city: null }));
    }),
  );
  return asked;
}

function renderRow(onOpen: () => void = () => undefined, locale: Locale = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <ClassRow locale={locale} onOpen={onOpen} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const text = (el: HTMLElement) => el.textContent.replace(/[⁨⁩]/g, "");
const settled = () => new Promise((resolve) => setTimeout(resolve, 30));

beforeEach(() => {
  // 05:00 in Almaty on the day: every class of the day is still ahead.
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-07T00:00:00Z") });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("ClassRow", () => {
  it("my own zone: the place, no offset; a tap opens My schedule", async () => {
    stubApi({ occurrences: [row("2026-11-07T02:00:00Z")] });
    const onOpen = vi.fn();
    renderRow(onOpen);

    const button = await screen.findByRole("button");
    expect(text(button)).toBe("🗓 07:00 Almaty · Mysore · Ashtanga Almaty");
    fireEvent.click(button);

    expect(haptics.selection).toHaveBeenCalled();
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it("a class on another clock adds its own time, with the offset", async () => {
    stubApi({
      shalas: [BERLIN],
      occurrences: [
        row("2026-11-07T16:30:00Z", {
          shala_id: BERLIN.id,
          type: "led",
          start: "17:30",
          zone: "Europe/Berlin",
          online: true,
        }),
      ],
    });
    renderRow();

    expect(text(await screen.findByRole("button"))).toBe(
      "🗓 21:30 Almaty · Led · Yoga Berlin · 17:30 Berlin (UTC+1)",
    );
  });

  it("an unknown zone of mine is nobody's own yet: the offset shows", async () => {
    stubApi({ occurrences: [row("2026-11-07T02:00:00Z")], zoneKnown: false });
    renderRow();

    expect(text(await screen.findByRole("button"))).toBe(
      "🗓 07:00 Almaty (UTC+5) · Mysore · Ashtanga Almaty",
    );
  });

  it("names a class by its title too, and other types by their own word", async () => {
    stubApi({
      occurrences: [row("2026-11-07T11:00:00Z", { type: "conference", title: "Sutras" })],
    });
    renderRow();

    expect(text(await screen.findByRole("button"))).toBe(
      "🗓 16:00 Almaty · Conference Sutras · Ashtanga Almaty",
    );
  });

  it("shows the next class still ahead and counts the others", async () => {
    vi.setSystemTime(new Date("2026-11-07T05:00:00Z")); // 10:00 in Almaty: Mysore has begun
    stubApi({
      occurrences: [
        row("2026-11-07T02:00:00Z"),
        row("2026-11-07T13:00:00Z", { type: "led", start: "18:00" }),
      ],
    });
    renderRow();

    expect(text(await screen.findByRole("button"))).toBe(
      "🗓 18:00 Almaty · Led · Ashtanga Almaty · +1 more",
    );
  });

  it("falls back to the day's first class once all have begun", async () => {
    vi.setSystemTime(new Date("2026-11-07T15:00:00Z"));
    stubApi({ occurrences: [row("2026-11-07T02:00:00Z")] });
    renderRow();

    expect(text(await screen.findByRole("button"))).toBe(
      "🗓 07:00 Almaty · Mysore · Ashtanga Almaty",
    );
  });

  it("no class today: no row (another day's and a cancelled one don't count)", async () => {
    const asked = stubApi({
      occurrences: [
        row("2026-11-08T02:00:00Z", { key: "2026-11-08", on: "2026-11-08" }),
        row("2026-11-07T02:00:00Z", { cancelled: "moon" }),
      ],
    });
    const { container } = renderRow();

    await vi.waitFor(() => {
      expect(asked).toContain("/api/v1/me/schedule");
    });
    await settled();
    expect(container).toBeEmptyDOMElement();
  });

  it("in no shala: no row and no schedule request", async () => {
    const asked = stubApi({ shalas: [] });
    const { container } = renderRow();

    await vi.waitFor(() => {
      expect(asked).toContain("/api/v1/me/shalas");
    });
    await settled();
    expect(container).toBeEmptyDOMElement();
    expect(asked).not.toContain("/api/v1/me/schedule");
  });

  it("is in Russian too", async () => {
    stubApi({
      occurrences: [row("2026-11-07T02:00:00Z"), row("2026-11-07T13:00:00Z", { type: "led" })],
    });
    renderRow(undefined, "ru");

    expect(text(await screen.findByRole("button"))).toBe(
      "🗓 07:00 Almaty · Майсор · Ashtanga Almaty · ещё 1",
    );
  });
});
