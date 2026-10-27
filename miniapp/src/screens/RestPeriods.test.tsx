import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import type { Days, NotificationSettings } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import { PracticeReminderCard } from "./PracticeReminderCard";
import { DayEditor } from "./stats/DayEditor";
import { TodayCard } from "./TodayCard";

// WH-01 part 2 (ADR-0023): the "for how many days?" offer after a 🌸/🤒/✈️ save, "keep the
// pause" after a 🧘 save inside one, the covered-day line with End, hiding the 🌸 chip, and
// the paused line on the reminder card. The chips always come from the server.

vi.mock("../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
}));

const TODAY = "2026-10-26";
const YESTERDAY = "2026-10-25";
const LATER = "2026-10-28";

const ME = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Ash",
  locale: "en",
  timezone: "Asia/Almaty",
  name_from_telegram: true,
  locale_from_telegram: true,
  day_off: null,
  hide_ladies: false,
};

type Period = { start: string; end: string; kind: "ladies" | "sick" | "travel" };

function days(over: Record<string, unknown> = {}): Days {
  return {
    today: TODAY,
    notes: [], // PR-07
    timezone_known: true,
    auto: [],
    moon_location: "mysuru",
    days: [],
    periods: [],
    practice_on: false,
    ...over,
  };
}

const json = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

interface Stub {
  days?: Days;
  me?: Record<string, unknown>;
  /** The PUT /me/days answer (DaySaved). */
  saved?: Record<string, unknown>;
  settings?: NotificationSettings;
  /** POST /me/rest-periods answers 503 (second review: the question comes back). */
  startFails?: boolean;
  /** POST …/end answers after this many ms (to see the optimistic state). */
  endDelay?: number;
}

