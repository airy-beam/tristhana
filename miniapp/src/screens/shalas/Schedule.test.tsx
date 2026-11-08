import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import ClassForm from "./ClassForm";
import ShalaScreen from "./ShalaScreen";

// SC-02 (spec §2, §4, §7): the schedule section of the shala card (zone label once, 🌙 and 😌
// day rows, a cancelled row with its reason, "your time" only when the viewer's offset
// differs), the moon policy select with its note (owner/manager), the Q109 day-off adoption,
// the occurrence sheet per role, and the class form (Mysore window preset "all but the day
// off", other types start empty, the Led hint). The API and the Telegram SDK are mocked.
// Assumed: `ClassForm({ shala, onDone })` in `./ClassForm`; the schedule lives on
// `ShalaScreen`; weekday chips are checkboxes named by the weekday.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  confirmDestructive: vi.fn(() => Promise.resolve(true)),
  openTelegramLink: vi.fn(),
}));

const SHALA = "00000000-0000-0000-0000-0000000000c1";
const CLASS = "00000000-0000-0000-0000-0000000000d1";
const ANNA = "00000000-0000-0000-0000-0000000000a1";
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

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Stub {
  card?: unknown;
  schedule?: unknown;
  dayOff?: number[] | null;
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
      if (path.startsWith(`/api/v1/shalas/${SHALA}/classes/`) && request.method === "PUT")
        return json(occurrence({ cancelled: "cancelled" }));
      if (path === `/api/v1/shalas/${SHALA}`) return json(stub.card ?? shalaOut(STUDENT));
      if (path === "/api/v1/moon/cities") return json(CITIES);
      if (path === "/api/v1/me/day-off") return json({ day_off: [6], practice_days: [] });
      if (path === "/api/v1/me")
        return json({
          id: "00000000-0000-0000-0000-000000000001",
          display_name: "Ash",
          locale: "en",
          timezone: "Asia/Almaty",
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
    const text = pageText();
    expect(text.match(/Almaty \(UTC\+5\)/g)).toHaveLength(1);
    expect(text).toContain("🌙 Moon day");
    expect(text).toContain("😌 Shala day off");
    expect(text).toContain("moon day"); // the cancelled Friday keeps its reason
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
});

describe("the class form", () => {
  const form = () => <ClassForm shala={shalaOut(OWNER) as never} onDone={vi.fn()} />;
  const weekday = (name: string) => screen.getByRole<HTMLInputElement>("checkbox", { name });

  it("presets Mysore to every day but the shala's day off, with an until time", async () => {
    stubApi();
    renderWith(form());

    await screen.findByRole("button", { name: "Mysore" });
    expect(weekday("Saturday").checked).toBe(false);
    for (const d of ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Sunday"])
      expect(weekday(d).checked).toBe(true);
    expect(screen.getByLabelText(/Until/)).toHaveAttribute("type", "time");
    expect(pageText()).toContain("Almaty (UTC+5)");
  });

  it("starts other types with no day ticked; Led shows its hint and minutes", async () => {
    stubApi();
    renderWith(form());
    fireEvent.click(await screen.findByRole("button", { name: "Led" }));

    for (const d of ["Monday", "Friday", "Sunday"]) expect(weekday(d).checked).toBe(false);
    expect(pageText()).toContain("Often Friday or Sunday");
    expect(screen.getByLabelText(/Length/)).toHaveAttribute("type", "number");

    fireEvent.click(screen.getByRole("button", { name: "Conference" }));
    expect(pageText()).not.toContain("Often Friday or Sunday");
  });

  it("refuses a window that ends before it starts, without a request", async () => {
    const seen = stubApi();
    renderWith(form());
    await screen.findByRole("button", { name: "Mysore" });

    fireEvent.change(screen.getByLabelText(/Start/), { target: { value: "09:00" } });
    fireEvent.change(screen.getByLabelText(/Until/), { target: { value: "08:00" } });
    fireEvent.submit(screen.getByLabelText(/Start/).closest("form") as HTMLFormElement);

    await screen.findByRole("alert");
    expect(calls(seen, "POST", `/api/v1/shalas/${SHALA}/classes`)).toHaveLength(0);
  });

  it("sends the Mysore window as minutes", async () => {
    const seen = stubApi();
    renderWith(form());
    await screen.findByRole("button", { name: "Mysore" });

    fireEvent.change(screen.getByLabelText(/Start/), { target: { value: "06:00" } });
    fireEvent.change(screen.getByLabelText(/Until/), { target: { value: "09:30" } });
    fireEvent.submit(screen.getByLabelText(/Start/).closest("form") as HTMLFormElement);

    await waitFor(() => {
      expect(calls(seen, "POST", `/api/v1/shalas/${SHALA}/classes`)).toHaveLength(1);
    });
    const body: unknown = await calls(seen, "POST", `/api/v1/shalas/${SHALA}/classes`)[0]?.json();
    expect(body).toMatchObject({
      type: "mysore",
      start: "06:00",
      minutes: 210,
      weekdays: [1, 2, 3, 4, 5, 7],
      every: 1,
    });
  });

  it("offers the zone select for online classes only", async () => {
    stubApi();
    renderWith(form());
    await screen.findByRole("button", { name: "Mysore" });

    expect(screen.queryByRole("combobox", { name: /Times in/ })).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /online/i }));
    const zone = await screen.findByRole<HTMLSelectElement>("combobox", { name: /Times in/ });
    expect(zone.value).toBe("almaty");
    expect(within(zone).getByText(/Berlin/)).toBeInTheDocument();
  });
});
