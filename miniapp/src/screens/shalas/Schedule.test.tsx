import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import { confirmDestructive, useBackButton } from "../../telegram";
import ClassForm from "./ClassForm";
import ShalaScreen from "./ShalaScreen";

// SC-02 (spec §2, §4, §7): the schedule section of the shala card (zone label once, 🌙 and 😌
// day rows, a cancelled row with its reason, "your time" only when the viewer's offset
// differs), the moon policy select with its note (owner/manager), the Q109 day-off adoption,
// the occurrence sheet per role, and the class form (Mysore window preset "all but the day
// off", other types start empty, the Led hint). The API and the Telegram SDK are mocked.
// UI-06 stage 4 (ADR-0048): the form is short (type, start, weekday chips; the rest under
// "More options"), opens as a layer of its own, and also changes a saved class: from a date
// when the class has run, whole when it has not. The sheet has two headed groups; Delete is in
// the edit form; "Tell students…" follows a cancel (Q339).
// Review fixes: the edit form trusts only a class list fetched after it opened; the stub's
// class list follows a delete; Back asks before it drops what was typed; a date of a class
// that has since changed (404) shows the "class changed" line; "End this class from this date".

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  confirmDestructive: vi.fn(() => Promise.resolve(true)),
  confirmAction: vi.fn(() => Promise.resolve(true)),
  openTelegramLink: vi.fn(),
  useMainButton: vi.fn(),
  mainButtonAvailable: vi.fn(() => false),
  enableClosingConfirmation: vi.fn(),
  disableClosingConfirmation: vi.fn(),
}));

const SHALA = "00000000-0000-0000-0000-0000000000c1";
const CLASS = "00000000-0000-0000-0000-0000000000d1";
const ANNA = "00000000-0000-0000-0000-0000000000a1";
const DANA = "00000000-0000-0000-0000-0000000000a2";
const CITIES = [
  { slug: "mysuru", name_en: "Mysuru", name_ru: "Майсур", timezone: "Asia/Kolkata" },
  { slug: "almaty", name_en: "Almaty", name_ru: "Алматы", timezone: "Asia/Almaty" },
  { slug: "berlin", name_en: "Berlin", name_ru: "Берлин", timezone: "Europe/Berlin" },
];

type Role = "admin" | "teacher" | "assistant" | "office";
interface MeIn {
  owner: boolean;
  roles: Role[];
  student: boolean;
  schedule: boolean;
  announce?: boolean;
}
const OWNER: MeIn = { owner: true, roles: ["teacher"], student: false, schedule: true };
const TEACHER: MeIn = { owner: false, roles: ["teacher"], student: false, schedule: true };
const STUDENT: MeIn = { owner: false, roles: [], student: true, schedule: false };

const shalaOut = (me: MeIn, over: Record<string, unknown> = {}) => ({
  id: SHALA,
  name: "Ashtanga Almaty",
  city: { slug: "almaty", name: "Almaty" },
  zone: "Asia/Almaty",
  online: false,
  moon_city: null,
  staff: [{ id: ANNA, name: "Anna", owner: true, roles: ["teacher"] }],
  students_total: me.student ? null : 3,
  days_off: [6],
  moon_policy: "closed",
  me,
  ...over,
});

const occurrence = (over: Record<string, unknown> = {}) => ({
  class_id: CLASS,
  key: "2026-11-09",
  on: "2026-11-09",
  start: "06:00",
  end: "09:30",
  starts_at: "2026-11-09T01:00:00Z",
  type: "mysore",
  title: null,
  online: false,
  teacher: { id: ANNA, name: "Anna" },
  substitute: false,
  cancelled: null,
  moved: false,
  swapped_from: null,
  held: false,
  usual_teacher: { id: ANNA, name: "Anna" },
  ...over,
});

const day = (date: string, over: Record<string, unknown> = {}) => ({
  date,
  moon: false,
  day_off: false,
  swap_from: null,
  ...over,
});

const SCHEDULE = {
  zone: "Asia/Almaty",
  city: { slug: "almaty", name: "Almaty" },
  moon_policy: "closed",
  days_off: [6],
  days: [
    day("2026-11-09"),
    day("2026-11-13", { moon: true }),
    day("2026-11-14", { day_off: true }),
  ],
  occurrences: [
    occurrence(),
    occurrence({
      key: "2026-11-13",
      on: "2026-11-13",
      starts_at: "2026-11-13T01:00:00Z",
      cancelled: "moon",
    }),
  ],
  closures: [],
};

/** The Monday Mysore as saved: weekly, started long ago. */
const SERIES = {
  id: CLASS,
  type: "mysore",
  title: null,
  online: false,
  city: null,
  teacher_id: ANNA,
  start: "06:00",
  minutes: 210,
  weekdays: [1, 2, 3, 4, 5, 7],
  every: 1,
  starts_on: "2026-01-05",
  ends_on: null,
  rrule: "FREQ=WEEKLY",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Stub {
  card?: unknown;
  schedule?: unknown;
  /** The saved class series (`GET …/classes`); a deleted class leaves it. */
  classes?: unknown[] | undefined;
  /** The answer to a `PATCH` of a class; the merged class unless given. */
  patch?: () => Response;
  /** The answer to a cancel, a hold or a substitute; the cancelled date unless given. */
  put?: () => Response;
  /** The answer to a restore; done unless given. */
  restore?: () => Response;
  dayOff?: number[] | null;
  /** My own zone (the viewer's); Almaty, the shala's, unless given; null = not known yet. */
  timezone?: string | null;
}

function stubApi(stub: Stub = {}): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      await Promise.resolve();
      seen.push(request.clone());
      const path = new URL(request.url).pathname;
      if (path === `/api/v1/shalas/${SHALA}/schedule`) return json(stub.schedule ?? SCHEDULE);
      if (path === `/api/v1/shalas/${SHALA}/classes` && request.method === "POST")
        return json({ id: CLASS, rrule: null, ...((await request.json()) as object) }, 201);
      if (path === `/api/v1/shalas/${SHALA}/classes`) return json(stub.classes ?? []);
      if (path.startsWith(`/api/v1/shalas/${SHALA}/classes/`) && request.method === "PUT")
        return stub.put?.() ?? json(occurrence({ cancelled: "cancelled" }));
      if (
        path.startsWith(`/api/v1/shalas/${SHALA}/classes/${CLASS}/occurrences/`) &&
        request.method === "DELETE"
      )
        return stub.restore?.() ?? new Response(null, { status: 204 });
      if (path === `/api/v1/shalas/${SHALA}/classes/${CLASS}` && request.method === "PATCH")
        return stub.patch?.() ?? json({ ...SERIES, ...((await request.json()) as object) });
      if (path === `/api/v1/shalas/${SHALA}/classes/${CLASS}` && request.method === "DELETE") {
        // As the server: a deleted class is in no later list.
        stub.classes = stub.classes?.filter((c) => (c as { id: string }).id !== CLASS);
        return new Response(null, { status: 204 });
      }
      if (path === "/api/v1/me/announcements/sent") return json([]);
      if (path === "/api/v1/me/links") return json({ teachers: [], students: [] });
      if (path === `/api/v1/shalas/${SHALA}`) return json(stub.card ?? shalaOut(STUDENT));
      if (path === "/api/v1/moon/cities") return json(CITIES);
      if (path === "/api/v1/me/day-off") return json({ day_off: [6], practice_days: [] });
      if (path === "/api/v1/me")
        return json({
          id: "00000000-0000-0000-0000-000000000001",
          display_name: "Ash",
          locale: "en",
          timezone: stub.timezone === undefined ? "Asia/Almaty" : stub.timezone,
          home_city: null,
          name_from_telegram: true,
          locale_from_telegram: true,
          hide_ladies: false,
          offer_check_in: true,
          home_city_chosen: true,
          day_off: stub.dayOff === undefined ? [7] : stub.dayOff,
        });
      return json({});
    }),
  );
  return seen;
}

function renderWith(node: React.ReactNode, locale: Locale = "en") {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <L10nProvider locale={locale}>{node}</L10nProvider>
    </QueryClientProvider>,
  );
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
const pageText = () => plain(document.body.textContent);
const calls = (seen: Request[], method: string, path: string) =>
  seen.filter((r) => r.method === method && new URL(r.url).pathname === path);
