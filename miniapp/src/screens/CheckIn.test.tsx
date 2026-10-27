import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { Days } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import { DayEditor } from "./stats/DayEditor";
import { TodayCard } from "./TodayCard";

// PR-06 (spec §6): the after-practice check-in block under the practice details, in the
// Today card and the day editor. Open for the server's today/yesterday with the setting on
// (or when a check-in exists), else a collapsed "✨ Check-in" link. Every chip tap PUTs the
// whole check-in optimistically; the tag list always comes from the catalog.

vi.mock("../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
}));

const TODAY = "2026-10-26";
const YESTERDAY = "2026-10-25";
const TWO_DAYS_AGO = "2026-10-24";
// The device's own date is never used: it may differ from the server's today.
const DEVICE_NOW = new Date("2026-10-28T12:00:00Z");

const ME = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Ash",
  locale: "en",
  timezone: "Asia/Almaty",
  name_from_telegram: true,
  locale_from_telegram: true,
  day_off: null,
  hide_ladies: false,
  offer_check_in: true,
};

const ALL_TAGS = [
  { key: "stiff", group: "body" },
  { key: "open", group: "body" },
  { key: "strong", group: "body" },
  { key: "light", group: "body" },
  { key: "heavy", group: "body" },
  { key: "sore", group: "body" },
  { key: "focused", group: "mind" },
  { key: "calm", group: "mind" },
  { key: "scattered", group: "mind" },
  { key: "steady_breath", group: "mind" },
];

type CheckInOut = {
  slot: number;
  mood: number | null;
  energy: number | null;
  effort: number | null;
  tags: string[];
};

const checkIn = (over: Partial<CheckInOut> = {}): CheckInOut => ({
  slot: 1,
  mood: null,
  energy: null,
  effort: null,
  tags: [],
  ...over,
});

/** `checkIns: null` = an older server's payload, without the field. */
function day(date: string, status = "practiced", checkIns: CheckInOut[] | null = []) {
  const base = { date, status, practices: [] };
  return checkIns === null ? base : { ...base, check_ins: checkIns };
}

function days(list: unknown[]): Days {
  return {
    today: TODAY,
    timezone_known: true,
    auto: [],
    moon_location: "mysuru",
    days: list,
    periods: [],
    practice_on: false,
  } as unknown as Days;
}

const json = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

interface Stub {
  days?: Days;
  me?: Record<string, unknown>;
  tags?: { key: string; group: string }[];
  /** How PUT …/check-ins/1 answers: 200 echoes the body, 0 never answers. */
  putStatus?: number;
}

const checkInPath = (date: string) => `/api/v1/me/days/${date}/check-ins/1`;

/** A small stateful server: check-in writes change what GET /me/days returns afterwards. */
function stubApi({
  days: d = days([day(TODAY)]),
  me = ME,
  tags = ALL_TAGS,
  putStatus = 200,
}: Stub = {}) {
  const seen: Request[] = [];
  let served = d;
  const setCheckIn = (date: string, value: CheckInOut | null) => {
    const list = (served.days as unknown as Record<string, unknown>[]).map((x) =>
      x.date === date ? { ...x, check_ins: value ? [value] : [] } : x,
    );
    served = { ...served, days: list } as unknown as Days;
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request);
      const path = new URL(request.url).pathname;
      const method = request.method;
      if (path === "/api/v1/me" && method === "GET") return json(me);
      if (path === "/api/v1/me/moon-days")
        return json({ location: { slug: "mysuru", explicit: false }, today: TODAY, days: [] });
      if (path === "/api/v1/moon/cities") return json([]);
      if (path === "/api/v1/catalog")
        return json({ version: "test", series: [], check_in_tags: tags });
      if (path.endsWith("/practice-presets")) return json({ last: null, presets: [] });
      if (path === "/api/v1/me/notification-settings") return json({});
      if (path.includes("/check-ins/") && method === "PUT") {
        if (putStatus === 0) return new Promise<Response>(() => undefined);
        if (putStatus === 409) return json({ code: "day_not_practiced" }, 409);
        if (putStatus !== 200) return json({ code: "unavailable" }, putStatus);
        const body = (await request.clone().json()) as Omit<CheckInOut, "slot">;
        const saved = { slot: 1, ...body };
        setCheckIn(path.split("/")[5] ?? "", saved);
        return json(saved);
      }
      if (path.includes("/check-ins/") && method === "DELETE") {
        setCheckIn(path.split("/")[5] ?? "", null);
        return json(null, 204);
      }
      if (path.startsWith("/api/v1/me/days") && method === "GET") return json(served);
      return json({});
    }),
  );
  return seen;
}

function renderWith(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale="en">{node}</L10nProvider>
    </QueryClientProvider>,
  );
}

const renderToday = () => renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

const renderEditor = (date: string) =>
  renderWith(
    <DayEditor
      date={date}
      label="A day"
      zone="Asia/Almaty"
      locale="en"
      showLadies
      onClose={() => undefined}
    />,
  );

const mood = (n: number) => screen.findByRole("button", { name: `Mood ${String(n)} of 5` });

