import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { Me } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import Links from "../settings/Links";
import Settings from "../settings/Settings";
import ShalaScreen from "./ShalaScreen";

// SC-01 (spec §2, §4, §7): the 🏛 Shalas part of 👥 Teachers and students, the create form
// (name 1–64, a listed city preselected with home_city, the online toggle, roles), the card
// per role, the staff role editor, delete with a native confirm, the zone label built here
// from the IANA zone, "🏛 Follow my shala" in the moon select, and cache invalidation.
// `ShalaScreen({ id, onBack })` is the card screen. The API and the Telegram SDK are mocked.

const telegram = vi.hoisted(() => ({
  confirmDestructive: vi.fn<(message: string, ok: string, cancel: string) => Promise<boolean>>(),
}));

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  confirmDestructive: telegram.confirmDestructive,
  openTelegramLink: vi.fn(),
}));

const ME: Me = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Ash",
  locale: "en",
  timezone: "Asia/Almaty",
  name_from_telegram: true,
  locale_from_telegram: true,
  hide_ladies: false,
  offer_check_in: true,
  home_city_chosen: true,
};
const SHALA = "00000000-0000-0000-0000-0000000000c1";
const ANNA = "00000000-0000-0000-0000-0000000000a1";
const BORIS = "00000000-0000-0000-0000-0000000000a2";
const TODAY = "2026-11-07";
const CITIES = [
  { slug: "mysuru", name_en: "Mysuru", name_ru: "Майсур", timezone: "Asia/Kolkata" },
  { slug: "almaty", name_en: "Almaty", name_ru: "Алматы", timezone: "Asia/Almaty" },
  { slug: "moscow", name_en: "Moscow", name_ru: "Москва", timezone: "Europe/Moscow" },
];

type Role = "admin" | "teacher" | "assistant" | "office";
interface MeIn {
  owner: boolean;
  roles: Role[];
  student: boolean;
  schedule?: boolean; // SC-02
}
const STAFF = [
  { id: ANNA, name: "Anna", owner: true, roles: ["teacher"] as Role[] },
  { id: BORIS, name: "Boris", owner: false, roles: ["teacher"] as Role[] },
];
const shalaOut = (me: MeIn, over: Record<string, unknown> = {}) => ({
  id: SHALA,
  name: "Ashtanga Almaty",
  city: { slug: "almaty", name: "Almaty" },
  zone: "Asia/Almaty",
  online: false,
  moon_city: null,
  staff: STAFF,
  students_total: me.student ? null : 34,
  days_off: null, // SC-02
  moon_policy: "closed",
  me: { schedule: false, ...me },
  ...over,
});
const OWNER: MeIn = { owner: true, roles: ["teacher"], student: false };
const ADMIN: MeIn = { owner: false, roles: ["admin"], student: false };
const TEACHER: MeIn = { owner: false, roles: ["teacher"], student: false };
const STUDENT: MeIn = { owner: false, roles: [], student: true };
const MINE = [
  {
    id: SHALA,
    name: "Ashtanga Almaty",
    city: "almaty",
    online: false,
    side: "staff",
    owner: true,
    roles: ["teacher"],
  },
];

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Stub {
  mine?: unknown[];
  card?: unknown;
  location?: unknown;
  create?: (body: unknown) => Response;
}

