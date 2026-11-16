import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import { useBackButton } from "../../telegram";
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
// the edit form; "Tell students…" follows a cancel (Q338).

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
  /** The saved class series (`GET …/classes`). */
  classes?: unknown[];
  /** The answer to a `PATCH` of a class; the merged class unless given. */
  patch?: () => Response;
  dayOff?: number[] | null;
  /** My own zone (the viewer's); Almaty, the shala's, unless given. */
  timezone?: string;
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
        return json(occurrence({ cancelled: "cancelled" }));
      if (path === `/api/v1/shalas/${SHALA}/classes/${CLASS}` && request.method === "PATCH")
        return stub.patch?.() ?? json({ ...SERIES, ...((await request.json()) as object) });
      if (path === `/api/v1/shalas/${SHALA}/classes/${CLASS}` && request.method === "DELETE")
        return new Response(null, { status: 204 });
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
          timezone: stub.timezone ?? "Asia/Almaty",
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
    expect(text.match(/shala time: Almaty/g)).toHaveLength(1);
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
    expect(plain(nav.textContent)).toMatch(/^◀\w{3}, \w{3} \d+ – \w{3}, \w{3} \d+▶$/);
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
    expect(screen.queryByRole("button", { name: /Cancel this class/ })).toBeNull();
  });

  it("lets a teacher cancel, and offers Hold anyway only on an auto-cancelled one", async () => {
    const seen = stubApi({ card: shalaOut(TEACHER) });
    renderWith(card());

    const rows = await screen.findAllByText(/06:00–09:30/);
    fireEvent.click(rows[0] as HTMLElement);
    expect(screen.queryByRole("button", { name: /Hold anyway/ })).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: "❌ Cancel this class" }));

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
    // Nothing else to fill in: no title, teacher, dates or online on the first screen.
    expect(screen.getAllByRole("group")).toHaveLength(2);
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
    fireEvent.click(screen.getByRole("button", { name: "One date only" }));

    expect(screen.queryByRole("group", { name: "Repeats on" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-12-05" } });
    expect(screen.getByRole("button", { name: "Repeat weekly" })).toBeInTheDocument();
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

  it("offers the length as chips, and any other length as an end time", async () => {
    const seen = stubApi();
    renderWith(form());
    fireEvent.click(await screen.findByRole("button", { name: "Led" }));
    fireEvent.click(chip("Friday"));
    fireEvent.click(more());

    const length = screen.getByRole("group", { name: "Length" });
    expect(
      within(length)
        .getAllByRole("button")
        .map((b) => plain(b.textContent)),
    ).toEqual(["60 min", "75 min", "90 min", "120 min", "Other"]);
    expect(within(length).getByRole("button", { name: "90 min" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.queryByLabelText("Ends at")).toBeNull();
    fireEvent.click(within(length).getByRole("button", { name: "75 min" }));
    // Changing the start keeps the length.
    fireEvent.change(screen.getByLabelText("Start, Almaty"), { target: { value: "18:30" } });
    fireEvent.click(within(length).getByRole("button", { name: "Other" }));
    const ends = screen.getByLabelText<HTMLInputElement>("Ends at");
    expect(ends.value).toBe("19:45");
    fireEvent.change(ends, { target: { value: "20:15" } });
    save();

    await waitFor(() => {
      expect(posts(seen)).toHaveLength(1);
    });
    expect(await posts(seen)[0]?.json()).toMatchObject({ start: "18:30", minutes: 105 });
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
    expect(screen.getByRole("button", { name: "Ещё настройки" })).toBeInTheDocument();
  });
});

describe("changing a class (ADR-0048)", () => {
  const MONDAY = "2099-06-01"; // the date that was tapped: far ahead, so never before today
  const edit = (onDone = vi.fn(), date = MONDAY) => (
    <ClassForm shala={shalaOut(OWNER) as never} edit={{ classId: CLASS, date }} onDone={onDone} />
  );
  const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Almaty" }).format();

  it("fills the form from the saved class and names the date the change applies from", async () => {
    stubApi({ classes: [SERIES] });
    renderWith(edit());

    expect(
      await screen.findByRole("heading", { level: 1, name: "Change the class" }),
    ).toBeVisible();
    const applies = await screen.findByLabelText<HTMLInputElement>("Changes apply from");
    expect(applies.value).toBe(MONDAY);
    expect(applies).toHaveAttribute("min", today());
    expect(applies).toHaveAccessibleDescription("Earlier dates stay as they were.");
    expect(pressed("Mysore")).toBe(true);
    expect(pressed("Saturday")).toBe(false);
    // A class keeps its kind: no switch to one date, and no first date to rewrite.
    expect(screen.queryByRole("button", { name: "One date only" })).toBeNull();
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
    renderWith(edit(vi.fn(), "2026-01-05"));
    const applies = await screen.findByLabelText<HTMLInputElement>("Changes apply from");
    expect(applies.value).toBe(today());
    fireEvent.change(applies, { target: { value: "2020-01-01" } }); // typed past the picker
    fireEvent.click(more());
    fireEvent.change(screen.getByLabelText(/Title/), { target: { value: "Full Primary" } });
    save();

    await waitFor(() => {
      expect(patches(seen)).toHaveLength(1);
    });
    expect(await patches(seen)[0]?.json()).toEqual({ title: "Full Primary", from: today() });
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

  it("deletes the class from the form, after the confirm", async () => {
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
    expect(screen.getByRole("button", { name: "❌ Cancel this class" })).toBeInTheDocument();
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
    expect(await screen.findByLabelText("Changes apply from")).toBeInTheDocument();
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

  it("offers Tell students only after a cancel, with the text filled in", async () => {
    const seen = stubApi({ card: shalaOut(MANAGER) });
    renderWith(card());
    await openSheet();

    expect(screen.queryByRole("button", { name: "📣 Tell students…" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "❌ Cancel this class" }));
    await waitFor(() => {
      expect(calls(seen, "PUT", putPath)).toHaveLength(1);
    });
    fireEvent.click(await screen.findByRole("button", { name: "📣 Tell students…" }));

    // The compose screen, with a text a reader in any zone can use: day, time, zone, offset.
    const text = await screen.findByRole<HTMLTextAreaElement>("textbox", { name: "Text" });
    expect(text.value).toBe("Class cancelled: Mysore, Mon, Nov 9, 06:00 Almaty (UTC+5).");
    // Nothing went out by the cancel or by opening the screen.
    expect(calls(seen, "POST", "/api/v1/me/announcements")).toHaveLength(0);
  });

  it("does not offer it for a 1:1, or to someone who may not announce", async () => {
    const one = { ...SCHEDULE, occurrences: [occurrence({ type: "private" })] };
    const seen = stubApi({ card: shalaOut(MANAGER), schedule: one });
    const first = renderWith(card());
    await openSheet();
    fireEvent.click(screen.getByRole("button", { name: "❌ Cancel this class" }));
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
    fireEvent.click(screen.getByRole("button", { name: "❌ Cancel this class" }));
    await waitFor(() => {
      expect(calls(again, "PUT", putPath)).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "The whole class" })).toBeNull();
    });
    expect(screen.queryByRole("button", { name: "📣 Tell students…" })).toBeNull();
  });
});