/** A small stateful server: writes change what GET /me/days returns afterwards. */
function stubApi({
  days: d = days(),
  me = ME,
  saved,
  settings,
  startFails = false,
  endDelay = 0,
}: Stub = {}): Request[] {
  const seen: Request[] = [];
  let served = d;
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
      // The practice details under a 🧘 save (PR-02): nothing to pick from here.
      if (path === "/api/v1/catalog") return json({ version: "test", series: [] });
      if (path.endsWith("/practice-presets")) return json({ last: null, presets: [] });
      if (path === "/api/v1/me/notification-settings") return json(settings ?? {});
      if (path.startsWith("/api/v1/me/days") && method === "GET") return json(served);
      if (path.startsWith("/api/v1/me/days/") && method === "PUT") {
        const { status } = (await request.clone().json()) as { status: string };
        const date = path.split("/").at(-1) ?? "";
        const others = served.days.filter((x) => x.date !== date);
        served = { ...served, days: [...others, { date, status, practices: [] }] } as Days;
        return json(
          saved ?? {
            date: TODAY,
            status,
            practices: [],
            pause_offer: null,
            period: null,
            cut: null,
          },
        );
      }
      if (path === "/api/v1/me/rest-periods" && method === "POST" && startFails)
        return new Response(JSON.stringify({ code: "unavailable" }), { status: 503 });
      if (path === "/api/v1/me/rest-periods" && method === "POST") {
        const body = (await request.clone().json()) as { start: string; kind: string };
        return json({ start: body.start, end: LATER, kind: body.kind });
      }
      if (path.startsWith("/api/v1/me/rest-periods/") && path.endsWith("/end")) {
        if (endDelay) await new Promise((resolve) => setTimeout(resolve, endDelay));
        return json({ period: null });
      }
      if (path.startsWith("/api/v1/me/rest-periods/") && method === "PUT") {
        const body = (await request.clone().json()) as { end: string; kind: string };
        const start = path.split("/").at(-1) ?? "";
        return json({ period: { start, end: body.end, kind: body.kind } });
      }
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

const plain = (text: string) => text.replace(/[⁨⁩]/g, "");
const button = (name: string) => screen.findByRole("button", { name: (n) => plain(n) === name });

async function sent(seen: Request[], method: string, path: string): Promise<unknown> {
  await vi.waitFor(() => {
    expect(seen.some((r) => r.method === method && new URL(r.url).pathname === path)).toBe(true);
  });
  const request = seen.find((r) => r.method === method && new URL(r.url).pathname === path);
  return request?.clone().json();
}

const posted = (seen: Request[], path: string) =>
  seen.some((r) => r.method === "POST" && new URL(r.url).pathname === path);

const OFFER = {
  date: TODAY,
  status: "ladies",
  practices: [],
  pause_offer: {
    start: TODAY,
    kind: "ladies",
    reminders_on: false,
    choices: [2, 3, 5],
    more: [4, 6, 7],
  },
  period: null,
  cut: null,
};

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("TodayCard: the pause offer", () => {
  it("asks after a 🌸 save with the server's chips and posts the chosen number", async () => {
    const seen = stubApi({ saved: OFFER });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

    fireEvent.click(await button("🌸 Ladies' holiday"));

    expect(
      await screen.findByText(
        (t) => plain(t) === "How many days should show as 🌸 Ladies' holiday, including today?",
      ),
    ).toBeInTheDocument();
    for (const n of ["2 days", "3 days", "5 days", "Other…"]) await button(n);
    expect(screen.queryByRole("button", { name: "4 days" })).not.toBeInTheDocument();

    fireEvent.click(await button("5 days"));

    expect(await sent(seen, "POST", "/api/v1/me/rest-periods")).toEqual({
      start: TODAY,
      days: 5,
      kind: "ladies",
    });
  });

  it("reveals the other choices on Other…", async () => {
    stubApi({ saved: OFFER });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);
    fireEvent.click(await button("🌸 Ladies' holiday"));

    fireEvent.click(await button("Other…"));

    for (const n of ["4 days", "6 days", "7 days"]) await button(n);
  });

  it("uses whatever choices the server sends (never a hard-coded list)", async () => {
    stubApi({
      saved: {
        ...OFFER,
        status: "sick",
        pause_offer: { ...OFFER.pause_offer, kind: "sick", choices: [3, 4, 5], more: [2, 14] },
      },
    });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

    fireEvent.click(await button("🤒 Sick / injury"));

    await button("4 days");
    expect(screen.queryByRole("button", { name: "2 days" })).not.toBeInTheDocument();
  });

  it("names the reminders when they are on", async () => {
    stubApi({ saved: { ...OFFER, pause_offer: { ...OFFER.pause_offer, reminders_on: true } } });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

    fireEvent.click(await button("🌸 Ladies' holiday"));

    expect(await screen.findByText(/Pause practice reminders for how many days/)).toBeVisible();
  });

  it("offers Just today, which closes the question without a pause", async () => {
    const seen = stubApi({ saved: OFFER });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);
    fireEvent.click(await button("🌸 Ladies' holiday"));

    fireEvent.click(await button("Just today"));

    await vi.waitFor(() => {
      expect(screen.queryByText(/How many days/)).not.toBeInTheDocument();
    });
    expect(posted(seen, "/api/v1/me/rest-periods")).toBe(false);
    expect(seen.some((r) => new URL(r.url).pathname.endsWith("/end"))).toBe(false);
  });

  it("Just today on a re-asked first day ends that pause", async () => {
    const period = { start: TODAY, end: LATER, kind: "ladies" };
    const seen = stubApi({ saved: { ...OFFER, period } });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);
    fireEvent.click(await button("🌸 Ladies' holiday"));

    fireEvent.click(await button("Just today"));

    await vi.waitFor(() => {
      expect(posted(seen, `/api/v1/me/rest-periods/${TODAY}/end`)).toBe(true);
    });
  });

  it("asks nothing when the server sends no offer", async () => {
    stubApi();
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

    fireEvent.click(await button("😌 Rest day"));

    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: /Rest day/ })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    });
    expect(screen.queryByText(/How many days/)).not.toBeInTheDocument();
  });
});

