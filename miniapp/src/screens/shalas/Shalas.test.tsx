import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type { Me } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import More from "../settings/pages/More";
import { confirmAction, useBackButton } from "../../telegram";
import { addDays, dayName, todayIn } from "./scheduleText";
import ShalaScreen from "./ShalaScreen";
import ShalaTab from "./ShalaTab";

// SC-01 (spec §2, §4, §7): my shalas on the Shala tab (a row each; UI-06 stage 4B), the create form
// (UI-06 stage 4: two fields, name 1–64 and a listed city preselected with home_city; the
// owner starts as its teacher and changes the rest on the card, their own roles too), the
// owner's setup list (add a class, invite students, invite teachers), the card
// per role, the staff role editor, delete with a native confirm, the zone label built here
// from the IANA zone, "🏛 Follow my shala" in the moon select, and cache invalidation.
// `ShalaScreen({ id, onBack })` is the card screen. The API and the Telegram SDK are mocked.

const telegram = vi.hoisted(() => ({
  confirmDestructive: vi.fn<(message: string, ok: string, cancel: string) => Promise<boolean>>(),
  openLink: vi.fn<(url: string) => void>(),
}));

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  confirmDestructive: telegram.confirmDestructive,
  confirmAction: vi.fn(() => Promise.resolve(false)),
  openTelegramLink: vi.fn(),
  openLink: telegram.openLink,
  useMainButton: vi.fn(),
  mainButtonAvailable: vi.fn(() => false),
  enableClosingConfirmation: vi.fn(),
  disableClosingConfirmation: vi.fn(),
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
const CLASS_ID = "00000000-0000-0000-0000-0000000000d1";
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
  announce?: boolean; // NT-03
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
const OFFICE: MeIn = { owner: false, roles: ["office"], student: false };
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
  /** My account's home city. */
  home?: unknown;
  /** UI-06 stage 4B: who I can pick here, read again after each write. */
  choices?: () => unknown;
  /** What an ask comes to. */
  ask?: () => Response;
  /** The shala's saved class series (`GET …/classes`, UI-06 stage 6); none unless given. */
  classes?: unknown[];
  /** My account's language; English unless given. */
  locale?: Locale;
  /** The shala's students page (staff); none unless given. */
  students?: { id: string; name: string | null }[];
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
      if (path === `/api/v1/shalas/${SHALA}/teacher-choices`)
        return json(stub.choices?.() ?? { offer: [], waiting: [] });
      if (path === "/api/v1/me/teacher-requests" && request.method === "POST")
        return stub.ask?.() ?? json({ result: "created" });
      if (path.startsWith("/api/v1/me/teacher-requests/") && request.method === "DELETE")
        return new Response(null, { status: 204 });
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
      if (path === `/api/v1/shalas/${SHALA}/students`) {
        const students = stub.students ?? [];
        return json({ students, total: students.length });
      }
      if (path === `/api/v1/shalas/${SHALA}/join-link`)
        return json({ url: "https://t.me/x?start=s_a", qr: "data:image/png;base64,AA==" });
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
      if (path === `/api/v1/shalas/${SHALA}/staff-invites`)
        return json({ url: "https://t.me/x?start=i_a", qr: "data:image/png;base64,AA==" });
      if (path === `/api/v1/shalas/${SHALA}/classes` && request.method === "POST")
        return json({ id: CLASS_ID, rrule: null, ...((await request.json()) as object) }, 201);
      if (path === `/api/v1/shalas/${SHALA}/classes`) return json(stub.classes ?? []);
      if (path === "/api/v1/me/announcements/sent") return json([]); // NT-03
      if (path === "/api/v1/me")
        return json({
          ...ME,
          locale: stub.locale ?? ME.locale,
          day_off: [6],
          home_city: stub.home ?? null,
        });
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