function stubApi(stub: Stub = {}): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      await Promise.resolve();
      seen.push(request.clone());
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/me/shalas") return json(stub.mine ?? []);
      if (path === "/api/v1/shalas" && request.method === "POST") {
        const body: unknown = await request.json();
        return stub.create?.(body) ?? json(shalaOut(OWNER), 201);
      }
      if (path === `/api/v1/shalas/${SHALA}` && request.method === "DELETE")
        return new Response(null, { status: 204 });
      if (path.startsWith(`/api/v1/shalas/${SHALA}/staff/`) && request.method === "PUT")
        return json(stub.card ?? shalaOut(OWNER));
      if (path === `/api/v1/shalas/${SHALA}`) return json(stub.card ?? shalaOut(OWNER));
      if (path === `/api/v1/shalas/${SHALA}/schedule`)
        return json({
          zone: "Asia/Almaty",
          city: "almaty",
          moon_policy: "closed",
          days_off: null,
          days: [],
          occurrences: [],
          closures: [],
        }); // SC-02
      if (path === "/api/v1/me/links") return json({ teachers: [], students: [] });
      if (path === "/api/v1/me/invite") return json({ url: "https://t.me/x?start=t_a", qr: "" });
      if (path === "/api/v1/moon/cities") return json(CITIES);
      if (path === "/api/v1/me/moon-days")
        return json({
          location: stub.location ?? {
            slug: "mysuru",
            explicit: false,
            source: "default",
            follow_chosen: false,
            teacher: null,
            shared: null,
            shala: null,
          },
          today: TODAY,
          days: [],
        });
      if (path === "/api/v1/me/notification-settings")
        return json({
          moon: { offsets: [1, 7], at: "19:00:00" },
          quiet: { start: "22:00:00", end: "07:00:00" },
          daily_cap: 3,
          practice: { on: null, at: "10:00:00", days: [1, 2, 3, 4, 5, 7] },
          timezone: "Asia/Almaty",
        });
      if (path === "/api/v1/me") return json({ ...ME, day_off: [6] });
      return json({});
    }),
  );
  return seen;
}

function renderWith(node: React.ReactNode, locale: Locale = "en", client?: QueryClient) {
  const queries = client ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
const card = (id = SHALA) => <ShalaScreen id={id} onBack={vi.fn()} />;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("the Shalas part of Teachers and students", () => {
  it("lists my shalas, then Create a shala", async () => {
    stubApi({ mine: MINE });

    renderWith(<Links onBack={vi.fn()} onStudents={vi.fn()} />);

    await screen.findByText(/Ashtanga Almaty/);
    expect(screen.getByRole("button", { name: "🏛 Create a shala" })).toBeInTheDocument();
  });

  it("offers Create a shala with no shalas", async () => {
    stubApi({ mine: [] });

    renderWith(<Links onBack={vi.fn()} onStudents={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "🏛 Create a shala" })).toBeInTheDocument();
  });
});