describe("TodayCard: keep the pause", () => {
  it("offers Keep after a 🧘 save that cut a pause, and PUTs the period back", async () => {
    const cut: Period = { start: YESTERDAY, end: LATER, kind: "sick" };
    const seen = stubApi({
      days: days({ periods: [cut] }),
      saved: {
        date: TODAY,
        status: "practiced",
        practices: [],
        pause_offer: null,
        period: null,
        cut,
      },
    });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

    fireEvent.click(await button("🧘 Practiced"));
    expect(await screen.findByText(/no longer show as/)).toBeInTheDocument();
    fireEvent.click(await button("⏸ Keep the pause"));

    expect(await sent(seen, "PUT", `/api/v1/me/rest-periods/${YESTERDAY}`)).toEqual({
      end: LATER,
      kind: "sick",
    });
  });

  it("offers nothing when the cut pause had no days left", async () => {
    const cut: Period = { start: "2026-10-23", end: TODAY, kind: "sick" };
    stubApi({
      saved: {
        date: TODAY,
        status: "practiced",
        practices: [],
        pause_offer: null,
        period: null,
        cut,
      },
    });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

    fireEvent.click(await button("🧘 Practiced"));

    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: /Practiced/ })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    });
    expect(screen.queryByRole("button", { name: /Keep the pause/ })).not.toBeInTheDocument();
  });
});

describe("TodayCard: a covered day", () => {
  const covered = (practiceOn: boolean) =>
    days({
      days: [{ date: YESTERDAY, status: "sick", practices: [] }],
      periods: [{ start: YESTERDAY, end: LATER, kind: "sick" }],
      practice_on: practiceOn,
    });

  it("shows the period line, no pressed chip, and End early", async () => {
    const seen = stubApi({ days: covered(false) });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

    expect(
      await screen.findByText((t) =>
        /^🤒 Sick \/ injury through .+\. If the day went differently, log it below\.$/.test(
          plain(t),
        ),
      ),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole("button", { pressed: true })).toHaveLength(0);

    fireEvent.click(await button("⏹ End early"));

    await vi.waitFor(() => {
      expect(posted(seen, `/api/v1/me/rest-periods/${YESTERDAY}/end`)).toBe(true);
    });
  });

  it("labels it End the pause while practice reminders are on", async () => {
    stubApi({ days: covered(true) });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

    expect(await button("⏹ End the pause")).toBeInTheDocument();
  });

  it("still renders an old payload without periods", async () => {
    stubApi({
      days: {
        today: TODAY,
        timezone_known: true,
        auto: [],
        moon_location: "mysuru",
        days: [],
      } as unknown as Days,
    });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

    expect(await button("😌 Rest day")).toBeInTheDocument();
    expect(screen.queryByText(/through/)).not.toBeInTheDocument();
  });
});