const card = () => <ShalaScreen id={SHALA} onBack={vi.fn()} />;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("the schedule on the shala card", () => {
  it("shows the zone once, the window, and the moon and day-off rows", async () => {
    stubApi();
    renderWith(card());

    await screen.findAllByText(/06:00–09:30/); // two rows: Monday's and the cancelled Friday
    // The shala's zone is my own: the card names the place, with no offset (ADR-0044).
    await waitFor(() => {
      expect(pageText()).not.toContain("UTC+5");
    });
    const text = pageText();
    // UI-06 stage 5: in my own zone the place line is the place alone, as in the bot.
    expect(screen.getByText((t) => plain(t) === "📍 Almaty")).toBeInTheDocument();
    expect(text).not.toContain("shala time");
    expect(text).toContain("🌙 Moon day");
    expect(text).toContain("😌 Shala day off");
    expect(text).toContain("moon day"); // the cancelled Friday keeps its reason
  });

  it("shows the zone with its offset, once, to a member in another zone", async () => {
    stubApi({ timezone: "Asia/Tashkent" }); // the same clock, still another zone
    renderWith(card());

    await screen.findAllByText(/06:00–09:30/);
    await waitFor(() => {
      expect(pageText().match(/Almaty \(UTC\+5\)/g)).toHaveLength(1);
    });
    // Outside my zone the card says whose time it is, with the offset (ADR-0044).
    expect(
      screen.getByText((t) => plain(t) === "📍 Almaty · shala time: Almaty (UTC+5)"),
    ).toBeInTheDocument();
  });

  it("says whose time it is when the viewer's zone is not known yet", async () => {
    stubApi({ timezone: null });
    renderWith(card());

    await screen.findAllByText(/06:00–09:30/);
    // An unknown zone is no one's own: the offset shows (ADR-0044).
    expect(
      await screen.findByText((t) => plain(t) === "📍 Almaty · shala time: Almaty (UTC+5)"),
    ).toBeInTheDocument();
  });

  it.each([
    ["Asia/Kolkata", "Asia/Calcutta"],
    ["Asia/Calcutta", "Asia/Kolkata"],
  ])("takes %s and %s for the same zone: the place alone", async (shalaZone, mine) => {
    stubApi({
      timezone: mine,
      card: shalaOut(STUDENT, { city: { slug: "mysuru", name: "Mysuru" }, zone: shalaZone }),
    });
    renderWith(card());

    expect(await screen.findByText((t) => plain(t) === "📍 Mysuru")).toBeInTheDocument();
    await screen.findAllByText(/06:00–09:30/);
    expect(pageText()).not.toContain("shala time");
  });

  it("always says shala time when the shala's city is gone from the list, as the bot", async () => {
    // The API sends `Etc/UTC` and the city's slug when the city is no longer listed.
    stubApi({
      timezone: "Etc/UTC",
      card: shalaOut(STUDENT, { city: { slug: "atlantis", name: "atlantis" }, zone: "Etc/UTC" }),
    });
    renderWith(card());

    expect(
      await screen.findByText((t) => plain(t) === "📍 atlantis · shala time: atlantis"),
    ).toBeInTheDocument();
  });

  it("adds your time only when the viewer's offset differs", async () => {
    stubApi({
      schedule: {
        ...SCHEDULE,
        days: [day("2026-11-09")],
        occurrences: [
          occurrence({
            type: "led",
            online: true,
            start: "18:30",
            end: "20:00",
            starts_at: "2026-11-09T17:30:00Z",
          }),
        ],
        zone: "Europe/Berlin",
      },
    });
    renderWith(card());

    await screen.findByText(/18:30/);
    expect(pageText()).toContain("(22:30 your time)");
  });

  it("shows an online class from another city in the shala's time (Q124)", async () => {
    stubApi({
      schedule: {
        ...SCHEDULE,
        days: [day("2026-11-09")],
        occurrences: [
          occurrence({
            type: "led",
            online: true,
            start: "07:00", // Berlin wall clock
            end: "08:30",
            starts_at: "2026-11-09T06:00:00Z", // 11:00 in Almaty
          }),
        ],
      },
    });
    renderWith(card());

    await screen.findByText(/11:00–12:30/);
    expect(pageText()).not.toContain("07:00");
  });

  // UI-06 stage 4: the arrows stand either side of the week's own dates, over the days.
  it("names the week between its arrows; no arrow leads before this week", async () => {
    const seen = stubApi();
    renderWith(card());
    await screen.findAllByText(/06:00–09:30/);

    const nav = screen.getByRole("navigation");
    // "Nov 16 – 22", "Nov 30 – Dec 6": short enough for one line at 320px, also in Russian.
    expect(plain(nav.textContent)).toMatch(/^◀\w{3} \d+\s–\s(\w{3} )?\d+▶$/);
    expect(within(nav).getByRole("button", { name: "◀" })).toBeDisabled();
    const before = calls(seen, "GET", `/api/v1/shalas/${SHALA}/schedule`).length;
    fireEvent.click(within(nav).getByRole("button", { name: "▶" }));

    expect(within(nav).getByRole("button", { name: "◀" })).toBeEnabled();
    await waitFor(() => {
      expect(calls(seen, "GET", `/api/v1/shalas/${SHALA}/schedule`).length).toBe(before + 1);
    });
  });

  it("has no your-time note for a class in my own zone", async () => {
    stubApi();
    renderWith(card());

    await screen.findAllByText(/06:00–09:30/); // two rows: Monday's and the cancelled Friday
    expect(pageText()).not.toContain("your time");
  });
});

describe("the moon policy (owner, manager)", () => {
  it("is a select with its note, and sends moon_policy", async () => {
    const seen = stubApi({ card: shalaOut(OWNER) });
    renderWith(card());
    fireEvent.click(await screen.findByRole("button", { name: "✏️ Edit the shala" }));

    const policy = await screen.findByRole<HTMLSelectElement>("combobox", {
      name: /On moon days/,
    });
    expect([...policy.options].map((o) => o.value)).toEqual(["closed", "pranayama", "open"]);
    expect(pageText()).toContain("Dates follow the shala's moon city (lunar day at sunrise).");
    fireEvent.change(policy, { target: { value: "pranayama" } });
    fireEvent.submit(policy.closest("form") as HTMLFormElement);

    await waitFor(() => {
      expect(calls(seen, "PATCH", `/api/v1/shalas/${SHALA}`)).toHaveLength(1);
    });
    const body: unknown = await calls(seen, "PATCH", `/api/v1/shalas/${SHALA}`)[0]?.json();
    expect(body).toMatchObject({ moon_policy: "pranayama" });
  });
});

describe("the day-off adoption (Q109)", () => {
  it("is offered to a never-chose member and goes through PUT /me/day-off", async () => {
    const seen = stubApi({ dayOff: null });
    renderWith(card());

    fireEvent.click(await screen.findByRole("button", { name: "😌 Make Saturday my day off too" }));

    await waitFor(() => {
      expect(calls(seen, "PUT", "/api/v1/me/day-off")).toHaveLength(1);
    });
    const body: unknown = await calls(seen, "PUT", "/api/v1/me/day-off")[0]?.json();
    expect(JSON.stringify(body)).toContain("6");
  });

  it("is not offered to someone who chose", async () => {
    stubApi({ dayOff: [7] });
    renderWith(card());

    await screen.findAllByText(/06:00–09:30/); // two rows: Monday's and the cancelled Friday
    expect(screen.queryByRole("button", { name: /Make Saturday my day off/ })).toBeNull();
  });
});