describe("the create form", () => {
  async function openForm() {
    renderWith(<Links onBack={vi.fn()} onStudents={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "🏛 Create a shala" }));
    return screen.findByRole("textbox");
  }

  it("refuses a blank name without a request", async () => {
    const seen = stubApi();
    const name = await openForm();

    fireEvent.change(name, { target: { value: "   " } });
    fireEvent.submit(name.closest("form") as HTMLFormElement);

    await waitFor(() => {
      expect(calls(seen, "POST", "/api/v1/shalas")).toHaveLength(0);
    });
  });

  it("caps the name at 64 characters", async () => {
    stubApi();
    const name = await openForm();

    expect(name).toHaveAttribute("maxLength", "64");
  });

  it("lists the cities, preselects the home city and sends the form", async () => {
    const seen = stubApi();
    const name = await openForm();
    const city = await screen.findByRole<HTMLSelectElement>("combobox");
    await waitFor(() => {
      expect(Array.from(city.options).map((o) => o.value)).toEqual(
        expect.arrayContaining(["mysuru", "almaty", "moscow"]),
      );
    });

    fireEvent.change(name, { target: { value: "Ashtanga Almaty" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /🌐 Online classes only/ }));
    fireEvent.submit(name.closest("form") as HTMLFormElement);

    await waitFor(() => {
      expect(calls(seen, "POST", "/api/v1/shalas")).toHaveLength(1);
    });
    const body: unknown = await calls(seen, "POST", "/api/v1/shalas")[0]?.json();
    expect(body).toMatchObject({ name: "Ashtanga Almaty", online: true, roles: ["teacher"] });
  });

  it("shows the caps error from a 409", async () => {
    stubApi({ create: () => json({ code: "shala_caps" }, 409) });
    const name = await openForm();

    fireEvent.change(name, { target: { value: "One more" } });
    fireEvent.submit(name.closest("form") as HTMLFormElement);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});

describe("the shala card", () => {
  it("shows the zone label from the IANA zone and the moon city", async () => {
    stubApi({ card: shalaOut(STUDENT) });

    renderWith(card());

    await screen.findByText(/Ashtanga Almaty/);
    expect(pageText()).toContain("Almaty (UTC+5)");
    expect(pageText()).toContain("🌙 Moon days: 📍 Almaty");
  });

  it.each([
    ["owner", OWNER, true, true, false],
    ["admin", ADMIN, true, true, true],
    ["teacher", TEACHER, true, false, true],
    ["student", STUDENT, false, false, true],
  ] as const)("per role: %s", async (_, me, students, inviteStaff, leave) => {
    stubApi({ card: shalaOut(me) });

    renderWith(card());

    await screen.findByText(/Ashtanga Almaty/);
    expect(!!screen.queryByRole("button", { name: /👥 Students \(34\)/ })).toBe(students);
    expect(!!screen.queryByRole("button", { name: "➕ Invite students" })).toBe(students);
    expect(!!screen.queryByRole("button", { name: "➕ Invite staff" })).toBe(inviteStaff);
    expect(!!screen.queryByRole("button", { name: /^Leave/ })).toBe(leave);
  });

  it("never shows other students to a student", async () => {
    stubApi({ card: shalaOut(STUDENT) });

    renderWith(card());

    await screen.findByText(/Ashtanga Almaty/);
    expect(pageText()).not.toMatch(/Students \(/);
  });

  it("lets the owner edit a staff member's roles and shows the server's answer", async () => {
    const after = shalaOut(OWNER, {
      staff: [STAFF[0], { ...STAFF[1], roles: ["teacher", "office"] }],
    });
    const seen = stubApi({ card: shalaOut(OWNER) });
    renderWith(card());
    await screen.findByText(/Boris/);
    stubApi({ card: after });

    fireEvent.click(screen.getByRole("button", { name: /Boris/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Front desk" }));
    fireEvent.click(screen.getByRole("button", { name: /Save|Сохранить/ }));

    await waitFor(() => {
      expect(pageText()).toContain("Front desk");
    });
    expect(seen).toBeDefined();
  });

  it("offers no Manager role to an admin", async () => {
    stubApi({ card: shalaOut(ADMIN) });
    renderWith(card());
    await screen.findByText(/Boris/);

    fireEvent.click(screen.getByRole("button", { name: /Boris/ }));

    await screen.findByRole("checkbox", { name: "Teacher" });
    expect(screen.queryByRole("checkbox", { name: "Manager" })).toBeNull();
  });

  it("deletes only after the native confirm", async () => {
    telegram.confirmDestructive.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    const seen = stubApi({ card: shalaOut(OWNER) });
    renderWith(card());
    await screen.findByText(/Ashtanga Almaty/);

    fireEvent.click(screen.getByRole("button", { name: /Delete/ }));
    await waitFor(() => {
      expect(telegram.confirmDestructive).toHaveBeenCalledTimes(1);
    });
    expect(calls(seen, "DELETE", `/api/v1/shalas/${SHALA}`)).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: /Delete/ }));
    await waitFor(() => {
      expect(calls(seen, "DELETE", `/api/v1/shalas/${SHALA}`)).toHaveLength(1);
    });
  });

  it("lets a manager edit the moon city; null means the shala's city", async () => {
    const seen = stubApi({ card: shalaOut(ADMIN) });
    renderWith(card());
    fireEvent.click(await screen.findByRole("button", { name: "✏️ Edit the shala" }));
    const moon = await screen.findByRole<HTMLSelectElement>("combobox", {
      name: "City for the shala's moon days",
    });
    await waitFor(() => {
      expect(moon.options.length).toBeGreaterThan(1);
    });

    fireEvent.change(moon, { target: { value: "mysuru" } });
    fireEvent.submit(moon.closest("form") as HTMLFormElement);

    await waitFor(() => {
      expect(calls(seen, "PATCH", `/api/v1/shalas/${SHALA}`)).toHaveLength(1);
    });
    const body: unknown = await calls(seen, "PATCH", `/api/v1/shalas/${SHALA}`)[0]?.json();
    expect(body).toMatchObject({ name: "Ashtanga Almaty", moon_city: "mysuru" });
  });

  it("offers no edit to a teacher or a student", async () => {
    for (const me of [TEACHER, STUDENT]) {
      stubApi({ card: shalaOut(me) });
      const { unmount } = renderWith(card());
      await screen.findByText(/Ashtanga Almaty/);
      expect(screen.queryByRole("button", { name: "✏️ Edit the shala" })).toBeNull();
      unmount();
    }
  });

  it("has no delete for an admin", async () => {
    stubApi({ card: shalaOut(ADMIN) });
    renderWith(card());
    await screen.findByText(/Ashtanga Almaty/);

    expect(screen.queryByRole("button", { name: /Delete/ })).toBeNull();
  });

  it("refetches my shalas and the moon days after leaving", async () => {
    telegram.confirmDestructive.mockResolvedValue(true);
    const seen = stubApi({ card: shalaOut(STUDENT) });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWith(card(), "en", client);
    await screen.findByText(/Ashtanga Almaty/);
    const invalidate = vi.spyOn(client, "invalidateQueries");

    fireEvent.click(screen.getByRole("button", { name: /^Leave/ }));

    await waitFor(() => {
      expect(calls(seen, "DELETE", `/api/v1/shalas/${SHALA}/students/${ME.id}`)).toHaveLength(1);
    });
    await waitFor(() => {
      expect(invalidate).toHaveBeenCalled();
    });
  });
});

describe("Follow my shala in Settings", () => {
  const settings = (locale: Locale = "en") => (
    <Settings me={{ ...ME, locale }} onBack={vi.fn()} onTour={vi.fn()} onLinks={vi.fn()} />
  );
  const shalaLocation = {
    slug: "moscow",
    explicit: false,
    source: "shala",
    follow_chosen: false,
    teacher: null,
    shared: null,
    shala: { id: SHALA, name: "Moscow Shala", staff: false },
  };

  it("is an option only with a shala, and sends follow: shala", async () => {
    const seen = stubApi({ location: shalaLocation });
    renderWith(settings());
    const select = await screen.findByRole<HTMLSelectElement>("combobox", {
      name: "City for the calendar",
    });
    await waitFor(() => {
      expect(Array.from(select.options).map((o) => plain(o.textContent))).toContain(
        "🏛 Follow my shala (Moscow Shala)",
      );
    });

    const option = Array.from(select.options).find((o) => o.textContent.includes("shala"));
    fireEvent.change(select, { target: { value: option?.value } });

    await waitFor(() => {
      expect(calls(seen, "PUT", "/api/v1/me/moon-location")).toHaveLength(1);
    });
    const body: unknown = await calls(seen, "PUT", "/api/v1/me/moon-location")[0]?.json();
    expect(body).toEqual({ slug: null, follow: "shala" });
  });

  it("says the source", async () => {
    stubApi({ location: shalaLocation });

    renderWith(settings());

    await waitFor(() => {
      expect(pageText()).toContain(
        "🏛 Same as your shala, Moscow Shala. You can choose another city.",
      );
    });
  });

  it("has no shala option without a shala", async () => {
    stubApi();
    renderWith(settings());
    const select = await screen.findByRole<HTMLSelectElement>("combobox", {
      name: "City for the calendar",
    });

    await waitFor(() => {
      expect(select.options.length).toBeGreaterThan(1);
    });
    expect(Array.from(select.options).some((o) => o.textContent.includes("shala"))).toBe(false);
  });
});