describe("Hide the 🌸 chip", () => {
  it("leaves 🌸 out of today's chips", async () => {
    stubApi({ me: { ...ME, hide_ladies: true } });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

    await button("🤒 Sick / injury");
    await vi.waitFor(() => {
      expect(screen.queryByRole("button", { name: /Ladies' holiday/ })).not.toBeInTheDocument();
    });
    expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(6);
  });

  it("keeps it on a day that shows as 🌸", async () => {
    stubApi({
      me: { ...ME, hide_ladies: true },
      days: days({ days: [{ date: TODAY, status: "ladies", practices: [] }] }),
    });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);

    const pressed = await screen.findByRole("button", { pressed: true });
    expect(plain(pressed.textContent)).toBe("🌸 Ladies' holiday");
  });

  it("leaves 🌸 out of the day editor too", async () => {
    stubApi({ me: { ...ME, hide_ladies: true }, days: days({ today: TODAY }) });
    renderWith(
      <DayEditor
        date={YESTERDAY}
        label="Sun, Oct 25"
        zone="Asia/Almaty"
        locale="en"
        showLadies
        onClose={() => undefined}
      />,
    );

    await button("🤒 Sick / injury");
    await vi.waitFor(() => {
      expect(screen.queryByRole("button", { name: /Ladies' holiday/ })).not.toBeInTheDocument();
    });
  });
});

describe("DayEditor: rest periods", () => {
  it("shows the period line for a covered day from /me/days.periods", async () => {
    stubApi({ days: days({ periods: [{ start: "2026-10-24", end: LATER, kind: "travel" }] }) });
    renderWith(
      <DayEditor
        date={YESTERDAY}
        label="Sun, Oct 25"
        zone="Asia/Almaty"
        locale="en"
        showLadies={false}
        onClose={() => undefined}
      />,
    );

    expect(await screen.findByText((t) => /^✈️ Travel through/.test(plain(t)))).toBeInTheDocument();
    expect(screen.queryAllByRole("button", { pressed: true })).toHaveLength(0);
  });

  it("asks the pause question after a yesterday 🤒 save", async () => {
    stubApi({
      saved: {
        ...OFFER,
        date: YESTERDAY,
        status: "sick",
        pause_offer: {
          start: YESTERDAY,
          kind: "sick",
          reminders_on: false,
          choices: [3, 4, 5],
          more: [2, 6, 7, 10, 14],
        },
      },
    });
    renderWith(
      <DayEditor
        date={YESTERDAY}
        label="Sun, Oct 25"
        zone="Asia/Almaty"
        locale="en"
        showLadies={false}
        onClose={() => undefined}
      />,
    );

    fireEvent.click(await button("🤒 Sick / injury"));

    expect(await screen.findByText(/including yesterday/)).toBeInTheDocument();
    await button("3 days");
  });
});

describe("PracticeReminderCard during a pause", () => {
  const SETTINGS = {
    moon: { offsets: [1, 7], at: "19:00:00" },
    quiet: { start: "22:00:00", end: "07:00:00" },
    daily_cap: 3,
    practice: {
      on: true,
      at: "10:00:00",
      days: [1, 2, 3, 4, 5, 7],
      paused_start: YESTERDAY,
      paused_until: LATER,
    },
    timezone: "Asia/Almaty",
  } as unknown as NotificationSettings;

  it("says until when it is paused and resumes on request", async () => {
    const seen = stubApi({ settings: SETTINGS });
    renderWith(<PracticeReminderCard zone="Asia/Almaty" />);

    expect(await screen.findByText(/^⏸ Paused through/)).toBeInTheDocument();
    fireEvent.click(await button("▶️ Resume now"));

    await vi.waitFor(() => {
      expect(posted(seen, `/api/v1/me/rest-periods/${YESTERDAY}/end`)).toBe(true);
    });
  });

  it("shows no pause line without one", async () => {
    stubApi({
      settings: {
        ...SETTINGS,
        practice: { on: true, at: "10:00:00", days: [1, 2, 3, 4, 5, 7] },
      },
    });
    renderWith(<PracticeReminderCard zone="Asia/Almaty" />);

    await button("10:00");
    expect(screen.queryByText(/Paused through/)).not.toBeInTheDocument();
  });
});

describe("Review fixes", () => {
  const cutSaved = (cut: Period | { start: string; end: string; kind: "rest" }) => ({
    date: YESTERDAY,
    status: "practiced",
    practices: [],
    pause_offer: null,
    period: null,
    cut,
  });

  it("names a cut 🌸 pause as rest while 🌸 days are hidden on this device", async () => {
    stubApi({ saved: cutSaved({ start: "2026-10-24", end: LATER, kind: "ladies" }) });
    renderWith(
      <DayEditor
        date={YESTERDAY}
        label="Sun, Oct 25"
        zone="Asia/Almaty"
        locale="en"
        showLadies={false}
        onClose={() => undefined}
      />,
    );

    fireEvent.click(await button("🧘 Practiced"));

    const line = await screen.findByText(/no longer show as/);
    expect(plain(line.textContent)).toContain("😌 Rest day");
    expect(line.textContent).not.toContain("🌸");
  });

  it("offers no Keep for a pause whose kind can't be read", async () => {
    stubApi({ saved: cutSaved({ start: "2026-10-24", end: LATER, kind: "rest" }) });
    renderWith(
      <DayEditor
        date={YESTERDAY}
        label="Sun, Oct 25"
        zone="Asia/Almaty"
        locale="en"
        showLadies
        onClose={() => undefined}
      />,
    );

    fireEvent.click(await button("🧘 Practiced"));

    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: /Practiced/ })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    });
    expect(screen.queryByRole("button", { name: /Keep the pause/ })).not.toBeInTheDocument();
  });

  it("refreshes the reminder card after a day save (a 🧘 may have cut the pause)", async () => {
    const seen = stubApi({
      settings: {
        moon: { offsets: [1, 7], at: "19:00:00" },
        quiet: { start: "22:00:00", end: "07:00:00" },
        daily_cap: 3,
        practice: { on: true, at: "10:00:00", days: [1, 2, 3, 4, 5, 7] },
        timezone: "Asia/Almaty",
      } as unknown as NotificationSettings,
    });
    renderWith(
      <>
        <TodayCard zone="Asia/Almaty" locale="en" />
        <PracticeReminderCard zone="Asia/Almaty" />
      </>,
    );
    await button("10:00");
    const reads = () =>
      seen.filter(
        (r) => r.method === "GET" && new URL(r.url).pathname === "/api/v1/me/notification-settings",
      ).length;
    const before = reads();

    fireEvent.click(await button("🧘 Practiced"));

    await vi.waitFor(() => {
      expect(reads()).toBeGreaterThan(before);
    });
  });

  it("keeps the paused line after a reminder change (the server sends it back)", async () => {
    const settings = {
      moon: { offsets: [1, 7], at: "19:00:00" },
      quiet: { start: "22:00:00", end: "07:00:00" },
      daily_cap: 3,
      practice: {
        on: true,
        at: "10:00:00",
        days: [1, 2, 3, 4, 5, 7],
        paused_start: YESTERDAY,
        paused_until: LATER,
      },
      timezone: "Asia/Almaty",
    } as unknown as NotificationSettings;
    const seen = stubApi({ settings });
    renderWith(<PracticeReminderCard zone="Asia/Almaty" />);

    fireEvent.click(await button("12:00"));

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PATCH")).toBe(true);
    });
    expect(await screen.findByText(/^⏸ Paused through/)).toBeInTheDocument();
  });
});