async function sent(seen: Request[], method: string, path: string): Promise<Request[]> {
  await vi.waitFor(() => {
    expect(seen.some((r) => r.method === method && new URL(r.url).pathname === path)).toBe(true);
  });
  return seen.filter((r) => r.method === method && new URL(r.url).pathname === path);
}

async function lastBody(seen: Request[], date = TODAY): Promise<unknown> {
  const puts = await sent(seen, "PUT", checkInPath(date));
  return puts[puts.length - 1]?.clone().json();
}

const daysReads = (seen: Request[]) =>
  seen.filter((r) => r.method === "GET" && new URL(r.url).pathname === "/api/v1/me/days").length;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: DEVICE_NOW });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("CheckIn: when it shows", () => {
  it("is open on today's practiced day with the setting on", async () => {
    stubApi();
    renderToday();

    for (const n of [1, 2, 3, 4, 5]) expect(await mood(n)).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("How do you feel?")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "✨ Check-in" })).not.toBeInTheDocument();
  });

  it("is open for the server's yesterday in the day editor", async () => {
    stubApi({ days: days([day(YESTERDAY)]) });
    renderEditor(YESTERDAY);

    expect(await mood(3)).toBeInTheDocument();
  });

  it("is collapsed two days back, and the link opens it", async () => {
    stubApi({ days: days([day(TWO_DAYS_AGO)]) });
    renderEditor(TWO_DAYS_AGO);

    const link = await screen.findByRole("button", { name: "✨ Check-in" });
    expect(screen.queryByRole("button", { name: "Mood 3 of 5" })).not.toBeInTheDocument();
    fireEvent.click(link);

    expect(await mood(3)).toBeInTheDocument();
  });

  it("is collapsed with the setting off", async () => {
    stubApi({ me: { ...ME, offer_check_in: false } });
    renderToday();

    expect(await screen.findByRole("button", { name: "✨ Check-in" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mood 3 of 5" })).not.toBeInTheDocument();
  });

  it("is open when a check-in exists, whatever the day or the setting", async () => {
    stubApi({
      me: { ...ME, offer_check_in: false },
      days: days([day(TWO_DAYS_AGO, "practiced", [checkIn({ mood: 2, energy: 5 })])]),
    });
    renderEditor(TWO_DAYS_AGO);

    expect(await mood(2)).toHaveAttribute("aria-pressed", "true");
  });

  it.each(["rest", "moon", "sick", "skipped"])("is not there on a %s day", async (status) => {
    stubApi({ days: days([day(TODAY, status)]) });
    renderToday();

    await screen.findByRole("button", { pressed: true });
    expect(screen.queryByRole("button", { name: "Mood 3 of 5" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "✨ Check-in" })).not.toBeInTheDocument();
  });

  it("renders a payload from an older server without check_ins", async () => {
    stubApi({ days: days([day(TODAY, "practiced", null)]) });
    renderToday();

    expect(await mood(4)).toHaveAttribute("aria-pressed", "false");
  });
});

describe("CheckIn: saving", () => {
  it("a mood tap PUTs the whole check-in and shows it at once", async () => {
    const seen = stubApi({ putStatus: 0 }); // the server never answers
    renderToday();

    const chip = await mood(4);
    fireEvent.click(chip);

    await vi.waitFor(() => {
      expect(chip).toHaveAttribute("aria-pressed", "true");
    });
    expect(await lastBody(seen)).toEqual({ mood: 4, energy: null, effort: null, tags: [] });
  });

  it("energy and effort keep what is already there", async () => {
    const seen = stubApi({ days: days([day(TODAY, "practiced", [checkIn({ mood: 4 })])]) });
    renderToday();
    await mood(4);

    const energy = within(screen.getByRole("group", { name: /energy/i })).getAllByRole("button");
    expect(energy).toHaveLength(5);
    fireEvent.click(energy[2] as HTMLElement);

    expect(await lastBody(seen)).toEqual({ mood: 4, energy: 3, effort: null, tags: [] });
    const effort = within(screen.getByRole("group", { name: /effort/i })).getAllByRole("button");
    expect(effort).toHaveLength(5);
    fireEvent.click(effort[4] as HTMLElement);

    // Day-scope saves run in tap order: the second PUT goes out once the first settles.
    await vi.waitFor(async () => {
      expect(await lastBody(seen)).toEqual({ mood: 4, energy: 3, effort: 5, tags: [] });
    });
  });

  it("quick taps in a row all land: an earlier answer never undoes a later tap", async () => {
    const seen = stubApi();
    // Hold each PUT's answer until released, to land the first one while a later tap waits.
    const server = globalThis.fetch;
    const gates: (() => void)[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) => {
        if (request.method === "PUT" && request.url.includes("/check-ins/")) {
          await new Promise<void>((resolve) => gates.push(resolve));
        }
        return server(request);
      }),
    );
    const settle = () => new Promise((resolve) => setTimeout(resolve, 20));
    renderToday();

    const four = await mood(4);
    fireEvent.click(four);
    await vi.waitFor(() => {
      expect(gates).toHaveLength(1); // PUT 1 sent, its answer held
    });
    const energy = within(screen.getByRole("group", { name: /energy/i })).getAllByRole("button");
    fireEvent.click(energy[2] as HTMLElement); // queued behind PUT 1
    await settle();
    gates[0]?.(); // PUT 1 answers while the energy tap waits
    await vi.waitFor(() => {
      expect(gates).toHaveLength(2); // PUT 2 sent, its answer held
    });
    await settle();
    expect(energy[2]).toHaveAttribute("aria-pressed", "true"); // not undone by answer 1
    const effort = within(screen.getByRole("group", { name: /effort/i })).getAllByRole("button");
    fireEvent.click(effort[1] as HTMLElement);
    gates[1]?.();
    await vi.waitFor(() => {
      expect(gates).toHaveLength(3);
    });
    gates[2]?.();

    await vi.waitFor(async () => {
      expect(await lastBody(seen)).toEqual({ mood: 4, energy: 3, effort: 2, tags: [] });
    });
  });

  it("tapping a pressed chip clears that value", async () => {
    const seen = stubApi({
      days: days([day(TODAY, "practiced", [checkIn({ mood: 4, energy: 3 })])]),
    });
    renderToday();

    fireEvent.click(await mood(4));

    expect(await lastBody(seen)).toEqual({ mood: null, energy: 3, effort: null, tags: [] });
  });

  it("clearing the last value sends DELETE, not an empty PUT", async () => {
    const seen = stubApi({ days: days([day(TODAY, "practiced", [checkIn({ mood: 4 })])]) });
    renderToday();

    fireEvent.click(await mood(4));

    await sent(seen, "DELETE", checkInPath(TODAY));
    expect(seen.some((r) => r.method === "PUT" && r.url.includes("/check-ins/"))).toBe(false);
  });

  it("rolls back and says so when saving fails", async () => {
    stubApi({ putStatus: 503 });
    renderToday();
    const chip = await mood(2);

    fireEvent.click(chip);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await vi.waitFor(() => {
      expect(chip).toHaveAttribute("aria-pressed", "false");
    });
  });

  it("refetches the days when the day is no longer practiced (409)", async () => {
    const seen = stubApi({ putStatus: 409 });
    renderToday();
    await mood(5);
    const before = daysReads(seen);

    fireEvent.click(await mood(5));

    await vi.waitFor(() => {
      expect(daysReads(seen)).toBeGreaterThan(before);
    });
  });

  it("Remove check-in sends DELETE and is offered only when one exists", async () => {
    stubApi();
    const { unmount } = renderToday();
    await mood(3);
    expect(screen.queryByRole("button", { name: "Remove check-in" })).not.toBeInTheDocument();
    unmount();

    const seen = stubApi({
      days: days([day(TODAY, "practiced", [checkIn({ effort: 2, tags: ["calm"] })])]),
    });
    renderToday();
    fireEvent.click(await screen.findByRole("button", { name: "Remove check-in" }));

    await sent(seen, "DELETE", checkInPath(TODAY));
  });

  it("the day editor saves to its own date", async () => {
    const seen = stubApi({ days: days([day(YESTERDAY)]) });
    renderEditor(YESTERDAY);

    fireEvent.click(await mood(1));

    expect(await lastBody(seen, YESTERDAY)).toEqual({
      mood: 1,
      energy: null,
      effort: null,
      tags: [],
    });
  });
});