describe("the occurrence sheet", () => {
  it("offers nothing to a student", async () => {
    stubApi();
    renderWith(card());

    fireEvent.click((await screen.findAllByText(/06:00–09:30/))[0] as HTMLElement);
    expect(screen.queryByRole("button", { name: /Cancel this date/ })).toBeNull();
  });

  it("lets a teacher cancel, and offers Hold anyway only on an auto-cancelled one", async () => {
    const seen = stubApi({ card: shalaOut(TEACHER) });
    renderWith(card());

    const rows = await screen.findAllByText(/06:00–09:30/);
    fireEvent.click(rows[0] as HTMLElement);
    expect(screen.queryByRole("button", { name: /Hold anyway/ })).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: "❌ Cancel this date" }));

    await waitFor(() => {
      expect(
        calls(seen, "PUT", `/api/v1/shalas/${SHALA}/classes/${CLASS}/occurrences/2026-11-09`),
      ).toHaveLength(1);
    });
    const body: unknown = await calls(
      seen,
      "PUT",
      `/api/v1/shalas/${SHALA}/classes/${CLASS}/occurrences/2026-11-09`,
    )[0]?.json();
    expect(body).toMatchObject({ status: "cancelled" });
  });

  it("offers Hold anyway on a moon-cancelled one", async () => {
    stubApi({ card: shalaOut(TEACHER) });
    renderWith(card());

    const rows = await screen.findAllByText(/06:00–09:30/);
    fireEvent.click(rows[1] as HTMLElement);
    expect(await screen.findByRole("button", { name: "✅ Hold anyway" })).toBeInTheDocument();
  });

  const STAFF = [
    { id: ANNA, name: "Anna", owner: true, roles: ["teacher"] },
    { id: DANA, name: "Dana", owner: false, roles: ["office"] },
  ];
  const putPath = `/api/v1/shalas/${SHALA}/classes/${CLASS}/occurrences/2026-11-09`;

  it("names any staff member as the substitute for one date", async () => {
    const seen = stubApi({ card: shalaOut(TEACHER, { staff: STAFF }) });
    renderWith(card());

    fireEvent.click((await screen.findAllByText(/06:00–09:30/))[0] as HTMLElement);
    const picker = await screen.findByLabelText("Teacher on this date");
    expect(
      within(picker)
        .getAllByRole("option")
        .map((o) => plain(o.textContent)),
    ).toEqual(["Usual teacher (Anna)", "Dana"]);
    fireEvent.change(picker, { target: { value: DANA } });

    await waitFor(() => {
      expect(calls(seen, "PUT", putPath)).toHaveLength(1);
    });
    const body: unknown = await calls(seen, "PUT", putPath)[0]?.json();
    expect(body).toEqual({ status: null, teacher_id: DANA });
  });

  it("names no one for the usual teacher, in one request", async () => {
    const covered = occurrence({ teacher: { id: DANA, name: "Dana" }, substitute: true });
    const schedule = { ...SCHEDULE, occurrences: [covered] };
    const seen = stubApi({ card: shalaOut(TEACHER, { staff: STAFF }), schedule });
    renderWith(card());

    fireEvent.click((await screen.findAllByText(/06:00–09:30/))[0] as HTMLElement);
    fireEvent.change(await screen.findByLabelText("Teacher on this date"), {
      target: { value: "" },
    });

    await waitFor(() => {
      expect(calls(seen, "PUT", putPath)).toHaveLength(1);
    });
    expect(calls(seen, "DELETE", putPath)).toHaveLength(0);
    const body: unknown = await calls(seen, "PUT", putPath)[0]?.json();
    expect(body).toEqual({ status: null, teacher_id: null });
  });

  it("re-sends a swapped date's own move, not the swap's day", async () => {
    const swapped = occurrence({
      on: "2026-11-14",
      starts_at: "2026-11-14T01:00:00Z",
      moved: true,
      swapped_from: "2026-11-13",
    });
    const schedule = {
      ...SCHEDULE,
      days: [day("2026-11-14", { day_off: true, swap_from: "2026-11-13" })],
      occurrences: [swapped],
    };
    const seen = stubApi({ card: shalaOut(TEACHER, { staff: STAFF }), schedule });
    renderWith(card());

    fireEvent.click((await screen.findAllByText(/06:00–09:30/))[0] as HTMLElement);
    fireEvent.change(await screen.findByLabelText("Teacher on this date"), {
      target: { value: DANA },
    });

    await waitFor(() => {
      expect(calls(seen, "PUT", putPath)).toHaveLength(1);
    });
    const body: unknown = await calls(seen, "PUT", putPath)[0]?.json();
    expect(body).toMatchObject({ on: "2026-11-13", teacher_id: DANA });
  });

  it("keeps a hold and a move when the substitute goes back to the usual teacher", async () => {
    const moved = occurrence({
      teacher: { id: DANA, name: "Dana" },
      substitute: true,
      held: true,
      moved: true,
      start: "07:00",
      end: "08:30",
      starts_at: "2026-11-09T02:00:00Z",
    });
    const schedule = { ...SCHEDULE, occurrences: [moved] };
    const seen = stubApi({ card: shalaOut(TEACHER, { staff: STAFF }), schedule });
    renderWith(card());

    fireEvent.click((await screen.findAllByText(/07:00–08:30/))[0] as HTMLElement);
    const picker = await screen.findByLabelText("Teacher on this date");
    expect((picker as HTMLSelectElement).value).toBe(DANA);
    fireEvent.change(picker, { target: { value: "" } });

    await waitFor(() => {
      expect(calls(seen, "PUT", putPath)).toHaveLength(1);
    });
    const body: unknown = await calls(seen, "PUT", putPath)[0]?.json();
    expect(body).toEqual({
      status: "held",
      on: "2026-11-09",
      start: "07:00",
      minutes: 90,
      teacher_id: null,
    });
  });

  it("names the substitute field in Russian as the form names the teacher", async () => {
    stubApi({ card: shalaOut(TEACHER, { staff: STAFF }) });
    renderWith(card(), "ru");

    fireEvent.click((await screen.findAllByText(/06:00–09:30/))[0] as HTMLElement);
    const picker = await screen.findByLabelText("Преподаватель на эту дату");
    expect(plain(within(picker).getAllByRole("option")[0]?.textContent)).toBe("Как обычно (Anna)");
  });

  it("offers no substitute on a cancelled date", async () => {
    stubApi({ card: shalaOut(TEACHER, { staff: STAFF }) });
    renderWith(card());

    fireEvent.click((await screen.findAllByText(/06:00–09:30/))[1] as HTMLElement);
    await screen.findByRole("button", { name: "✅ Hold anyway" });
    expect(screen.queryByLabelText("Teacher on this date")).toBeNull();
  });
});

const ME = "00000000-0000-0000-0000-000000000001";
const chip = (name: string | RegExp) => screen.getByRole("button", { name });
const pressed = (name: string) => chip(name).getAttribute("aria-pressed") === "true";
const more = () => screen.getByRole("button", { name: "More options" });
const save = () => {
  fireEvent.click(screen.getByRole("button", { name: "Save the class" }));
};
const posts = (seen: Request[]) => calls(seen, "POST", `/api/v1/shalas/${SHALA}/classes`);
const patches = (seen: Request[]) =>
  calls(seen, "PATCH", `/api/v1/shalas/${SHALA}/classes/${CLASS}`);