describe("Second review", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the question again when starting the pause fails", async () => {
    stubApi({ saved: OFFER, startFails: true });
    renderWith(<TodayCard zone="Asia/Almaty" locale="en" />);
    fireEvent.click(await button("🌸 Ladies' holiday"));

    fireEvent.click(await button("5 days"));

    expect(await button("5 days")).toBeInTheDocument(); // back, to try again
    expect(
      screen.getByText(
        (t) => plain(t) === "How many days should show as 🌸 Ladies' holiday, including today?",
      ),
    ).toBeInTheDocument();
  });

  it("resumes with the server's today, not the device's UTC date", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-30T12:00:00Z")); // the device thinks it's Oct 30
    stubApi({
      days: days({ periods: [{ start: YESTERDAY, end: LATER, kind: "sick" }] }),
      settings: {
        moon: { offsets: [1, 7], at: "19:00:00" },
        quiet: { start: "22:00:00", end: "07:00:00" },
        daily_cap: 3,
        practice: {
          on: true,
          at: "10:00:00",
          days: [1, 2, 3, 4, 5, 7],
          paused_start: YESTERDAY,
          paused_until: LATER,
        },
        timezone: "Asia/Almaty",
      } as unknown as NotificationSettings,
      endDelay: 500,
    });
    renderWith(
      <>
        <TodayCard zone="Asia/Almaty" locale="en" />
        <PracticeReminderCard zone="Asia/Almaty" />
      </>,
    );
    const line = (t: string) => /^🤒 Sick \/ injury through/.test(plain(t));
    expect(await screen.findByText(line)).toBeInTheDocument();

    fireEvent.click(await button("▶️ Resume now"));

    // Server today = Oct 26: the pause (from Oct 25) ends Oct 25 and no longer covers today.
    await vi.waitFor(() => {
      expect(screen.queryByText(line)).not.toBeInTheDocument();
    });
  });
});