describe("my shalas on the Shala tab", () => {
  // UI-06 stage 4B: a row per shala (no card title), and creating one is the group's
  // "Shala and classes", last.
  it("lists my shalas, then the group's Shala and classes", async () => {
    stubApi({ mine: MINE });

    renderWith(<ShalaTab onSchedule={vi.fn()} onStudents={vi.fn()} />);

    const row = await screen.findByRole("button", { name: /Ashtanga Almaty/ });
    const create = screen.getByRole("button", { name: "Shala and classes" });
    expect(row.compareDocumentPosition(create)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(screen.queryByRole("heading", { name: "🏛 Shalas" })).toBeNull();
    expect(screen.queryByRole("button", { name: "🏛 Create a shala" })).toBeNull();
  });

  // UI-06 stage 2: with nobody on the lists and no shala there are no empty cards; the quiet
  // "Shala and classes" start opens the form under it.
  it("with no shalas and nobody on the lists, Shala and classes leads to the form", async () => {
    stubApi({ mine: [] });

    renderWith(<ShalaTab onSchedule={vi.fn()} onStudents={vi.fn()} />);
    const start = await screen.findByRole("button", { name: "Shala and classes" });
    fireEvent.click(start);

    const name = await screen.findByRole("textbox");
    expect(name).toHaveFocus();
    expect(start).toHaveAttribute("aria-expanded", "true");
    expect(name.closest("section.card")).toBe(start.closest("section.card"));
  });
});

describe("the create form", () => {
  /** Someone with nobody on the lists yet: the quiet start opens the form. */
  async function openForm() {
    renderWith(<ShalaTab onSchedule={vi.fn()} onStudents={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Shala and classes" }));
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

  // UI-06 stage 4: a name and a city, then Create. Nothing else to decide here.
  it("has two fields: the name, and the city preselected with my home city", async () => {
    const seen = stubApi({ home: CITIES[1] });
    const name = await openForm();
    const city = await screen.findByRole<HTMLSelectElement>("combobox", { name: "City" });
    await waitFor(() => {
      expect(Array.from(city.options).map((o) => o.value)).toEqual(["mysuru", "almaty", "moscow"]);
    });
    expect(name).toHaveAccessibleName("Name");
    expect(city.value).toBe("almaty");
    expect(screen.queryByRole("checkbox")).toBeNull(); // no online toggle, no roles
    expect(screen.getAllByRole("combobox")).toHaveLength(1);

    fireEvent.change(name, { target: { value: "Ashtanga Almaty" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(calls(seen, "POST", "/api/v1/shalas")).toHaveLength(1);
    });
    // The owner starts as its teacher; online-only and the roles are changed on the card.
    expect(await calls(seen, "POST", "/api/v1/shalas")[0]?.json()).toEqual({
      name: "Ashtanga Almaty",
      city: "almaty",
      online: false,
      roles: ["teacher"],
    });
  });

  it("says what is wrong with a blank name, at the field", async () => {
    stubApi();
    const name = await openForm();

    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The shala needs a name");
    expect(name).toHaveAttribute("aria-invalid", "true");
    expect(name).toHaveFocus();
  });

  // UI-06: the bot's "Create a shala" button opens the app here (`?open=new-shala`).
  it("starts open with the name focused when asked to (create)", async () => {
    stubApi({ mine: MINE });

    renderWith(<ShalaTab start="create" onSchedule={vi.fn()} onStudents={vi.fn()} />);

    expect(await screen.findByRole("textbox")).toHaveFocus();
    expect(screen.getByRole("button", { name: "Shala and classes" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  // UI-06 stage 4B: one row opens it, from a start or a tap, and either way it is to type in.
  it("opened by its row, it is ready to type too; a second tap closes it", async () => {
    stubApi({ mine: MINE });
    renderWith(<ShalaTab onSchedule={vi.fn()} onStudents={vi.fn()} />);
    const row = await screen.findByRole("button", { name: "Shala and classes" });

    fireEvent.click(row);

    expect(await screen.findByRole("textbox")).toHaveFocus();
    fireEvent.click(row);
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("opens only once: back from the new shala's card the form is closed", async () => {
    stubApi();
    renderWith(<ShalaTab start="create" onSchedule={vi.fn()} onStudents={vi.fn()} />);
    const name = await screen.findByRole("textbox");
    fireEvent.change(name, { target: { value: "Ashtanga Almaty" } });
    fireEvent.submit(name.closest("form") as HTMLFormElement);
    await screen.findByRole("button", { name: "➕ Invite staff" }); // the card

    act(() => {
      vi.mocked(useBackButton).mock.lastCall?.[0]();
    });

    expect(await screen.findByRole("button", { name: "Shala and classes" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByRole("textbox")).toBeNull();
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
    // The shala's zone is my own: its place, no offset (ADR-0044).
    await waitFor(() => {
      expect(pageText()).not.toContain("UTC+5");
    });
    // UI-06 stage 5: no "shala time" in my own zone; the place alone, as in the bot.
    expect(screen.getByText((t) => plain(t) === "📍 Almaty")).toBeInTheDocument();
    expect(pageText()).not.toContain("shala time");
    // C15 (UI-06 stage 6): one moon line, the policy included, as the bot's card has it.
    expect(pageText()).toContain("🌙 Moon days (📍 Almaty): shala closed");
    expect(pageText()).not.toContain("🌙 Moon days: ");
  });

  it.each([
    ["open", "🌙 Moon days (📍 Almaty): classes as usual"],
    ["pranayama", "🌙 Moon days (📍 Almaty): pranayama, chanting and talks only"],
  ])("names the moon policy %s on the same line", async (policy, line) => {
    stubApi({ card: shalaOut(STUDENT, { moon_policy: policy }) });

    renderWith(card());

    await screen.findByText(/Ashtanga Almaty/);
    await waitFor(() => {
      expect(screen.getByText((t) => plain(t) === line)).toBeInTheDocument();
    });
  });

  it("says in one line whom the moon calendar is for, to those who set it", async () => {
    stubApi({ card: shalaOut(OWNER) });

    renderWith(card());

    await screen.findByText(
      "🌙 Staff and students follow the shala's moon days unless they chose their own city.",
    );
  });

  // C14 (UI-06 stage 6): what each role can do, under it, as `application/policies.py` allows.
  const HINTS = {
    Teacher:
      "Classes and schedule, attendance, announcements, the student list; students can pick them as their teacher.",
    Assistant: "Attendance and the student list; not the schedule or announcements.",
    "Front desk":
      "Classes and schedule, attendance, announcements, the student list; can remove a student from the shala; not the shala's settings or roles.",
    Manager: "Everything except deleting the shala and managing other managers.",
  } as const;

  it("the staff invite picker says what each role can do", async () => {
    stubApi({ card: shalaOut(OWNER) });
    renderWith(card());
    await screen.findByText(/Ashtanga Almaty/);

    fireEvent.click(await screen.findByRole("button", { name: "➕ Invite staff" }));

    for (const [role, hint] of Object.entries(HINTS)) {
      expect(await screen.findByRole("button", { name: role })).toHaveAccessibleDescription(hint);
    }
  });

  it("the role editor says what each role it offers can do", async () => {
    stubApi({ card: shalaOut(ADMIN) });
    renderWith(card());
    await screen.findByText(/Boris/);

    fireEvent.click(screen.getByRole("button", { name: /Boris/ }));

    for (const role of ["Teacher", "Assistant", "Front desk"] as const) {
      expect(await screen.findByRole("checkbox", { name: role })).toHaveAccessibleDescription(
        HINTS[role],
      );
    }
    expect(screen.queryByText(HINTS.Manager)).toBeNull(); // a manager can't make a manager
  });

  // C3 (UI-06 stage 6): staff who read the names learn whose students they are.
  const ASSISTANT: MeIn = { owner: false, roles: ["assistant"], student: false };
  const YOURS =
    "These are the shala's students. They show up in 👥 My students once they pick you as their teacher or open your own link (➕ Invite my students).";
  const SEND =
    "These are the shala's students. To have students of your own, send them your own link (➕ Invite my students).";
  it.each([
    ["a teacher", TEACHER, YOURS],
    ["an assistant", ASSISTANT, SEND],
    ["the front desk", OFFICE, null],
  ])("the students list for %s", async (_, me, line) => {
    const told = line !== null;
    stubApi({ card: shalaOut(me), students: [{ id: BORIS, name: "Bea" }] });
    const onInvite = vi.fn();
    renderWith(<ShalaScreen id={SHALA} onBack={vi.fn()} onInvite={onInvite} />);
    await screen.findByText(/Ashtanga Almaty/);

    fireEvent.click(screen.getByRole("button", { name: /👥 Students/ }));
    await screen.findByText("Bea");

    if (line) expect(screen.getByText(line)).toBeVisible();
    expect(pageText()).not.toContain(line === YOURS ? SEND : YOURS);
    const invite = screen.queryByRole("button", { name: "➕ Invite my students" });
    expect(!!invite).toBe(told);
    if (invite) {
      fireEvent.click(invite);
      expect(onInvite).toHaveBeenCalledOnce();
    }
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
    expect(!!screen.queryByRole("button", { name: "➕ Invite students to the shala" })).toBe(
      students,
    );
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

  // Q338: Teacher is set without asking when the shala is created, so the owner can change it.
  it("lets the owner change their own roles from their row, never to Manager", async () => {
    const after = shalaOut(
      { ...OWNER, roles: ["assistant"] },
      { staff: [{ ...STAFF[0], roles: ["assistant"] }, STAFF[1]] },
    );
    const seen = stubApi({ card: shalaOut(OWNER) });
    renderWith(card());
    const mine = await screen.findByRole("button", { name: "Anna" });
    expect(mine).toHaveAccessibleDescription("Owner, Teacher");
    const put = stubApi({ card: after });

    fireEvent.click(mine);
    expect(await screen.findByText("My roles in the shala")).toBeInTheDocument();
    expect(
      screen
        .getAllByRole<HTMLInputElement>("checkbox")
        .map((c) => [c.labels?.[0]?.textContent, c.checked]),
    ).toEqual([
      ["Teacher", true],
      ["Assistant", false],
      ["Front desk", false],
    ]);
    expect(screen.queryByRole("button", { name: "Remove…" })).toBeNull(); // nobody removes an owner
    fireEvent.click(screen.getByRole("checkbox", { name: "Teacher" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Assistant" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(calls(put, "PUT", `/api/v1/shalas/${SHALA}/staff/${ANNA}`)).toHaveLength(1);
    });
    expect(await calls(put, "PUT", `/api/v1/shalas/${SHALA}/staff/${ANNA}`)[0]?.json()).toEqual({
      roles: ["assistant"],
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Anna" })).toHaveAccessibleDescription(
        "Owner, Assistant",
      );
    });
    expect(seen).toBeDefined();
  });

  it("gives a manager no way into the owner's roles", async () => {
    stubApi({ card: shalaOut(ADMIN) });
    renderWith(card());
    await screen.findByText("Boris");

    expect(screen.queryByRole("button", { name: "Anna" })).toBeNull();
    expect(screen.getByText("Anna")).toBeInTheDocument();
  });

  it("offers no Manager role to an admin", async () => {
    stubApi({ card: shalaOut(ADMIN) });
    renderWith(card());
    await screen.findByText(/Boris/);

    fireEvent.click(screen.getByRole("button", { name: /Boris/ }));

    await screen.findByRole("checkbox", { name: "Teacher" });
    expect(screen.queryByRole("checkbox", { name: "Manager" })).toBeNull();
  });

  it.each([
    ["a teacher", TEACHER, true],
    ["a student", STUDENT, false],
  ] as const)("leaving as %s says whether their own students stay", async (_, me, says) => {
    telegram.confirmDestructive.mockResolvedValueOnce(false);
    stubApi({ card: shalaOut(me) });
    renderWith(card());
    await screen.findByText(/Ashtanga Almaty/);

    fireEvent.click(screen.getByRole("button", { name: /^Leave/ }));

    await waitFor(() => {
      expect(telegram.confirmDestructive).toHaveBeenCalledTimes(1);
    });
    const [ask] = telegram.confirmDestructive.mock.calls[0] ?? [""];
    expect(ask).toMatch(/^Leave .*No one gets a message, and your log stays as it is\./);
    expect(ask.endsWith(" Your own students stay on your list.")).toBe(says);
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

// UI-06 (review): Today's next step lands where the work is, not on the card's first row.
describe("opened for one thing", () => {
  const scrolled = vi.fn();
  beforeEach(() => {
    Element.prototype.scrollIntoView = scrolled;
  });
  afterEach(() => {
    delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
  });
  const OWNS = shalaOut({ ...OWNER, schedule: true });
  const form = () => screen.findByRole("button", { name: "Save the class" });

  // UI-06 stage 4: the form is a layer of its own, so there is nothing to scroll to.
  it("class: the class form is open, over the card", async () => {
    stubApi({ card: OWNS });
    renderWith(<ShalaScreen id={SHALA} onBack={vi.fn()} open="class" />);

    expect(await form()).toBeVisible();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("New class");
    expect(screen.queryByRole("button", { name: "➕ Add a class" })).toBeNull();
    expect(scrolled).not.toHaveBeenCalled();
  });

  it("class: Back from the form focuses the card's title (nothing on the card had it)", async () => {
    stubApi({ card: OWNS });
    renderWith(<ShalaScreen id={SHALA} onBack={vi.fn()} open="class" />);
    await form();
    act(() => {
      vi.mocked(useBackButton).mock.lastCall?.[0]();
    });

    const title = await screen.findByRole("heading", { level: 1, name: /Ashtanga Almaty/ });
    await waitFor(() => {
      expect(title).toHaveFocus();
    });
  });

  it("join: the student invite is made and shown at once, in view", async () => {
    const seen = stubApi({ card: OWNS });
    renderWith(<ShalaScreen id={SHALA} onBack={vi.fn()} open="join" />);

    const qr = await screen.findByRole("img", { name: "QR code for the shala's link" });
    expect(screen.queryByRole("button", { name: "➕ Invite students to the shala" })).toBeNull();
    const posts = calls(seen, "POST", `/api/v1/shalas/${SHALA}/join-link`);
    expect(posts).toHaveLength(1);
    expect(await posts[0]?.json()).toEqual({ rotate: false }); // the same link, never a new one
    expect((scrolled.mock.contexts[0] as HTMLElement).contains(qr)).toBe(true);
    expect(screen.queryByRole("button", { name: "Save the class" })).toBeNull(); // the class form stays shut
  });

  it("opened plainly, nothing is open and nothing scrolls", async () => {
    const seen = stubApi({ card: OWNS });
    renderWith(card());

    await screen.findByRole("button", { name: "➕ Add a class" });
    expect(
      screen.getByRole("button", { name: "➕ Invite students to the shala" }),
    ).toBeInTheDocument();
    expect(calls(seen, "POST", `/api/v1/shalas/${SHALA}/join-link`)).toHaveLength(0);
    expect(scrolled).not.toHaveBeenCalled();
  });

  it("a staff member who may not edit classes gets the card, no form", async () => {
    stubApi({ card: shalaOut(TEACHER) });
    renderWith(<ShalaScreen id={SHALA} onBack={vi.fn()} open="class" />);

    await screen.findByRole("button", { name: "➕ Invite students to the shala" });
    expect(screen.queryByRole("button", { name: "Save the class" })).toBeNull();
  });

  it.each(["class", "join"] as const)(
    "the Shala tab's start %s:<id> opens that card so, once",
    async (open) => {
      stubApi({ mine: MINE, card: OWNS });
      renderWith(<ShalaTab start={`${open}:${SHALA}`} onSchedule={vi.fn()} onStudents={vi.fn()} />);
      const opened = () =>
        open === "class"
          ? form()
          : screen.findByRole("img", { name: "QR code for the shala's link" });
      expect(await opened()).toBeInTheDocument();

      if (open === "class") {
        act(() => {
          vi.mocked(useBackButton).mock.lastCall?.[0](); // Back from the form, to the card
        });
        expect(await screen.findByRole("button", { name: "➕ Add a class" })).toBeVisible();
      }
      act(() => {
        vi.mocked(useBackButton).mock.lastCall?.[0](); // Back to the lists
      });
      fireEvent.click(await screen.findByRole("button", { name: /Ashtanga Almaty/ }));

      // The same card again, as a tap opens it: nothing unfolded.
      expect(await screen.findByRole("button", { name: "➕ Add a class" })).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "➕ Invite students to the shala" }),
      ).toBeInTheDocument();
    },
  );
});

// ID-07, UI-06 stage 4B (spec §4): the bot's student part of the card, under its title: one
// line per teacher I wait for here, each with Withdraw, then "🤝 Pick a teacher" while someone
// can be picked. The picker opens over the card; its line stays on the card (QE).
describe("the card's student part", () => {
  const ANNA_C = { id: ANNA, name: "Anna" };
  const BORIS_C = { id: BORIS, name: "Boris" };
  const CHOICES = `/api/v1/shalas/${SHALA}/teacher-choices`;
  it("a student: the waiting lines with Withdraw, then Pick a teacher, right under the title", async () => {
    stubApi({ card: shalaOut(STUDENT), choices: () => ({ offer: [BORIS_C], waiting: [ANNA_C] }) });
    renderWith(card());

    const pick = await screen.findByRole("button", { name: "🤝 Pick a teacher" });
    const line = screen.getByText((t) => plain(t) === "⏳ Waiting for an answer: Anna");
    const withdraw = screen.getByRole("button", {
      name: (n) => plain(n) === "Withdraw: Anna…",
    });
    const heading = screen.getByRole("heading", { level: 1 });
    // The title, the waiting line and its Withdraw, then the row, before the rest of the card.
    expect(heading.compareDocumentPosition(line) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(line.compareDocumentPosition(withdraw) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(withdraw.compareDocumentPosition(pick) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const place = screen.getByText((t) => plain(t) === "📍 Almaty");
    expect(pick.compareDocumentPosition(place) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // No state, date or count: the name, and nothing else.
    const box = line.closest(".card");
    expect(plain(box?.textContent)).toBe("⏳ Waiting for an answer: AnnaWithdraw…");
    // The name stands on the line: the button reads "Withdraw…", named in full for a screen reader.
    expect(withdraw.textContent).toBe("Withdraw…");
  });

  it("nobody to pick and nobody waited for: nothing at all", async () => {
    stubApi({ card: shalaOut(STUDENT) });
    renderWith(card());

    await screen.findByText((t) => plain(t) === "📍 Almaty");
    expect(screen.queryByRole("button", { name: /Pick a teacher/ })).toBeNull();
    expect(pageText()).not.toContain("Waiting");
  });

  it.each([
    ["owner", OWNER],
    ["teacher", TEACHER],
    ["admin", ADMIN],
  ] as const)("staff (%s) never read who can be picked", async (_, me) => {
    const seen = stubApi({ card: shalaOut(me), choices: () => ({ offer: [ANNA_C], waiting: [] }) });
    renderWith(card());

    await screen.findByText((t) => plain(t) === "📍 Almaty");
    expect(calls(seen, "GET", CHOICES)).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /Pick a teacher/ })).toBeNull();
  });

  it("Withdraw asks once, takes it back, and the card says so", async () => {
    telegram.confirmDestructive.mockResolvedValue(true);
    let withdrawn = false;
    const seen = stubApi({
      card: shalaOut(STUDENT),
      choices: () => (withdrawn ? { offer: [], waiting: [] } : { offer: [], waiting: [ANNA_C] }),
    });
    renderWith(card());

    const withdraw = await screen.findByRole("button", {
      name: (n) => plain(n) === "Withdraw: Anna…",
    });
    withdrawn = true;
    fireEvent.click(withdraw);

    const said = await screen.findByRole("status");
    expect(plain(said.textContent)).toBe("Request withdrawn.");
    expect(pageText()).not.toContain("Waiting for an answer");
    const [message] = telegram.confirmDestructive.mock.calls[0] ?? [];
    expect(plain(message)).toMatch(/^Withdraw your request to Anna\? No one gets a message\./);
    expect(calls(seen, "DELETE", `/api/v1/me/teacher-requests/${ANNA}`)).toHaveLength(1);
  });

  it("Pick opens the picker over the card; the line and the new waiting line stay on the card", async () => {
    let asked = false;
    const seen = stubApi({
      card: shalaOut(STUDENT),
      choices: () =>
        asked ? { offer: [], waiting: [BORIS_C] } : { offer: [BORIS_C], waiting: [] },
      ask: () => {
        asked = true;
        return json({ result: "created" });
      },
    });
    renderWith(card());

    fireEvent.click(await screen.findByRole("button", { name: "🤝 Pick a teacher" }));

    await screen.findByText((t) => plain(t) === "Is Boris your teacher?");
    expect(screen.getByRole("heading", { level: 1 })).toHaveFocus();
    expect(screen.getByText((t) => plain(t) === "📍 Almaty")).not.toBeVisible(); // the card is under the layer
    fireEvent.click(screen.getByRole("button", { name: "✅ Yes" }));

    const said = await screen.findByRole("status");
    expect(plain(said.textContent)).toBe(
      "✉️ Request sent to Boris. Nothing from your log is shown until they confirm.",
    );
    // A result, not an error or an aside: normal text, not the small grey status style.
    expect(said).not.toHaveClass("status");
    expect(said).not.toHaveClass("hint");
    const line = await screen.findByText((t) => plain(t) === "⏳ Waiting for an answer: Boris");
    expect(said.compareDocumentPosition(line) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("button", { name: "🤝 Pick a teacher" })).toBeNull();
    expect(calls(seen, "POST", "/api/v1/me/teacher-requests")).toHaveLength(1);
    // Right under the card's title.
    expect(said.previousElementSibling).toBe(
      screen.getByRole("heading", { level: 1, name: /Ashtanga Almaty/ }),
    );
  });

  it("Russian: the bot's words", async () => {
    stubApi({ card: shalaOut(STUDENT), choices: () => ({ offer: [BORIS_C], waiting: [ANNA_C] }) });
    renderWith(card(), "ru");

    expect(await screen.findByRole("button", { name: "🤝 Выбрать учителя" })).toBeVisible();
    expect(screen.getByText((t) => plain(t) === "⏳ Ждём ответа: Anna")).toBeVisible();
    expect(
      screen.getByRole("button", { name: (n) => plain(n) === "Отозвать: Anna…" }),
    ).toBeVisible();
  });
});

// UI-06 stage 4B (QF): the bot's "📣 Announce" from a shala (`?open=announce&shala=`) opens
// that shala's card with the message form over it; Back finds the card, where its
// announcements are, and then the list.
describe("opened to announce", () => {
  const ANNOUNCES = shalaOut({ ...OWNER, announce: true });
  const back = () => {
    act(() => {
      vi.mocked(useBackButton).mock.lastCall?.[0]();
    });
  };
  const composer = () => screen.findByRole("heading", { level: 1, name: "📣 Announcement" });

  it("someone who may announce gets the form over the card; Back shows the card", async () => {
    stubApi({ card: ANNOUNCES });
    renderWith(<ShalaScreen id={SHALA} onBack={vi.fn()} open="announce" />);

    expect(await composer()).toBeVisible();
    // The card is there under it, hidden.
    expect(
      screen.getByRole("button", { name: "📣 Announcements", hidden: true }),
    ).not.toBeVisible();
    back();

    expect(await screen.findByRole("button", { name: "📣 Announcements" })).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: "📣 Announcement" })).toBeNull();
  });

  // Opened from a link, nothing on the card had the focus: Back gives it to the card's title,
  // never to the page's body.
  it("Back from the form opened by the link focuses the card's title", async () => {
    stubApi({ card: ANNOUNCES });
    renderWith(<ShalaScreen id={SHALA} onBack={vi.fn()} open="announce" />);
    await composer();
    back();

    const title = await screen.findByRole("heading", { level: 1, name: /Ashtanga Almaty/ });
    await waitFor(() => {
      expect(title).toHaveFocus();
    });
  });

  // QF is for sending to this shala: the form sends with its id, not to all my students.
  it("the form opened by the link sends to this shala", async () => {
    vi.mocked(confirmAction).mockResolvedValueOnce(true);
    const seen = stubApi({ card: ANNOUNCES });
    renderWith(<ShalaTab start={`announce:${SHALA}`} onSchedule={vi.fn()} onStudents={vi.fn()} />);
    await composer();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Led class at 7" } });
    const send = screen.getByRole("button", { name: "Send" });
    await waitFor(() => {
      expect(send).toBeEnabled(); // once the shala's audience is known
    });
    fireEvent.click(send);

    await waitFor(() => {
      expect(calls(seen, "POST", "/api/v1/me/announcements")).toHaveLength(1);
    });
    const [post] = calls(seen, "POST", "/api/v1/me/announcements");
    expect(await post?.json()).toEqual({
      to: "shala",
      shala_id: SHALA,
      text: "Led class at 7",
      pin_days: 0,
    });
  });

  it("once: the card's own Announce opens the form again, plainly", async () => {
    stubApi({ card: ANNOUNCES });
    renderWith(<ShalaScreen id={SHALA} onBack={vi.fn()} open="announce" />);
    await composer();
    back();

    fireEvent.click(await screen.findByRole("button", { name: "📣 Announce to the shala" }));

    expect(await composer()).toBeVisible();
    back();
    expect(await screen.findByRole("button", { name: "📣 Announce to the shala" })).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: "📣 Announcement" })).toBeNull();
  });

  it.each([
    ["a student", STUDENT],
    ["staff without the right", TEACHER],
  ])("%s gets the card, no form", async (_who, me) => {
    stubApi({ card: shalaOut(me) });
    renderWith(<ShalaScreen id={SHALA} onBack={vi.fn()} open="announce" />);

    expect(await screen.findByRole("button", { name: "📣 Announcements" })).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: "📣 Announcement" })).toBeNull();
  });

  it("the Shala tab's start announce:<id> for someone who may not announce: the card, no form", async () => {
    const seen = stubApi({ mine: MINE, card: shalaOut(TEACHER) });
    renderWith(<ShalaTab start={`announce:${SHALA}`} onSchedule={vi.fn()} onStudents={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "📣 Announcements" })).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: "📣 Announcement" })).toBeNull();
    expect(screen.queryByRole("button", { name: "📣 Announce to the shala" })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(calls(seen, "POST", "/api/v1/me/announcements")).toHaveLength(0);
  });

  it("the Shala tab's start announce:<id>: form, then the card, then the list", async () => {
    stubApi({ mine: MINE, card: ANNOUNCES });
    renderWith(<ShalaTab start={`announce:${SHALA}`} onSchedule={vi.fn()} onStudents={vi.fn()} />);

    expect(await composer()).toBeVisible();
    back();
    expect(await screen.findByRole("button", { name: "📣 Announcements" })).toBeVisible();
    back();

    fireEvent.click(await screen.findByRole("button", { name: /Ashtanga Almaty/ }));
    expect(await screen.findByRole("button", { name: "📣 Announcements" })).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: "📣 Announcement" })).toBeNull();
  });
});

// UI-06 stage 4 (Q340): the owner's first steps, from the server's `setup` (the same rule as
// Today's next step). One step is the button; "I teach alone" is remembered on the device.
describe("the setup list", () => {
  const scrolled = vi.fn();
  beforeEach(() => {
    Element.prototype.scrollIntoView = scrolled;
    localStorage.clear();
  });
  afterEach(() => {
    delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    vi.restoreAllMocks();
  });
  const owns = (setup: string[] | null, me: MeIn = OWNER) =>
    shalaOut({ ...me, schedule: true }, { setup });
  const list = () => screen.queryByRole("region", { name: "Set up your shala" });
  const current = () =>
    screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-current") === "step")
      .map((b) => b.textContent);
  const loaded = () => screen.findByRole("button", { name: "➕ Add a class" });

  it("a new shala: Add a class is the step, the other two are quiet", async () => {
    stubApi({ card: owns(["add_class", "invite_students", "invite_staff"]) });
    renderWith(card());
    await loaded();

    expect(list()).toBeInTheDocument();
    expect(current()).toEqual(["Add a class"]);
    expect(
      screen.getByRole("button", { name: "Invite students to the shala" }),
    ).toBeInTheDocument();
    // Two or three words on the row; "optional" is its quiet second line.
    const third = screen.getByRole("button", { name: "Invite teachers and staff" });
    expect(third).toHaveAccessibleDescription("Optional");
    expect(third.textContent).toBe("Invite teachers and staff");
    expect(screen.queryByRole("img", { name: "done" })).toBeNull();
    expect(screen.queryByRole("button", { name: "I teach alone" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Add a class" }));
    expect(await screen.findByRole("heading", { level: 1, name: "New class" })).toBeVisible();
  });

  it("with a class: it is ticked, and Invite students opens the student link", async () => {
    const seen = stubApi({ card: owns(["invite_students", "invite_staff"]) });
    renderWith(card());
    await loaded();

    expect(current()).toEqual(["Invite students to the shala"]);
    expect(screen.getAllByRole("img", { name: "done" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Add a class" })).toBeNull(); // done: plain text
    fireEvent.click(screen.getByRole("button", { name: "Invite students to the shala" }));

    const qr = await screen.findByRole("img", { name: "QR code for the shala's link" });
    const made = calls(seen, "POST", `/api/v1/shalas/${SHALA}/join-link`);
    expect(made).toHaveLength(1);
    expect(await made[0]?.json()).toEqual({ rotate: false });
    expect((scrolled.mock.contexts[0] as HTMLElement).contains(qr)).toBe(true);
  });

  it("with a class and a student: Invite teachers and staff opens the role picker on Teacher", async () => {
    const seen = stubApi({ card: owns(["invite_staff"]) });
    renderWith(card());
    await loaded();

    expect(current()).toEqual(["Invite teachers and staff"]);
    expect(
      screen.getByRole("button", { name: "Invite teachers and staff" }),
    ).toHaveAccessibleDescription("Optional");
    expect(screen.getAllByRole("img", { name: "done" })).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Invite teachers and staff" }));

    const hint = await screen.findByText("Choose a role. The link adds one person with that role.");
    expect((scrolled.mock.contexts[0] as HTMLElement).contains(hint)).toBe(true);
    // The step is about teachers: that role is the one marked and under the finger. Nothing
    // is made until it is tapped (a staff link works once).
    const teacher = screen.getByRole("button", { name: "Teacher" });
    expect(teacher).toHaveAttribute("aria-current", "true");
    expect(teacher).toHaveFocus();
    expect(screen.getByRole("button", { name: "Assistant" })).not.toHaveAttribute("aria-current");
    expect(calls(seen, "POST", `/api/v1/shalas/${SHALA}/staff-invites`)).toHaveLength(0);
  });

  it("opened from its own row, the role picker marks no role", async () => {
    stubApi({ card: owns(["invite_staff"]) });
    renderWith(card());
    await loaded();

    fireEvent.click(screen.getByRole("button", { name: "➕ Invite staff" }));

    await screen.findByText("Choose a role. The link adds one person with that role.");
    expect(screen.getByRole("button", { name: "Teacher" })).not.toHaveAttribute("aria-current");
  });

  it("I teach alone puts the list away, on this device, for good", async () => {
    stubApi({ card: owns(["invite_staff"]) });
    const first = renderWith(card());
    await loaded();

    fireEvent.click(screen.getByRole("button", { name: "I teach alone" }));

    expect(list()).toBeNull();
    first.unmount();
    renderWith(card());
    await loaded();
    expect(list()).toBeNull();
  });

  it("put away, the third step is not listed when another one comes back", async () => {
    localStorage.setItem(`setup.solo.${SHALA}`, "1");
    stubApi({ card: owns(["add_class", "invite_staff"]) }); // the only class was deleted
    renderWith(card());
    await loaded();

    expect(current()).toEqual(["Add a class"]);
    expect(screen.queryByRole("button", { name: "Invite teachers and staff" })).toBeNull();
  });

  it("blocked storage counts as I teach alone: never a list that cannot be put away", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    stubApi({ card: owns(["invite_staff"]) });
    renderWith(card());
    await loaded();

    expect(list()).toBeNull();
  });

  it.each([
    ["set up", owns([])],
    ["a manager", owns(null, ADMIN)],
    ["a teacher", owns(null, TEACHER)],
  ])("is not there for %s", async (_, shala) => {
    stubApi({ card: shala });
    renderWith(card());
    await loaded();

    expect(list()).toBeNull();
  });
});

describe("Follow my shala in Settings", () => {
  // The moon calendar's city is on Settings → More (UI-06 stage 3).
  const settings = (locale: Locale = "en") => <More me={{ ...ME, locale }} onBack={vi.fn()} />;
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
      name: /^🌙 Moon days · 📍/,
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
      name: /^🌙 Moon days · 📍/,
    });

    await waitFor(() => {
      expect(select.options.length).toBeGreaterThan(1);
    });
    expect(Array.from(select.options).some((o) => o.textContent.includes("shala"))).toBe(false);
  });
});

// UI-06 stage 6 (spec §3.1, B2): the card's Classes, each class as it stands, for those who may
// manage the schedule; a row opens the class's form, "➕ Add a class" is under the rows and
// leads while there are none; after a save the card says so and offers "Add another class".
describe("the Classes on the card", () => {
  const scrolled = vi.fn();
  beforeEach(() => {
    Element.prototype.scrollIntoView = scrolled;
  });
  afterEach(() => {
    delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
  });
  const OWNS = shalaOut({ ...OWNER, schedule: true });
  const today = todayIn("Asia/Almaty");
  const series = (id: string, over: Record<string, unknown> = {}) => ({
    id,
    type: "mysore",
    title: null,
    online: false,
    city: null,
    teacher_id: null,
    start: "06:00:00",
    minutes: 210,
    weekdays: [1, 2, 3, 4, 5],
    every: 1,
    starts_on: "2026-01-05",
    ends_on: null,
    rrule: "FREQ=WEEKLY",
    ...over,
  });
  const id = (n: number) => `00000000-0000-0000-0000-0000000000e${String(n)}`;
  const section = () => screen.findByRole("heading", { level: 2, name: "Classes" });
  /** The rows of the Classes, as read: label, then the quiet second line. */
  const rows = async () => {
    const heading = await section();
    const box = heading.closest("section") as HTMLElement;
    await waitFor(() => {
      expect(box).not.toHaveAttribute("aria-busy");
    });
    return within(box)
      .getAllByRole("button")
      .filter((b) => !b.classList.contains("guide")) // the quiet 📖 Guide, tested apart
      .map((b) =>
        [
          b.querySelector(".lrow-label")?.textContent ?? b.textContent,
          b.querySelector(".lrow-sub")?.textContent,
        ]
          .filter(Boolean)
          .map((t) => plain(t))
          .join(" | "),
      );
  };

  it("ends with the guide's page on classes, in the person's language", async () => {
    stubApi({ card: OWNS, classes: [series(id(1))] });
    renderWith(card());
    const box = (await section()).closest("section") as HTMLElement;

    fireEvent.click(within(box).getByRole("button", { name: "📖 Guide" }));

    expect(telegram.openLink).toHaveBeenLastCalledWith("https://tristhana.app/staff/classes/");
  });

  it("lists the current classes in order, each with what else is set; ended ones go", async () => {
    stubApi({
      card: OWNS,
      classes: [
        series(id(1), {
          type: "led",
          start: "08:00:00",
          minutes: 90,
          weekdays: [7],
          teacher_id: ANNA,
        }),
        series(id(2), { ends_on: "2026-01-31" }), // ended
        series(id(3), { teacher_id: BORIS }),
        series(id(4), {
          type: "workshop",
          start: "10:00:00",
          minutes: 120,
          weekdays: [],
          starts_on: addDays(today, 3),
          rrule: null,
        }),
        series(id(5), {
          type: "pranayama",
          start: "17:00:00",
          minutes: 60,
          weekdays: [1, 3, 5],
          every: 2,
          title: "Nadi",
        }),
        series(id(6), {
          weekdays: [1, 2, 3, 4, 5, 6, 7],
          start: "07:00:00",
          online: true,
          city: "moscow",
          ends_on: addDays(today, 30),
        }),
        series(id(7), {
          type: "chanting",
          start: "19:00:00",
          minutes: 60,
          weekdays: [6, 7, 1],
          starts_on: addDays(today, 2),
        }),
      ],
    });
    renderWith(card());

    expect(await rows()).toEqual([
      "Mysore · Mon–Fri · 06:00–09:30 | Boris",
      `Mysore · every day · 07:00–10:30 | through ${dayName(addDays(today, 30), "en")} · 🌐 Moscow (UTC+3)`,
      "Pranayama Nadi · Mon, Wed, Fri · 17:00–18:00 | every 2 weeks",
      `Chanting · Mon, Sat, Sun · 19:00–20:00 | from ${dayName(addDays(today, 2), "en")}`,
      "Led · Sun · 08:00–09:30 | Anna",
      `Workshop · ${dayName(addDays(today, 3), "en")} · 10:00–12:00`,
      "➕ Add a class",
    ]);
    // Between the place and the announcements; the Schedule by date stays below.
    const classes = (await section()).closest("section") as HTMLElement;
    const announcements = screen.getByRole("button", { name: "📣 Announcements" });
    expect(classes.compareDocumentPosition(announcements)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("reads in Russian", async () => {
    stubApi({
      locale: "ru",

      card: OWNS,
      classes: [
        series(id(1)),
        series(id(2), { weekdays: [1, 2, 3, 4, 5, 6, 7], start: "08:00:00" }),
      ],
    });
    renderWith(card(), "ru");

    const heading = await screen.findByRole("heading", { level: 2, name: "Занятия" });
    await waitFor(() => {
      expect(heading.closest("section")).not.toHaveAttribute("aria-busy");
    });
    const text = plain(heading.closest("section")?.textContent);
    expect(text).toContain("Майсор · пн–пт · 06:00–09:30");
    expect(text).toContain("Майсор · каждый день · 08:00–11:30");
    expect(text).toContain("➕ Добавить занятие");
  });

  it("with none: the line, and Add a class as the main row", async () => {
    stubApi({ card: OWNS, classes: [series(id(2), { ends_on: "2026-01-31" })] });
    renderWith(card());

    await section();
    expect(await screen.findByText("No classes yet.")).toBeInTheDocument();
    const add = screen.getByRole("button", { name: "➕ Add a class" });
    expect(add).toHaveClass("btn");
    expect(add.closest("section")).toBe((await section()).closest("section"));
  });

  // Spec §13.14: one main action. The owner's setup list leads with "Add a class" while it is
  // due, so the Classes' own add row is a plain row then.
  it("with none and the setup list showing Add a class: the add row is plain", async () => {
    stubApi({
      card: shalaOut({ ...OWNER, schedule: true }, { setup: ["add_class", "invite_students"] }),
      classes: [],
    });
    renderWith(card());

    const heading = await section();
    expect(await screen.findByText("No classes yet.")).toBeInTheDocument();
    const box = heading.closest("section") as HTMLElement;
    const add = within(box).getByRole("button", { name: "➕ Add a class" });
    expect(add).not.toHaveClass("btn");
    expect(add).toHaveClass("lrow");
    // The setup list's step is the one main action on the card.
    const steps = screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-current") === "step");
    expect(steps.map((b) => b.textContent)).toEqual(["Add a class"]);
    expect(screen.getAllByRole("button").filter((b) => b.classList.contains("btn"))).toEqual(steps);

    fireEvent.click(add);
    expect(await screen.findByRole("heading", { level: 1, name: "New class" })).toBeVisible();
  });

  it("with none and the setup list past that step: the add row is the main one again", async () => {
    stubApi({
      card: shalaOut({ ...OWNER, schedule: true }, { setup: ["invite_students"] }),
      classes: [series(id(2), { ends_on: "2026-01-31" })], // its only class has ended
    });
    renderWith(card());

    await screen.findByText("No classes yet.");
    expect(screen.getByRole("button", { name: "➕ Add a class" })).toHaveClass("btn");
  });

  it.each([
    ["a student", STUDENT],
    ["a teacher who may not manage the schedule", TEACHER],
  ] as const)("is not there for %s, and nothing reads the classes", async (_, me) => {
    const seen = stubApi({ card: shalaOut(me), classes: [series(id(1))] });
    renderWith(card());

    await screen.findByText(/Ashtanga Almaty/);
    await screen.findByRole("heading", { name: "🗓 Schedule" });
    expect(screen.queryByRole("heading", { name: "Classes" })).toBeNull();
    expect(screen.queryByRole("button", { name: "➕ Add a class" })).toBeNull();
    expect(calls(seen, "GET", `/api/v1/shalas/${SHALA}/classes`)).toHaveLength(0);
  });

  it("a row opens that class's form, proposing today for a change to a class that has run", async () => {
    // A day the class does not run today: the form proposes today itself (ADR-0048).
    const tomorrow = new Date(`${addDays(today, 1)}T00:00:00Z`).getUTCDay() || 7;
    stubApi({ card: OWNS, classes: [series(id(1), { weekdays: [tomorrow] })] });
    renderWith(card());
    await rows();

    fireEvent.click(screen.getByRole("button", { name: /^Mysore · / }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Change the class" }),
    ).toBeVisible();
    expect(
      await screen.findByText((t) =>
        plain(t).startsWith(`Changes apply from ${dayName(today, "en")}.`),
      ),
    ).toBeInTheDocument();
  });

  it("a class that has not begun opens whole, from its own first date", async () => {
    stubApi({ card: OWNS, classes: [series(id(1), { starts_on: addDays(today, 5) })] });
    renderWith(card());
    await rows();

    fireEvent.click(screen.getByRole("button", { name: /^Mysore · / }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Change the class" }),
    ).toBeVisible();
    // Nothing has run, so the change is to the whole class: no date to apply it from.
    expect(screen.queryByText(/Changes apply from/)).toBeNull();
  });

  it("after a save: the card says so, and the add row reads Add another class", async () => {
    const seen = stubApi({ card: OWNS });
    renderWith(card());
    fireEvent.click(await screen.findByRole("button", { name: "➕ Add a class" }));
    expect(await screen.findByRole("heading", { level: 1, name: "New class" })).toBeVisible();
    // B2: what one class is, under the days (the wording changed after A1).
    expect(
      screen.getByText(
        "Pick the days this class runs at this time. A different time or type is a separate class: Mysore Mon–Fri at 06:00 and Led on Sunday at 08:00 are two. Save this one, then add the next.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save the class" }));

    await waitFor(() => {
      expect(calls(seen, "POST", `/api/v1/shalas/${SHALA}/classes`)).toHaveLength(1);
    });
    expect(await screen.findByRole("status")).toHaveTextContent("✓ Class saved.");
    expect(await screen.findByRole("button", { name: "➕ Add another class" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "➕ Add a class" })).toBeNull();
  });

  it("opened plainly, it says nothing was saved", async () => {
    stubApi({ card: OWNS, classes: [series(id(1))] });
    renderWith(card());
    await rows();

    expect(screen.queryByText("✓ Class saved.")).toBeNull();
    expect(screen.getByRole("button", { name: "➕ Add a class" })).not.toHaveClass("btn");
  });
});

// UI-06 stage 6 (spec §2): the bot's "✏️ Edit the shala" opens the card with its edit form.
describe("opened to edit the shala", () => {
  const scrolled = vi.fn();
  beforeEach(() => {
    Element.prototype.scrollIntoView = scrolled;
  });
  afterEach(() => {
    delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
  });

  it("an owner or a manager gets the form open, in view", async () => {
    stubApi({ card: shalaOut(ADMIN) });
    renderWith(<ShalaScreen id={SHALA} onBack={vi.fn()} open="edit" />);

    const name = await screen.findByLabelText("Name");
    expect(name).toHaveValue("Ashtanga Almaty");
    expect(scrolled.mock.contexts[0]).toBe(name.closest("form"));
    expect(screen.queryByRole("button", { name: "✏️ Edit the shala" })).toBeNull();
  });

  it("someone who may not edit it gets the card", async () => {
    stubApi({ card: shalaOut(TEACHER) });
    renderWith(<ShalaScreen id={SHALA} onBack={vi.fn()} open="edit" />);

    await screen.findByText(/Ashtanga Almaty/);
    await screen.findByRole("button", { name: "➕ Invite students to the shala" });
    expect(screen.queryByLabelText("Name")).toBeNull();
    expect(scrolled).not.toHaveBeenCalled();
  });

  it("the Shala tab's start edit:<id> opens that card so", async () => {
    stubApi({ mine: MINE, card: shalaOut(OWNER) });
    renderWith(<ShalaTab start={`edit:${SHALA}`} onSchedule={vi.fn()} onStudents={vi.fn()} />);

    expect(await screen.findByLabelText("Name")).toHaveValue("Ashtanga Almaty");
  });
});