describe("the class form", () => {
  // The owner is on the staff under my own id, as the server lists them.
  const MINE = [{ id: ME, name: "Ash", owner: true, roles: ["teacher"] }];
  const form = (over: Record<string, unknown> = {}) => (
    <ClassForm shala={shalaOut(OWNER, { staff: MINE, ...over }) as never} onDone={vi.fn()} />
  );
  const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Almaty" }).format();

  it("shows three things to choose and Save; the rest is under More options", async () => {
    stubApi();
    renderWith(form());

    expect(await screen.findByRole("heading", { level: 1, name: "New class" })).toBeVisible();
    expect(screen.getByRole("group", { name: "Type" })).toBeInTheDocument();
    // The start time's label: my own zone, so the place alone (ADR-0044).
    expect(await screen.findByLabelText("Start, Almaty")).toHaveAttribute("type", "time");
    expect(screen.getByRole("group", { name: "Repeats on" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save the class" })).toBeInTheDocument();
    // Regularly or one date: two chips, the first chosen.
    const when = screen.getByRole("group", { name: "When" });
    expect(
      within(when)
        .getAllByRole("button")
        .map((b) => [b.textContent, b.getAttribute("aria-pressed")]),
    ).toEqual([
      ["Regularly", "true"],
      ["One date", "false"],
    ]);
    // Nothing else to fill in: no title, teacher, dates or online on the first screen.
    expect(screen.getAllByRole("group")).toHaveLength(3);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByLabelText(/Until/)).toBeNull();
    expect(more()).toHaveAttribute("aria-expanded", "false");
  });

  it("presets Mysore to every day but the shala's day off, and saves as it is", async () => {
    const seen = stubApi();
    renderWith(form());
    await screen.findByLabelText("Start, Almaty");

    expect(pressed("Mysore")).toBe(true);
    expect(pressed("Saturday")).toBe(false);
    expect(chip("Saturday")).toHaveTextContent("Sat"); // short on the chip, full for a reader
    for (const d of ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Sunday"])
      expect(pressed(d)).toBe(true);
    // What is set under "More options", in one line: the window's end and the teacher (me).
    await waitFor(() => {
      expect(more()).toHaveAccessibleDescription("until 09:30 · Ash");
    });
    save();

    await waitFor(() => {
      expect(posts(seen)).toHaveLength(1);
    });
    // The same body as before the short form, with me as the teacher (I hold Teacher).
    expect(await posts(seen)[0]?.json()).toEqual({
      type: "mysore",
      title: null,
      online: false,
      city: null,
      teacher_id: ME,
      start: "06:00",
      minutes: 210,
      weekdays: [1, 2, 3, 4, 5, 7],
      every: 1,
      starts_on: today(),
      ends_on: null,
    });
  });

  it("labels the start with the offset for staff in another zone", async () => {
    stubApi({ timezone: "Europe/Berlin" });
    renderWith(form());

    expect(await screen.findByLabelText("Start, Almaty (UTC+5)")).toBeInTheDocument();
  });

  it("starts other types with no day; Led shows its hint and 90 minutes", async () => {
    stubApi();
    renderWith(form());
    fireEvent.click(await screen.findByRole("button", { name: "Led" }));

    for (const d of ["Monday", "Friday", "Sunday"]) expect(pressed(d)).toBe(false);
    expect(pageText()).toContain("Often Friday or Sunday");
    expect(more()).toHaveAccessibleDescription(/^90 min/);

    fireEvent.click(chip("Conference"));
    expect(pageText()).not.toContain("Often Friday or Sunday");
    expect(more()).toHaveAccessibleDescription(/^60 min/);
  });

  it("refuses a weekly class with no day, without a request", async () => {
    const seen = stubApi();
    renderWith(form());
    fireEvent.click(await screen.findByRole("button", { name: "Led" }));
    save();

    expect(await screen.findByRole("alert")).toHaveTextContent("Choose at least one day");
    expect(posts(seen)).toHaveLength(0);

    fireEvent.click(chip("Friday"));
    expect(screen.queryByRole("alert")).toBeNull();
    save();
    await waitFor(() => {
      expect(posts(seen)).toHaveLength(1);
    });
    expect(await posts(seen)[0]?.json()).toMatchObject({
      type: "led",
      minutes: 90,
      weekdays: [5],
    });
  });

  it("takes one date instead of weekdays", async () => {
    const seen = stubApi();
    renderWith(form());
    fireEvent.click(await screen.findByRole("button", { name: "Workshop" }));
    fireEvent.click(chip("One date"));

    expect(screen.queryByRole("group", { name: "Repeats on" })).toBeNull();
    expect(pressed("One date")).toBe(true);
    expect(pressed("Regularly")).toBe(false);
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-12-05" } });
    save();

    await waitFor(() => {
      expect(posts(seen)).toHaveLength(1);
    });
    expect(await posts(seen)[0]?.json()).toMatchObject({
      type: "workshop",
      minutes: 120,
      weekdays: [],
      every: 1,
      starts_on: "2026-12-05",
      ends_on: null,
    });
  });

  it("offers how long as chips, and any other length in minutes", async () => {
    const seen = stubApi();
    renderWith(form());
    fireEvent.click(await screen.findByRole("button", { name: "Led" }));
    fireEvent.click(chip("Friday"));
    fireEvent.click(more());

    const length = screen.getByRole("group", { name: "How long" });
    expect(
      within(length)
        .getAllByRole("button")
        .map((b) => plain(b.textContent)),
    ).toEqual(["60 min", "75 min", "90 min", "120 min", "Enter minutes"]);
    expect(within(length).getByRole("button", { name: "90 min" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.queryByLabelText("How many minutes")).toBeNull();
    fireEvent.click(within(length).getByRole("button", { name: "75 min" }));
    // Changing the start keeps the length.
    fireEvent.change(screen.getByLabelText("Start, Almaty"), { target: { value: "18:30" } });
    fireEvent.click(within(length).getByRole("button", { name: "Enter minutes" }));
    // Minutes, as on the chips: a number, not a clock.
    const minutes = screen.getByLabelText<HTMLInputElement>("How many minutes");
    expect(minutes).toHaveAttribute("type", "number");
    expect(minutes).toHaveAttribute("inputmode", "numeric");
    expect(minutes.value).toBe("75");
    expect(screen.queryByLabelText("Ends at")).toBeNull();
    fireEvent.change(minutes, { target: { value: "105" } });
    save();

    await waitFor(() => {
      expect(posts(seen)).toHaveLength(1);
    });
    expect(await posts(seen)[0]?.json()).toMatchObject({ start: "18:30", minutes: 105 });
  });

  it("refuses minutes that do not fit, at the field, without a request", async () => {
    const seen = stubApi();
    renderWith(form());
    fireEvent.click(await screen.findByRole("button", { name: "Led" }));
    fireEvent.click(chip("Friday"));
    fireEvent.click(more());
    fireEvent.click(screen.getByRole("button", { name: "Enter minutes" }));
    fireEvent.change(screen.getByLabelText("How many minutes"), { target: { value: "" } });
    fireEvent.click(more()); // folded: the mistake is out of sight
    save();

    expect(await screen.findByRole("alert")).toHaveTextContent("15 to 480 minutes");
    expect(screen.getByLabelText("How many minutes")).toHaveFocus();
    expect(screen.getByLabelText("How many minutes")).toHaveAttribute("aria-invalid", "true");
    expect(posts(seen)).toHaveLength(0);
  });

  it("refuses a last date before the first one, at the field, without a request", async () => {
    const seen = stubApi();
    renderWith(form());
    await screen.findByLabelText("Start, Almaty");
    fireEvent.click(more());
    fireEvent.change(screen.getByLabelText("First date"), { target: { value: "2099-06-01" } });
    fireEvent.change(screen.getByLabelText(/Last date/), { target: { value: "2099-05-31" } });
    fireEvent.click(more());
    save();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The last date is before the first one.",
    );
    expect(screen.getByLabelText(/Last date/)).toHaveFocus();
    expect(screen.getByLabelText(/Last date/)).toHaveAttribute("aria-invalid", "true");
    expect(posts(seen)).toHaveLength(0);
  });

  it("shows an example in the empty title field", async () => {
    stubApi();
    renderWith(form());
    await screen.findByLabelText("Start, Almaty");
    fireEvent.click(more());

    expect(screen.getByLabelText(/Title/)).toHaveAttribute("placeholder", "Full Primary");
  });

  it("saves once when Save is pressed twice before the screen redraws", async () => {
    const seen = stubApi();
    renderWith(form());
    await screen.findByLabelText("Start, Almaty");
    const button = screen.getByRole("button", { name: "Save the class" });

    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });

    await waitFor(() => {
      expect(posts(seen)).toHaveLength(1);
    });
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(posts(seen)).toHaveLength(1);
  });

  it("Back asks before it drops what was typed, and not when nothing was", async () => {
    stubApi();
    const onDone = vi.fn();
    renderWith(<ClassForm shala={shalaOut(OWNER, { staff: MINE }) as never} onDone={onDone} />);
    await screen.findByLabelText("Start, Almaty");
    const back = () => {
      act(() => {
        vi.mocked(useBackButton).mock.lastCall?.[0]();
      });
    };

    back();
    expect(confirmDestructive).not.toHaveBeenCalled();
    expect(onDone).toHaveBeenCalledWith();

    onDone.mockClear();
    vi.mocked(confirmDestructive).mockResolvedValueOnce(false);
    fireEvent.change(screen.getByLabelText("Start, Almaty"), { target: { value: "07:00" } });
    back();
    expect(confirmDestructive).toHaveBeenCalledWith(
      "Leave without saving this class?",
      "Don't save",
      "Keep editing",
    );
    await act(() => Promise.resolve());
    expect(onDone).not.toHaveBeenCalled(); // "Keep editing": the form stays

    back(); // and "Don't save" closes it
    await waitFor(() => {
      expect(onDone).toHaveBeenCalledWith();
    });
  });

  it("opens More options on a window that ends before it starts, without a request", async () => {
    const seen = stubApi();
    renderWith(form());
    await screen.findByLabelText("Start, Almaty");
    fireEvent.click(more());
    fireEvent.change(screen.getByLabelText("Start, Almaty"), { target: { value: "09:00" } });
    fireEvent.change(screen.getByLabelText("Until"), { target: { value: "08:00" } });
    fireEvent.click(more()); // folded again: the mistake is out of sight
    expect(screen.queryByLabelText("Until")).toBeNull();
    save();

    expect(await screen.findByRole("alert")).toHaveTextContent("needs to end after it starts");
    const until = screen.getByLabelText("Until");
    expect(more()).toHaveAttribute("aria-expanded", "true");
    expect(until).toHaveFocus();
    expect(until).toHaveAttribute("aria-invalid", "true");
    expect(posts(seen)).toHaveLength(0);
  });

  it("sends the Mysore window as minutes", async () => {
    const seen = stubApi();
    renderWith(form());
    await screen.findByLabelText("Start, Almaty");
    fireEvent.click(more());

    fireEvent.change(screen.getByLabelText("Start, Almaty"), { target: { value: "06:30" } });
    expect(screen.getByLabelText<HTMLInputElement>("Until").value).toBe("10:00");
    fireEvent.change(screen.getByLabelText("Until"), { target: { value: "09:00" } });
    save();

    await waitFor(() => {
      expect(posts(seen)).toHaveLength(1);
    });
    expect(await posts(seen)[0]?.json()).toMatchObject({
      type: "mysore",
      start: "06:30",
      minutes: 150,
      weekdays: [1, 2, 3, 4, 5, 7],
      every: 1,
    });
  });

  it("offers the zone select for online classes only", async () => {
    stubApi();
    renderWith(form());
    await screen.findByLabelText("Start, Almaty");
    fireEvent.click(more());

    expect(screen.queryByRole("combobox", { name: /Times in/ })).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /online/i }));
    const zone = await screen.findByRole<HTMLSelectElement>("combobox", { name: /Times in/ });
    expect(zone.value).toBe("almaty");
    expect(within(zone).getByText(/Berlin/)).toBeInTheDocument();
  });

  it("lists every staff member as the teacher: teachers first, an owner without roles too", async () => {
    stubApi();
    const staff = [
      { id: ME, name: "Ash", owner: true, roles: [] },
      { id: DANA, name: "Dana", owner: false, roles: ["office"] },
      { id: ANNA, name: "Anna", owner: false, roles: ["assistant"] },
    ];
    const me = { ...OWNER, roles: [] };
    renderWith(<ClassForm shala={shalaOut(me, { staff }) as never} onDone={vi.fn()} />);
    await screen.findByLabelText("Start, Almaty");
    fireEvent.click(more());

    const teacher = screen.getByRole<HTMLSelectElement>("combobox", { name: "Teacher" });
    expect([...teacher.options].map((o) => o.textContent)).toEqual(["—", "Anna", "Ash", "Dana"]);
    expect(teacher.value).toBe(""); // I hold no Teacher role: nobody is preselected
  });

  it("reads in Russian", async () => {
    stubApi();
    renderWith(form(), "ru");

    expect(await screen.findByRole("heading", { level: 1, name: "Новое занятие" })).toBeVisible();
    expect(screen.getByRole("group", { name: "Повторяется по дням" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "суббота" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Дополнительно" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Когда" })).toHaveTextContent("РегулярноОдна дата");
  });
});