describe("CheckIn: tags", () => {
  it("come from the catalog, never a hard-coded list", async () => {
    stubApi({
      tags: [
        { key: "light", group: "body" },
        { key: "calm", group: "mind" },
      ],
    });
    renderToday();
    await mood(3);

    expect(await screen.findByRole("button", { name: "Light" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Calm" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stiff" })).not.toBeInTheDocument();
  });

  it("show every catalog tag with its label, body and mind apart", async () => {
    stubApi();
    renderToday();
    await mood(3);
    await screen.findByRole("button", { name: "Stiff" }); // the catalog has loaded

    const body = within(screen.getByRole("group", { name: /body/i }));
    const mind = within(screen.getByRole("group", { name: /mind/i }));
    expect(body.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Stiff",
      "Open",
      "Strong",
      "Light",
      "Heavy",
      "Sore muscles",
    ]);
    expect(mind.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Focused",
      "Calm",
      "Scattered",
      "Steady breath",
    ]);
  });

  it("toggle with aria-pressed and save the whole check-in", async () => {
    const seen = stubApi({
      days: days([day(TODAY, "practiced", [checkIn({ mood: 3, tags: ["calm"] })])]),
    });
    renderToday();

    expect(await screen.findByRole("button", { name: "Calm" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Light" }));

    const body = (await lastBody(seen)) as CheckInOut;
    expect({ ...body, tags: [...body.tags].sort() }).toEqual({
      mood: 3,
      energy: null,
      effort: null,
      tags: ["calm", "light"],
    });
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Light" })).toHaveAttribute("aria-pressed", "true");
    });
  });
});