describe("changing a class (ADR-0048)", () => {
  const MONDAY = "2099-06-01"; // the date that was tapped: far ahead, so never before today
  const edit = (onDone = vi.fn(), date = MONDAY, startsAt?: string) => (
    <ClassForm
      shala={shalaOut(OWNER) as never}
      edit={{ classId: CLASS, date, startsAt }}
      onDone={onDone}
    />
  );
  const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Almaty" }).format();
  const after = (day: string, n: number) => {
    const d = new Date(`${day}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  };
  const named = (day: string) =>
    new Intl.DateTimeFormat("en", {
      weekday: "short",
      day: "numeric",
      month: "short",
      timeZone: "UTC",
    }).format(new Date(`${day}T00:00:00Z`));
  /** "Another date": the date field behind the sentence. */
  const anotherDate = async () => {
    fireEvent.click(await screen.findByRole("button", { name: "Another date" }));
    return screen.getByLabelText<HTMLInputElement>("Changes apply from");
  };

  it("fills the form from the saved class and names the date the change applies from", async () => {
    stubApi({ classes: [SERIES] });
    renderWith(edit());

    expect(
      await screen.findByRole("heading", { level: 1, name: "Change the class" }),
    ).toBeVisible();
    // One sentence, not a field: the date that was tapped, and what stays.
    expect(
      await screen.findByText("Changes apply from Mon, Jun 1. Earlier dates stay as they were."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Changes apply from")).toBeNull();
    expect(pressed("Mysore")).toBe(true);
    expect(pressed("Saturday")).toBe(false);
    // A class keeps its kind: no switch to one date, and no first date to rewrite.
    expect(screen.queryByRole("group", { name: "When" })).toBeNull();
    // "Another date" brings the field, on the same date, never before the shala's today.
    const applies = await anotherDate();
    expect(applies.value).toBe(MONDAY);
    expect(applies).toHaveAttribute("min", today());
    expect(applies).toHaveFocus();
    expect(applies).toHaveAccessibleDescription("Earlier dates stay as they were.");
    expect(screen.queryByRole("button", { name: "Another date" })).toBeNull();
    fireEvent.click(more());
    expect(screen.queryByLabelText("First date")).toBeNull();
    expect(screen.getByLabelText<HTMLInputElement>("Until").value).toBe("09:30");
  });

  it("sends only the changed fields, from the tapped date", async () => {
    const seen = stubApi({ classes: [SERIES] });
    const onDone = vi.fn();
    renderWith(edit(onDone));
    fireEvent.change(await screen.findByLabelText("Start, Almaty"), {
      target: { value: "07:00" },
    });
    fireEvent.click(chip("Sunday"));
    save();

    await waitFor(() => {
      expect(patches(seen)).toHaveLength(1);
    });
    expect(await patches(seen)[0]?.json()).toEqual({
      start: "07:00",
      weekdays: [1, 2, 3, 4, 5],
      from: MONDAY,
    });
    await waitFor(() => {
      expect(onDone).toHaveBeenCalledWith("saved");
    });
  });

  it("never applies before the shala's today, also for a date of last week", async () => {
    const seen = stubApi({ classes: [SERIES] });
    renderWith(edit(vi.fn(), "2026-01-05", "2026-01-05T01:00:00Z"));
    const applies = await anotherDate();
    expect(applies.value >= today()).toBe(true);
    fireEvent.change(applies, { target: { value: "2020-01-01" } }); // typed past the picker
    fireEvent.click(more());
    fireEvent.change(screen.getByLabelText(/Title/), { target: { value: "Full Primary" } });
    save();

    await waitFor(() => {
      expect(patches(seen)).toHaveLength(1);
    });
    expect(await patches(seen)[0]?.json()).toEqual({ title: "Full Primary", from: today() });
  });

  // Review fix: a class that has already begun today keeps its marks and its place on today's
  // schedule: the change starts with the class's next date.
  const DAILY = { ...SERIES, weekdays: [1, 2, 3, 4, 5, 6, 7] };

  it("applies from the class's next date when the tapped date's class has begun", async () => {
    const seen = stubApi({ classes: [DAILY] });
    const begun = new Date(Date.now() - 60_000).toISOString();
    renderWith(edit(vi.fn(), today(), begun));

    const next = after(today(), 1);
    expect(
      await screen.findByText(
        `Changes apply from ${named(next)}. Earlier dates stay as they were.`,
      ),
    ).toBeInTheDocument();
    fireEvent.click(chip("Sunday"));
    save();

    await waitFor(() => {
      expect(patches(seen)).toHaveLength(1);
    });
    expect(await patches(seen)[0]?.json()).toEqual({ weekdays: [1, 2, 3, 4, 5, 6], from: next });
  });

  it("applies from the tapped date when its class has not begun", async () => {
    stubApi({ classes: [DAILY] });
    const later = new Date(Date.now() + 3_600_000).toISOString();
    renderWith(edit(vi.fn(), today(), later));

    expect(
      await screen.findByText(
        `Changes apply from ${named(today())}. Earlier dates stay as they were.`,
      ),
    ).toBeInTheDocument();
  });

  // Review fix: the class already has a last date (a later change begins after it, or it
  // simply ends). The form says how far this change reaches, and so does the delete.
  const ENDING = { ...SERIES, ends_on: "2099-12-31" };

  it("says how far the change reaches when the class has a last date", async () => {
    stubApi({ classes: [ENDING] });
    renderWith(edit());

    expect(
      await screen.findByText(
        "Changes apply from Mon, Jun 1. Earlier dates stay as they were. " +
          "The changes apply through the class's last date: Thu, Dec 31.",
      ),
    ).toBeInTheDocument();
    const applies = await anotherDate();
    expect(applies).toHaveAccessibleDescription(
      "Earlier dates stay as they were. " +
        "The changes apply through the class's last date: Thu, Dec 31.",
    );
  });

  it("names the dates a delete removes when the class has a last date", async () => {
    const seen = stubApi({ classes: [ENDING] });
    renderWith(edit());

    fireEvent.click(
      await screen.findByRole("button", { name: "🗑 Delete this class (all dates)…" }),
    );

    await waitFor(() => {
      expect(calls(seen, "DELETE", `/api/v1/shalas/${SHALA}/classes/${CLASS}`)).toHaveLength(1);
    });
    expect(plain(vi.mocked(confirmDestructive).mock.lastCall?.[0])).toBe(
      "Delete this class from Jan 5, 2026 through Dec 31, 2099? Anything after that stays. " +
        "No one gets a message.",
    );
  });

  it("asks about every date when the class has no last date", async () => {
    stubApi({ classes: [SERIES] });
    renderWith(edit());

    fireEvent.click(
      await screen.findByRole("button", { name: "🗑 Delete this class (all dates)…" }),
    );

    await waitFor(() => {
      expect(confirmDestructive).toHaveBeenCalled();
    });
    expect(vi.mocked(confirmDestructive).mock.lastCall?.[0]).toMatch(/on every date\?/);
  });

  it("refuses an apply date after the last date, with the reason, without a request", async () => {
    const seen = stubApi({ classes: [{ ...SERIES, ends_on: "2099-05-31" }] });
    const onDone = vi.fn();
    renderWith(edit(onDone));
    fireEvent.change(await screen.findByLabelText("Start, Almaty"), {
      target: { value: "07:00" },
    });
    save();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The last date is before the date the changes apply from.",
    );
    expect(screen.getByLabelText(/Last date/)).toHaveFocus();
    expect(patches(seen)).toHaveLength(0);
    expect(onDone).not.toHaveBeenCalled();
  });

  it("changes a class that has not started whole: its first date, and no from", async () => {
    const ahead = { ...SERIES, starts_on: "2099-05-04" };
    const seen = stubApi({ classes: [ahead] });
    renderWith(edit());
    await screen.findByLabelText("Start, Almaty");

    expect(screen.queryByLabelText("Changes apply from")).toBeNull();
    fireEvent.click(more());
    fireEvent.change(screen.getByLabelText("First date"), { target: { value: "2099-05-11" } });
    save();

    await waitFor(() => {
      expect(patches(seen)).toHaveLength(1);
    });
    expect(await patches(seen)[0]?.json()).toEqual({ starts_on: "2099-05-11" });
  });

  it("changes a one-date class whole", async () => {
    const once = { ...SERIES, type: "workshop", weekdays: [], minutes: 120, rrule: null };
    const seen = stubApi({ classes: [{ ...once, starts_on: "2026-01-05" }] });
    renderWith(edit());

    const date = await screen.findByLabelText<HTMLInputElement>("Date");
    expect(date.value).toBe("2026-01-05");
    expect(screen.queryByLabelText("Changes apply from")).toBeNull();
    expect(screen.queryByRole("group", { name: "Repeats on" })).toBeNull();
    fireEvent.change(date, { target: { value: "2099-05-11" } });
    save();

    await waitFor(() => {
      expect(patches(seen)).toHaveLength(1);
    });
    expect(await patches(seen)[0]?.json()).toEqual({ starts_on: "2099-05-11" });
  });

  it("closes without a request when nothing was changed", async () => {
    const seen = stubApi({ classes: [SERIES] });
    const onDone = vi.fn();
    renderWith(edit(onDone));
    await screen.findByLabelText("Start, Almaty");
    save();

    expect(onDone).toHaveBeenCalledWith();
    expect(patches(seen)).toHaveLength(0);
  });

  it("says the class is gone on a 404", async () => {
    const seen = stubApi({ classes: [SERIES], patch: () => json({ code: "not_found" }, 404) });
    const onDone = vi.fn();
    renderWith(edit(onDone));
    fireEvent.change(await screen.findByLabelText("Start, Almaty"), {
      target: { value: "07:00" },
    });
    save();

    await waitFor(() => {
      expect(onDone).toHaveBeenCalledWith("gone");
    });
    expect(patches(seen)).toHaveLength(1);
  });

  it("says so at once when the class is no longer in the list", async () => {
    stubApi({ classes: [] });
    const onDone = vi.fn();
    renderWith(edit(onDone));

    await waitFor(() => {
      expect(onDone).toHaveBeenCalledWith("gone");
    });
    expect(screen.queryByRole("button", { name: "Save the class" })).toBeNull();
  });

  it("keeps the form on a refusal, with the reason", async () => {
    stubApi({ classes: [SERIES], patch: () => json({ code: "invalid_class" }, 422) });
    const onDone = vi.fn();
    renderWith(edit(onDone));
    fireEvent.change(await screen.findByLabelText("Start, Almaty"), {
      target: { value: "07:00" },
    });
    save();

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't save the class");
    expect(onDone).not.toHaveBeenCalled();
    // What I typed stays, whatever the refetch brought.
    expect(screen.getByLabelText<HTMLInputElement>("Start, Almaty").value).toBe("07:00");
  });

  it("deletes the class from the form, after the confirm: saved, never gone", async () => {
    const seen = stubApi({ classes: [SERIES] });
    const onDone = vi.fn();
    renderWith(edit(onDone));

    fireEvent.click(
      await screen.findByRole("button", { name: "🗑 Delete this class (all dates)…" }),
    );

    await waitFor(() => {
      expect(calls(seen, "DELETE", `/api/v1/shalas/${SHALA}/classes/${CLASS}`)).toHaveLength(1);
    });
    await waitFor(() => {
      expect(onDone).toHaveBeenCalledWith("saved");
    });
    // The list refetched after the delete no longer has the class: that is my own doing.
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});

describe("the sheet's two groups, and the form as a layer", () => {
  const MANAGER: MeIn = { ...TEACHER, announce: true };
  const openSheet = async (n = 0) => {
    fireEvent.click((await screen.findAllByText(/06:00–09:30/))[n] as HTMLElement);
    return screen.findByRole("heading", { name: "The whole class" });
  };
  const putPath = `/api/v1/shalas/${SHALA}/classes/${CLASS}/occurrences/2026-11-09`;

  it("heads what is for this date and what is for the whole class; no Delete here", async () => {
    stubApi({ card: shalaOut(TEACHER) });
    renderWith(card());
    await openSheet();

    expect(screen.getByRole("heading", { name: "This date: Mon, Nov 9" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "❌ Cancel this date" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "✏️ Change the class…" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete this class/ })).toBeNull();
  });

  it("opens the saved class from its date, and Back returns to the card as it was", async () => {
    stubApi({ card: shalaOut(TEACHER), classes: [SERIES] });
    renderWith(card());
    await openSheet();
    fireEvent.click(screen.getByRole("button", { name: "✏️ Change the class…" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Change the class" }),
    ).toBeVisible();
    expect(await screen.findByText(/^Changes apply from \w/)).toBeInTheDocument();
    // The card waits under the layer, out of sight and out of reach.
    expect(screen.queryByRole("button", { name: "➕ Add a class" })).toBeNull();

    act(() => {
      vi.mocked(useBackButton).mock.lastCall?.[0]();
    });

    expect(screen.queryByRole("heading", { name: "Change the class" })).toBeNull();
    expect(screen.getByRole("button", { name: "✏️ Change the class…" })).toBeVisible(); // still open
  });

  it("shows the class-gone line over the week when the class is no longer there", async () => {
    const seen = stubApi({ card: shalaOut(TEACHER), classes: [] });
    renderWith(card());
    await openSheet();
    const before = calls(seen, "GET", `/api/v1/shalas/${SHALA}/schedule`).length;
    fireEvent.click(screen.getByRole("button", { name: "✏️ Change the class…" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "This class has just changed or was removed. Here's the current schedule.",
    );
    expect(screen.queryByRole("heading", { name: "Change the class" })).toBeNull();
    await waitFor(() => {
      expect(calls(seen, "GET", `/api/v1/shalas/${SHALA}/schedule`).length).toBeGreaterThan(before);
    });
  });

  it("opens a new class from the first row of the schedule", async () => {
    stubApi({ card: shalaOut(TEACHER) });
    renderWith(card());

    fireEvent.click(await screen.findByRole("button", { name: "➕ Add a class" }));

    expect(await screen.findByRole("heading", { level: 1, name: "New class" })).toBeVisible();
  });

  it("offers Tell students after a cancel, with the text filled in", async () => {
    const seen = stubApi({ card: shalaOut(MANAGER) });
    renderWith(card());
    await openSheet();

    expect(screen.queryByRole("button", { name: "📣 Tell students…" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "❌ Cancel this date" }));
    await waitFor(() => {
      expect(calls(seen, "PUT", putPath)).toHaveLength(1);
    });
    fireEvent.click(await screen.findByRole("button", { name: "📣 Tell students…" }));

    // The compose screen, with a text a reader in any zone can use: day, time, zone, offset.
    const text = await screen.findByRole<HTMLTextAreaElement>("textbox", { name: "Text" });
    expect(text.value).toBe(
      "Hi everyone. Mysore on Mon, Nov 9 at 06:00 Almaty (UTC+5) is cancelled. " +
        "See you next time 🙏",
    );
    // Nothing went out by the cancel or by opening the screen.
    expect(calls(seen, "POST", "/api/v1/me/announcements")).toHaveLength(0);
  });

  it("writes the cancellation in Russian with the class after a colon", async () => {
    stubApi({ card: shalaOut(MANAGER) });
    renderWith(card(), "ru");
    fireEvent.click((await screen.findAllByText(/06:00–09:30/))[0] as HTMLElement);
    fireEvent.click(await screen.findByRole("button", { name: "❌ Отменить на эту дату" }));
    fireEvent.click(await screen.findByRole("button", { name: "📣 Сообщить ученикам…" }));

    const text = await screen.findByRole<HTMLTextAreaElement>("textbox");
    // The stubbed account reads dates in English; the sentence around them is the message's.
    expect(text.value).toBe(
      "Всем привет! Занятие отменяется: Майсор, Mon, Nov 9, 06:00 Almaty (UTC+5). " +
        "До следующей встречи 🙏",
    );
  });

  // Review: the offer is not a moment that passes. A date cancelled yesterday still has it.
  it("keeps Tell students on a date that is already cancelled", async () => {
    const off = occurrence({ cancelled: "cancelled" });
    stubApi({ card: shalaOut(MANAGER), schedule: { ...SCHEDULE, occurrences: [off] } });
    renderWith(card());
    await openSheet();

    expect(screen.getByRole("button", { name: "↩ Restore" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "📣 Tell students…" }));

    const text = await screen.findByRole<HTMLTextAreaElement>("textbox", { name: "Text" });
    expect(text.value).toContain("Mysore on Mon, Nov 9");
  });

  it("returns from the announcement to the card as it was: the week, the open date", async () => {
    const off = occurrence({ cancelled: "cancelled" });
    stubApi({ card: shalaOut(MANAGER), schedule: { ...SCHEDULE, occurrences: [off] } });
    renderWith(card());
    await screen.findAllByText(/06:00–09:30/);
    fireEvent.click(within(screen.getByRole("navigation")).getByRole("button", { name: "▶" }));
    await openSheet();
    fireEvent.click(screen.getByRole("button", { name: "📣 Tell students…" }));
    await screen.findByRole("textbox", { name: "Text" });
    // The card waits under the announcement, out of sight and out of reach.
    expect(screen.queryByRole("button", { name: "➕ Add a class" })).toBeNull();

    act(() => {
      vi.mocked(useBackButton).mock.lastCall?.[0]();
    });

    expect(screen.queryByRole("textbox", { name: "Text" })).toBeNull();
    expect(screen.getByRole("heading", { name: "The whole class" })).toBeVisible(); // still open
    const nav = screen.getByRole("navigation");
    expect(within(nav).getByRole("button", { name: "◀" })).toBeEnabled(); // still the next week
  });

  it("does not offer it for a 1:1, or to someone who may not announce", async () => {
    const one = { ...SCHEDULE, occurrences: [occurrence({ type: "private" })] };
    const seen = stubApi({ card: shalaOut(MANAGER), schedule: one });
    const first = renderWith(card());
    await openSheet();
    fireEvent.click(screen.getByRole("button", { name: "❌ Cancel this date" }));
    await waitFor(() => {
      expect(calls(seen, "PUT", putPath)).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "The whole class" })).toBeNull(); // closed
    });
    expect(screen.queryByRole("button", { name: "📣 Tell students…" })).toBeNull();
    first.unmount();

    const again = stubApi({ card: shalaOut(TEACHER) });
    renderWith(card());
    await openSheet();
    fireEvent.click(screen.getByRole("button", { name: "❌ Cancel this date" }));
    await waitFor(() => {
      expect(calls(again, "PUT", putPath)).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "The whole class" })).toBeNull();
    });
    expect(screen.queryByRole("button", { name: "📣 Tell students…" })).toBeNull();
  });

  it("does not offer it when there is no one to tell", async () => {
    // Me alone on the staff and no student: the announcement would have no reader.
    const alone = shalaOut(MANAGER, { students_total: 0 });
    const off = occurrence({ cancelled: "cancelled" });
    stubApi({ card: alone, schedule: { ...SCHEDULE, occurrences: [off] } });
    renderWith(card());
    await openSheet();

    expect(screen.getByRole("button", { name: "↩ Restore" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "📣 Tell students…" })).toBeNull();
  });

  // Review fix: the class was changed "from a date" while this sheet was open, so its id has
  // no such date any more. Not "Try again" for ever: the current schedule, and a line saying why.
  it.each([
    ["a cancel", "❌ Cancel this date", "PUT"],
    ["a restore", "↩ Restore", "DELETE"],
  ])("shows the current schedule when %s meets a class that has changed", async (_, name, verb) => {
    const gone = () => json({ code: "not_found" }, 404);
    const shown = name.startsWith("↩") ? occurrence({ cancelled: "cancelled" }) : occurrence();
    const seen = stubApi({
      card: shalaOut(TEACHER),
      schedule: { ...SCHEDULE, occurrences: [shown] },
      put: gone,
      restore: gone,
    });
    renderWith(card());
    await openSheet();
    const before = calls(seen, "GET", `/api/v1/shalas/${SHALA}/schedule`).length;

    fireEvent.click(screen.getByRole("button", { name }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "This class has just changed or was removed. Here's the current schedule.",
    );
    expect(calls(seen, verb, putPath)).toHaveLength(1);
    expect(screen.queryByText(/Couldn't change the class/)).toBeNull();
    expect(screen.queryByRole("heading", { name: "The whole class" })).toBeNull(); // closed
    await waitFor(() => {
      expect(calls(seen, "GET", `/api/v1/shalas/${SHALA}/schedule`).length).toBeGreaterThan(before);
    });
  });

  // Review fix (a): the list in the cache is from an earlier visit to the form and has no
  // class B, added since. "Gone" is decided on a list fetched after the form opened.
  it("opens a class added since the form was last open", async () => {
    const B = "00000000-0000-0000-0000-0000000000d2";
    const second = occurrence({
      class_id: B,
      type: "led",
      start: "18:00",
      end: "19:30",
      starts_at: "2026-11-09T13:00:00Z",
    });
    const stub: Stub = {
      card: shalaOut(TEACHER),
      schedule: { ...SCHEDULE, occurrences: [occurrence(), second] },
      classes: [SERIES],
    };
    stubApi(stub);
    renderWith(card());
    await openSheet();
    fireEvent.click(screen.getByRole("button", { name: "✏️ Change the class…" }));
    await screen.findByRole("button", { name: "Save the class" });
    act(() => {
      vi.mocked(useBackButton).mock.lastCall?.[0]();
    });
    // Class B is saved meanwhile (the form's own "Add a class" leaves the list as stale).
    stub.classes = [SERIES, { ...SERIES, id: B, type: "led", start: "18:00", minutes: 90 }];

    fireEvent.click(await screen.findByText(/18:00–19:30/));
    const edits = await screen.findAllByRole("button", { name: "✏️ Change the class…" });
    fireEvent.click(edits.at(-1) as HTMLElement);

    expect(await screen.findByRole("button", { name: "Save the class" })).toBeInTheDocument();
    expect(pressed("Led")).toBe(true);
    expect(screen.queryByRole("status")).toBeNull();
  });

  // Review fix (b): my own delete is not "this class has just changed".
  it("returns from a delete to the schedule without the class-gone line", async () => {
    const seen = stubApi({ card: shalaOut(TEACHER), classes: [SERIES] });
    renderWith(card());
    await openSheet();
    fireEvent.click(screen.getByRole("button", { name: "✏️ Change the class…" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "🗑 Delete this class (all dates)…" }),
    );

    await waitFor(() => {
      expect(calls(seen, "DELETE", `/api/v1/shalas/${SHALA}/classes/${CLASS}`)).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Change the class" })).toBeNull();
    });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("gives the focus back to the row that opened the form", async () => {
    stubApi({ card: shalaOut(TEACHER), classes: [SERIES] });
    renderWith(card());
    await openSheet();
    const row = screen.getByRole("button", { name: "✏️ Change the class…" });
    row.focus();
    fireEvent.click(row);
    await screen.findByRole("button", { name: "Save the class" });
    expect(row).not.toHaveFocus();

    act(() => {
      vi.mocked(useBackButton).mock.lastCall?.[0]();
    });

    expect(row).toHaveFocus();
  });
});

// Review: the sheet's "whole class" group can end a class from the date that was tapped. Only
// on a date that has not begun: a class that ran is never taken off the schedule (ADR-0048).
describe("End this class from this date", () => {
  const ahead = occurrence({
    key: "2099-06-01",
    on: "2099-06-01",
    starts_at: "2099-06-01T01:00:00Z",
  });
  const schedule = { ...SCHEDULE, days: [day("2099-06-01")], occurrences: [ahead] };
  const row = { name: "⏹️ End this class from this date…" };
  const open = async () => {
    fireEvent.click((await screen.findAllByText(/06:00–09:30/))[0] as HTMLElement);
    await screen.findByRole("heading", { name: "The whole class" });
  };

  it("sets the last date to the day before, after a confirm that earlier dates stay", async () => {
    const seen = stubApi({ card: shalaOut(TEACHER), schedule, classes: [SERIES] });
    renderWith(card());
    await open();

    fireEvent.click(screen.getByRole("button", row));

    await waitFor(() => {
      expect(patches(seen)).toHaveLength(1);
    });
    expect(plain(vi.mocked(confirmDestructive).mock.lastCall?.[0])).toBe(
      "End this class from Mon, Jun 1? That date and later ones go from the schedule. " +
        "Earlier dates stay. No one gets a message.",
    );
    expect(await patches(seen)[0]?.json()).toEqual({ ends_on: "2099-05-31" });
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "The whole class" })).toBeNull(); // closed
    });
  });

  // As with Delete: a class that already has a last date ends only up to it. What comes
  // after (a later change of the same class is a class of its own) stays, and the question
  // names the last date.
  it("names the dates that go when the class has a last date", async () => {
    const ending = { ...SERIES, ends_on: "2099-12-31" };
    const seen = stubApi({ card: shalaOut(TEACHER), schedule, classes: [ending] });
    renderWith(card());
    await open();

    fireEvent.click(screen.getByRole("button", row));

    await waitFor(() => {
      expect(patches(seen)).toHaveLength(1);
    });
    expect(plain(vi.mocked(confirmDestructive).mock.lastCall?.[0])).toBe(
      "End this class from Mon, Jun 1? That date and later ones through Dec 31, 2099 go from " +
        "the schedule. Anything before or after stays. No one gets a message.",
    );
    expect(await patches(seen)[0]?.json()).toEqual({ ends_on: "2099-05-31" });
  });

  it("does nothing when the confirm is declined", async () => {
    vi.mocked(confirmDestructive).mockResolvedValueOnce(false);
    const seen = stubApi({ card: shalaOut(TEACHER), schedule, classes: [SERIES] });
    renderWith(card());
    await open();

    fireEvent.click(screen.getByRole("button", row));
    await waitFor(() => {
      expect(confirmDestructive).toHaveBeenCalled();
    });
    await act(() => Promise.resolve());

    expect(patches(seen)).toHaveLength(0);
    expect(screen.getByRole("heading", { name: "The whole class" })).toBeInTheDocument();
  });

  it("is not offered on a date that has already begun", async () => {
    stubApi({ card: shalaOut(TEACHER) }); // Mon 9 Nov 2026: past
    renderWith(card());
    await open();

    expect(screen.getByRole("button", { name: "✏️ Change the class…" })).toBeInTheDocument();
    expect(screen.queryByRole("button", row)).toBeNull();
  });

  it("says what to do when the date is the class's first, without a request", async () => {
    const first = { ...SERIES, starts_on: "2099-05-27" }; // a Wednesday; the first class is Mon 1 Jun
    const seen = stubApi({
      card: shalaOut(TEACHER),
      schedule,
      classes: [{ ...first, weekdays: [1] }],
    });
    renderWith(card());
    await open();

    fireEvent.click(screen.getByRole("button", row));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This is the class's first date. To remove the class, open “Change the class…” " +
        "and delete it there.",
    );
    expect(patches(seen)).toHaveLength(0);
  });

  it("says the same when the server finds the date to be the first", async () => {
    const seen = stubApi({
      card: shalaOut(TEACHER),
      schedule,
      classes: [SERIES],
      patch: () => json({ code: "invalid_class" }, 422),
    });
    renderWith(card());
    await open();

    fireEvent.click(screen.getByRole("button", row));

    expect(await screen.findByRole("alert")).toHaveTextContent("This is the class's first date.");
    expect(patches(seen)).toHaveLength(1);
  });

  // The class is read as it is now: someone else has just ended it before this date, and a
  // last date set from the old picture would run it beside its own successor.
  it("shows the current schedule, and writes nothing, when the class has changed meanwhile", async () => {
    const seen = stubApi({
      card: shalaOut(TEACHER),
      schedule,
      classes: [{ ...SERIES, ends_on: "2099-05-24" }],
    });
    renderWith(card());
    await open();

    fireEvent.click(screen.getByRole("button", row));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "This class has just changed or was removed.",
    );
    expect(patches(seen)).toHaveLength(0);
  });

  it("shows the current schedule when the write itself meets a class that is gone", async () => {
    stubApi({
      card: shalaOut(TEACHER),
      schedule,
      classes: [SERIES],
      patch: () => json({ code: "not_found" }, 404),
    });
    renderWith(card());
    await open();

    fireEvent.click(screen.getByRole("button", row));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "This class has just changed or was removed.",
    );
  });
});
