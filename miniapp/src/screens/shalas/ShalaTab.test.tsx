import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import shellSource from "../../shell/Shell.tsx?raw";

// The app's tsconfig has no Node types, and Vitest blanks CSS imports, `?raw` included.
declare const process: {
  cwd: () => string;
  getBuiltinModule: (id: "node:fs") => {
    readFileSync: (path: string, encoding: "utf8") => string;
  };
};

// UI-06 stage 4B (spec §3, §5, §11): the Shala tab's root is one list in a fixed order, each
// part only when it has something, the first row the main one, no empty card: the people
// waiting for my answer (QC), my schedule, my shalas, my teachers, "👥 My students" (QD), then
// the quiet group for teachers and shalas. ID-04's teachers with their ⭐ and takeover rules
// and the teacher invite live here: writes wait for the server, a 409 refetches, the QR comes
// from the API, and the link is never built here. Driven through App, so the file doesn't
// care where the screen lives. App keeps one QueryClient per module, so each test imports a
// fresh App.

const telegram = vi.hoisted(() => ({
  openSettings: vi.fn() as () => void,
  back: vi.fn() as () => void,
  confirmDestructive: vi.fn<(message: string, ok: string, cancel: string) => Promise<boolean>>(),
  confirmAction: vi.fn<(message: string, ok: string, cancel: string) => Promise<boolean>>(),
  openTelegramLink: vi.fn<(url: string) => void>(),
}));
const { confirmDestructive, confirmAction, openTelegramLink } = telegram;

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: (onBack: () => void) => {
    telegram.back = onBack;
  },
  useBackShown: vi.fn(() => false),
  backButtonAvailable: vi.fn(() => true),
  markReady: vi.fn(),
  useMainButton: vi.fn(),
  useSettingsButton: (open: () => void) => {
    telegram.openSettings = open;
  },
  enableClosingConfirmation: vi.fn(),
  disableClosingConfirmation: vi.fn(),
  confirmDestructive: telegram.confirmDestructive,
  confirmAction: telegram.confirmAction,
  allowBotMessages: vi.fn(() => Promise.resolve(false)),
  closeApp: vi.fn(),
  openTelegramLink: telegram.openTelegramLink,
}));

const TODAY = "2026-11-07";
const ME = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Ash",
  locale: "en",
  timezone: null,
  name_from_telegram: true,
  locale_from_telegram: true,
  hide_ladies: false,
  offer_check_in: true,
  home_city_chosen: true,
  day_off: null,
};
const LENA = "00000000-0000-0000-0000-0000000000a1";
const BORIS = "00000000-0000-0000-0000-0000000000a2";
const SHIVA = "00000000-0000-0000-0000-0000000000b1";
const URL_1 = "https://t.me/tristhana_bot?start=t_aB3dE6gH9jK2mN5p";
const URL_2 = "https://t.me/tristhana_bot?start=t_Zy8xW7vU6tS5rQ4p";
const QR_1 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkAAAACklEQVR4AQ==";
const QR_2 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkBBBBCklEQVR4AQ==";

interface Teacher {
  id: string;
  name: string | null;
  primary: boolean;
  primary_chosen: boolean;
  linked_at: string;
}
interface Student {
  id: string;
  name: string | null;
  linked_at: string;
}
/** ID-07: a teacher I asked and wait for. The API sends nothing else about a request. */
interface Asked {
  teacher_id: string;
  name: string | null;
  shala: { id: string; name: string };
}
interface LinksBody {
  teachers: Teacher[];
  students: Student[];
  asked?: Asked[];
  waiting?: number;
}

const teacher = (id: string, name: string | null, over: Partial<Teacher> = {}): Teacher => ({
  id,
  name,
  primary: false,
  primary_chosen: false,
  linked_at: "2026-11-01T06:00:00Z",
  ...over,
});
const student = (id: string, name: string | null): Student => ({
  id,
  name,
  linked_at: "2026-11-02T06:00:00Z",
});
const lena = (over: Partial<Teacher> = {}) => teacher(LENA, "Лена", { primary: true, ...over });
const boris = (over: Partial<Teacher> = {}) => teacher(BORIS, "Boris", over);
const TWO: LinksBody = { teachers: [lena(), boris()], students: [] };
const ANNA = "00000000-0000-0000-0000-0000000000d1";
const ROOM = { id: "00000000-0000-0000-0000-0000000000c1", name: "Mysore Room" };
const asked = (teacher_id: string, name: string | null, shala = ROOM): Asked => ({
  teacher_id,
  name,
  shala,
});

/** ID-07: someone waiting for my answer. */
interface Waiting {
  student_id: string;
  name: string | null;
  shala: { id: string; name: string };
}
const OLGA = "00000000-0000-0000-0000-0000000000e1";
const PAVEL = "00000000-0000-0000-0000-0000000000e2";
const AS_OF = "2026-11-07T04:30:00.123456Z";
const asks = (id: string, name: string | null, shala = ROOM): Waiting => ({
  student_id: id,
  name,
  shala,
});
const REQUESTS = "/api/v1/me/student-requests";

/** SC-01: a shala of mine, as `GET /me/shalas` lists it. */
const SHALA = "00000000-0000-0000-0000-0000000000c2";
const OTHER = "00000000-0000-0000-0000-0000000000c3";
const shalaOf = (id: string, name: string, side: "student" | "staff", owner = false) => ({
  id,
  name,
  city: "almaty",
  online: false,
  side,
  owner,
  roles: side === "staff" ? ["teacher"] : [],
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/** The account's language: `/me` wins over the launch locale, so the two must agree. */
let accountLocale: "en" | "ru" = "en";
/** My shalas, who waits for my answer, and my directory line (ID-05), per test. */
let mine: unknown[] = [];
let requests: () => Waiting[] = () => [];
let listing: unknown = { status: "none", available: false };

function background(path: string): unknown {
  // The device-timezone reply is the account too, and replaces it outside UTC.
  if (path === "/api/v1/me" || path === "/api/v1/me/device-timezone") {
    return { ...ME, locale: accountLocale };
  }
  if (path === "/api/v1/health") return { version: "1", commit: "abcdef0" };
  if (path === "/api/v1/moon/cities") return [];
  if (path === "/api/v1/me/days") {
    return {
      today: TODAY,
      timezone_known: true,
      days: [{ date: TODAY, status: "rest", practices: [], check_ins: [] }],
      auto: [],
      moon_location: "mysuru",
      notes: [],
      periods: [],
    };
  }
  if (path === "/api/v1/me/moon-days") {
    return { location: { slug: "mysuru", explicit: false }, today: TODAY, days: [] };
  }
  if (path === "/api/v1/me/notification-settings") {
    return {
      moon: { offsets: [1, 7], at: "19:00:00" },
      quiet: { start: "22:00:00", end: "07:00:00" },
      daily_cap: 3,
      practice: { on: true, at: "20:00:00", days: [1, 2, 3, 4, 5, 7] },
      timezone: null,
    };
  }
  return {};
}

type Answer = (request: Request) => Response | undefined | Promise<Response | undefined>;

/** Serves `links` (its `waiting` from `requests` unless given), `mine`, `requests` and
 * `listing`; `answer` may take over a write. Every API request lands in the result. */
function stubApi(links: () => LinksBody, answer: Answer = () => undefined): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request.clone());
      const custom = await answer(request);
      if (custom) return custom;
      const url = new URL(request.url);
      const path = url.pathname;
      if (path === "/api/v1/me/links") {
        const body = links();
        return json({ ...body, waiting: body.waiting ?? requests().length });
      }
      if (path === "/api/v1/me/shalas") return json(mine); // SC-01
      if (path === "/api/v1/me/directory-listing") return json(listing);
      if (path === "/api/v1/me/invite") return json({ url: URL_1, qr: QR_1 });
      if (path === REQUESTS) {
        const offset = Number(url.searchParams.get("offset") ?? 0);
        const limit = Number(url.searchParams.get("limit") ?? 50);
        const all = requests();
        return json({
          requests: all.slice(offset, offset + limit),
          total: all.length,
          as_of: AS_OF,
        });
      }
      if (path.startsWith(`${REQUESTS}/`)) return new Response(null, { status: 204 });
      if (request.method === "DELETE") return new Response(null, { status: 204 });
      return json(background(path));
    }),
  );
  return seen;
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
/** The screen's own text: the tab bar and the gear are the shell's. */
const pageText = () =>
  plain([...document.querySelectorAll("main")].map((main) => main.textContent).join(" "));
const calls = (seen: Request[], method: string, path: string) =>
  seen.filter((r) => r.method === method && new URL(r.url).pathname === path);

/** Today has loaded: the account is known. */
const homeLoaded = () => screen.findByRole("heading", { level: 2, name: /^(Today|Сегодня), / });
const TAB = { en: "🏛 Shala", ru: "🏛 Шала" } as const;

// The screens opened here are lazy chunks, and `renderApp()` resets the modules: loading
// each once fills the transform cache, so no test's first open outlasts `findBy…` (1 s).
beforeAll(async () => {
  await Promise.all([
    import("../../App"),
    import("./ShalaTab"),
    import("../settings/Settings"),
    import("../settings/DirectoryListing"),
    import("./ShalaScreen"),
    import("../teachers/Students"),
    import("../announcements/Announcements"),
  ]);
}, 60_000);

async function renderApp(locale: "en" | "ru" = "en") {
  accountLocale = locale;
  vi.resetModules();
  const { App } = await import("../../App");
  render(<App locale={locale} firstName="Ash" inTelegram />);
  await homeLoaded();
}

async function openScreen(locale: "en" | "ru" = "en") {
  await renderApp(locale);
  fireEvent.click(screen.getByRole("button", { name: TAB[locale] }));
  await screen.findByRole("heading", { level: 1, name: TAB[locale] });
}

beforeEach(() => {
  localStorage.clear();
  mine = [];
  requests = () => [];
  listing = { status: "none", available: false };
  confirmDestructive.mockReset();
  confirmDestructive.mockResolvedValue(false);
  confirmAction.mockReset();
  confirmAction.mockResolvedValue(false);
  openTelegramLink.mockReset();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe = vi.fn();
      disconnect = vi.fn();
    },
  );
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("the Shala tab opens the lazy screen; Today and Settings have no row for it", async () => {
  const seen = stubApi(() => TWO);
  await renderApp();
  expect(screen.queryByRole("button", { name: /Teachers and students/ })).toBeNull();
  expect(calls(seen, "GET", "/api/v1/me/links")).toHaveLength(0); // Today doesn't read the lists

  fireEvent.click(screen.getByRole("button", { name: "🏛 Shala" }));

  await screen.findByText("Лена");
  expect(screen.getByRole("heading", { level: 1, name: "🏛 Shala" })).toBeInTheDocument();
  expect(calls(seen, "GET", "/api/v1/me/links")).toHaveLength(1);

  act(() => {
    telegram.openSettings();
  });
  await screen.findByRole("heading", { level: 1, name: "Settings" });
  await screen.findByRole("button", { name: "📖 Guide" });
  expect(screen.queryByRole("button", { name: /Teachers and students/ })).toBeNull();
});

test("my teachers by name, with a fallback for no name; my students are one row, no names", async () => {
  stubApi(() => ({
    teachers: [lena(), teacher(BORIS, null)],
    students: [student(SHIVA, "Shiva")],
  }));

  await openScreen();

  const row = await screen.findByRole("button", { name: "👥 My students" });
  expect(pageText()).toContain("Лена");
  expect(pageText()).toContain("(no name)");
  // QD: the names, their week and Remove are on My students.
  expect(pageText()).not.toContain("Shiva");
  expect(row.closest(".card")).toBeNull();
});

test("nobody yet: one plain line and two starts in one small card, no empty cards", async () => {
  const seen = stubApi(() => ({ teachers: [], students: [] }));

  await openScreen();

  await screen.findByText(
    "Nobody here yet. To add a teacher or join a shala, open the link they send you.",
  );
  expect(screen.getByRole("heading", { level: 2, name: "For teachers and shalas" })).toBeVisible();
  const invite = screen.getByRole("button", { name: "Invite students" });
  expect(screen.getByRole("button", { name: "Shala and classes" })).toBeInTheDocument();
  expect(pageText()).not.toContain("start below");
  // The only card is the one that holds the two starts.
  expect([...document.querySelectorAll("main .card")]).toEqual([invite.parentElement]);
  expect(pageText()).not.toContain("No students on your list.");
  expect(calls(seen, "POST", "/api/v1/me/invite")).toHaveLength(0); // nothing is made unasked
});

test("no empty card: an empty list is simply not there", async () => {
  stubApi(() => ({ teachers: [], students: [student(SHIVA, "Shiva")] }));

  await openScreen();

  await screen.findByRole("button", { name: "👥 My students" });
  expect(pageText()).not.toContain("No teacher on your list");
  expect(document.querySelector("main .teachers")).toBeNull();
  // The only card is the group's list.
  expect(document.querySelectorAll("main .card")).toHaveLength(1);
  expect(screen.queryByRole("heading", { name: "🏛 Shalas" })).toBeNull();
});

test("with a teacher and no student, no students line either", async () => {
  stubApi(() => ({ teachers: [lena()], students: [] }));

  await openScreen();

  await screen.findByText("Лена");
  expect(pageText()).not.toContain("No students on your list.");
  expect(screen.queryByRole("button", { name: "👥 My students" })).toBeNull();
});

test("⭐ shows only with two or more teachers", async () => {
  stubApi(() => ({ teachers: [lena()], students: [] }));

  await openScreen();

  await screen.findByText("Лена");
  expect(pageText()).not.toContain("⭐");
  expect(screen.queryByRole("button", { name: "⭐ Make main" })).toBeNull();
});

test("two teachers separate the automatic main from a choice", async () => {
  stubApi(() => TWO);

  await openScreen();

  await screen.findByRole("button", { name: "⭐ Make main" });
  expect(pageText()).toContain("⭐ Main teacher: Лена (first on your list)");
  expect(screen.getAllByRole("button", { name: "⭐ Make main" })).toHaveLength(1);
});

test("a chosen main teacher reads as chosen", async () => {
  stubApi(() => ({
    teachers: [lena({ primary: false }), boris({ primary: true, primary_chosen: true })],
    students: [],
  }));

  await openScreen();

  await screen.findByRole("button", { name: "⭐ Make main" });
  expect(pageText()).toContain("⭐ Main teacher: Boris");
  expect(pageText()).not.toContain("first on your list");
});

test("make main waits for the server, then shows its answer", async () => {
  let release: (response: Response) => void = () => undefined;
  const after = {
    teachers: [lena({ primary: false }), boris({ primary: true, primary_chosen: true })],
    students: [],
  };
  const seen = stubApi(
    () => TWO,
    (request) =>
      request.method === "PUT"
        ? new Promise<Response>((r) => {
            release = r;
          })
        : undefined,
  );
  await openScreen();

  fireEvent.click(await screen.findByRole("button", { name: "⭐ Make main" }));

  await waitFor(() => {
    expect(calls(seen, "PUT", `/api/v1/me/teachers/${BORIS}/primary`)).toHaveLength(1);
  });
  expect(pageText()).toContain("⭐ Main teacher: Лена (first on your list)"); // not optimistic
  release(json(after));
  await waitFor(() => {
    expect(pageText()).not.toContain("first on your list");
  });
  expect(pageText()).toContain("⭐ Main teacher: Boris");
});

test("a 409 on make main refetches the lists", async () => {
  const changed = { teachers: [lena()], students: [] };
  let gets = 0;
  const seen = stubApi(
    () => (++gets === 1 ? TWO : changed),
    (request) => (request.method === "PUT" ? json({ code: "links_changed" }, 409) : undefined),
  );
  await openScreen();

  fireEvent.click(await screen.findByRole("button", { name: "⭐ Make main" }));

  await waitFor(() => {
    expect(screen.queryByText("Boris")).not.toBeInTheDocument();
  });
  expect(calls(seen, "GET", "/api/v1/me/links").length).toBeGreaterThan(1);
});

test("removing a teacher: Cancel sends nothing", async () => {
  const seen = stubApi(() => TWO);
  await openScreen();

  fireEvent.click((await screen.findAllByRole("button", { name: "Remove…" }))[1] as HTMLElement);

  await waitFor(() => {
    expect(confirmDestructive).toHaveBeenCalledOnce();
  });
  expect(seen.filter((r) => r.method === "DELETE")).toHaveLength(0);
  expect(pageText()).toContain("Boris");
});

test("removing the main teacher names who takes over, and confirming deletes", async () => {
  confirmDestructive.mockResolvedValue(true);
  let removed = false;
  const seen = stubApi(
    () => (removed ? { teachers: [boris({ primary: true })], students: [] } : TWO),
    (request) => {
      if (request.method !== "DELETE") return undefined;
      removed = true;
      return new Response(null, { status: 204 });
    },
  );
  await openScreen();

  fireEvent.click((await screen.findAllByRole("button", { name: "Remove…" }))[0] as HTMLElement);

  await waitFor(() => {
    expect(calls(seen, "DELETE", `/api/v1/me/teachers/${LENA}`)).toHaveLength(1);
  });
  const [message] = confirmDestructive.mock.calls[0] ?? [];
  expect(plain(message)).toContain(
    "Remove Лена from your teachers? They won't get a message, but you'll no longer be on their list.",
  );
  expect(plain(message)).toContain("Boris becomes your main teacher.");
  await waitFor(() => {
    expect(screen.queryByText("Лена")).not.toBeInTheDocument();
  });
});

test("removing a teacher who isn't main names no one", async () => {
  stubApi(() => TWO);
  await openScreen();

  fireEvent.click((await screen.findAllByRole("button", { name: "Remove…" }))[1] as HTMLElement);

  await waitFor(() => {
    expect(confirmDestructive).toHaveBeenCalledOnce();
  });
  const [message] = confirmDestructive.mock.calls[0] ?? [];
  expect(plain(message)).not.toContain("becomes your main teacher");
});

// Removing a student (and its confirm in the student's words) is on My students' card now:
// `teachers/Students.test.tsx`, "Remove".
test("a teacher with students sees no Remove for them here, and no primary marks", async () => {
  stubApi(() => ({ teachers: [], students: [student(SHIVA, "Shiva")] }));

  await openScreen();

  await screen.findByRole("button", { name: "👥 My students" });
  expect(screen.queryByRole("button", { name: "Remove…" })).toBeNull();
  expect(pageText()).not.toContain("⭐");
  expect(pageText().toLowerCase()).not.toContain("main teacher");
});

test("with 0 students the group's invite row is the quiet start", async () => {
  stubApi(() => ({ teachers: [lena()], students: [] }));

  await openScreen();

  await screen.findByRole("button", { name: "Invite students" });
  expect(screen.queryByRole("button", { name: "➕ Invite students" })).toBeNull();
  expect(screen.queryByRole("button", { name: "I teach: invite students" })).toBeNull();
});

test("with students the group's invite row is the plain invite", async () => {
  stubApi(() => ({ teachers: [], students: [student(SHIVA, "Shiva")] }));

  await openScreen();

  await screen.findByRole("button", { name: "➕ Invite students" });
  expect(screen.queryByRole("button", { name: "Invite students" })).toBeNull();
});

/** With nobody on the lists, the quiet "Invite students" row opens the invite under it. */
async function openInvite() {
  fireEvent.click(await screen.findByRole("button", { name: "Invite students" }));
  return screen.findByRole("img");
}

test("the invite shows the server's QR on the page, with no link built here", async () => {
  const seen = stubApi(() => ({ teachers: [], students: [] }));
  await openScreen();

  const qr = await openInvite();

  expect(qr).toHaveAttribute("src", QR_1);
  expect(pageText()).toContain(URL_1);
  expect(pageText()).toContain("Share this link or QR code. Each student confirms for themselves.");
  const [post] = calls(seen, "POST", "/api/v1/me/invite");
  expect(await post?.clone().json()).toEqual({ rotate: false });
  expect(seen.every((r) => !r.url.includes("t_"))).toBe(true);
});

test("Copy puts the link on the clipboard and says so", async () => {
  const writeText = vi.fn(() => Promise.resolve());
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  stubApi(() => ({ teachers: [], students: [] }));
  await openScreen();
  await openInvite();

  fireEvent.click(screen.getByRole("button", { name: "Copy link" }));

  await screen.findByRole("button", { name: "Copied" });
  expect(writeText).toHaveBeenCalledWith(URL_1);
});

test("Share opens Telegram's share sheet through the wrapper", async () => {
  stubApi(() => ({ teachers: [], students: [] }));
  await openScreen();
  await openInvite();

  fireEvent.click(screen.getByRole("button", { name: "📤 Share" }));

  expect(openTelegramLink).toHaveBeenCalledOnce();
  const [link = ""] = openTelegramLink.mock.calls[0] ?? [];
  const shared = new URL(link);
  expect(`${shared.origin}${shared.pathname}`).toBe("https://t.me/share/url");
  expect(shared.searchParams.get("url")).toBe(URL_1);
  expect(shared.searchParams.get("text")).toBe(
    "My link to add me as your teacher in Tristhana. The bot shows what I'd see before you confirm.",
  );
});

test("a new link: Cancel keeps it, confirming rotates and shows the new one", async () => {
  const seen = stubApi(
    () => ({ teachers: [], students: [] }),
    async (request) => {
      if (new URL(request.url).pathname !== "/api/v1/me/invite") return undefined;
      const body = (await request.clone().json()) as { rotate?: boolean };
      return json(body.rotate ? { url: URL_2, qr: QR_2 } : { url: URL_1, qr: QR_1 });
    },
  );
  await openScreen();
  await openInvite();

  fireEvent.click(screen.getByRole("button", { name: "🔄 New link…" }));
  await waitFor(() => {
    expect(confirmDestructive).toHaveBeenCalledOnce();
  });
  expect(calls(seen, "POST", "/api/v1/me/invite")).toHaveLength(1);
  const [message] = confirmDestructive.mock.calls[0] ?? [];
  expect(plain(message)).toBe(
    "Get a new link? The old link and QR stop working. People already on your list stay.",
  );

  confirmDestructive.mockResolvedValue(true);
  fireEvent.click(screen.getByRole("button", { name: "🔄 New link…" }));

  await waitFor(() => {
    expect(pageText()).toContain(URL_2);
  });
  expect(screen.getByRole("img")).toHaveAttribute("src", QR_2);
  const [, rotate] = calls(seen, "POST", "/api/v1/me/invite");
  expect(await rotate?.clone().json()).toEqual({ rotate: true });
});

test("Russian: the screen and its longest label", async () => {
  stubApi(() => ({ teachers: [lena()], students: [] }));

  await openScreen("ru");

  await screen.findByRole("button", { name: "Пригласить учеников" });
  expect(screen.getByRole("heading", { level: 1, name: "🏛 Шала" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 2, name: "Учителям и шалам" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Шала и занятия" })).toBeInTheDocument();
  expect(screen.queryByText("Учеников в списке нет.")).toBeNull();
  expect(screen.getByRole("button", { name: "Убрать…" })).toBeInTheDocument();
});

test("a failed load says so instead of an empty screen", async () => {
  stubApi(
    () => ({ teachers: [], students: [] }),
    (request) =>
      new URL(request.url).pathname === "/api/v1/me/links"
        ? json({ code: "unavailable" }, 503)
        : undefined,
  );

  await openScreen();

  await screen.findByRole("alert", {}, { timeout: 4000 });
  expect(pageText()).toContain("Couldn't load your lists.");
});

test("two long names still fit Telegram's 256-character popup", async () => {
  const long = "Я".repeat(64);
  stubApi(() => ({
    teachers: [lena({ name: long }), boris({ name: long })],
    students: [],
  }));
  await openScreen("ru");

  fireEvent.click((await screen.findAllByRole("button", { name: "Убрать…" }))[0] as HTMLElement);

  await waitFor(() => {
    expect(confirmDestructive).toHaveBeenCalledOnce();
  });
  const [message = ""] = confirmDestructive.mock.calls[0] ?? [];
  expect(message.length).toBeLessThanOrEqual(256);
});

// ID-07 (spec §2, §4): a teacher I named in a shala and wait for. One line with the name and the
// shala, and Withdraw. The line reads the same whatever the teacher did, so it carries no state,
// no date and no count.
describe("a teacher I asked", () => {
  const WAITING: LinksBody = { teachers: [lena()], students: [], asked: [asked(ANNA, "Anna")] };
  const reads = (text: string) => (found: string) => plain(found) === text;

  test("has a waiting line with the name and the shala", async () => {
    stubApi(() => WAITING);

    await openScreen();

    const line = await screen.findByText(reads("⏳ Waiting for an answer (Mysore Room)"));
    expect(line.closest(".card")).toBe(screen.getByText("Лена").closest(".card"));
    expect(screen.getByText("Anna")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Withdraw…" })).toBeInTheDocument();
    // Not a teacher on the list: no ⭐, and the one Remove is Лена's.
    expect(screen.getAllByRole("button", { name: "Remove…" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "⭐ Make main" })).toBeNull();
  });

  test("shows with no teacher on the list yet, and a missing name has the fallback", async () => {
    stubApi(() => ({ teachers: [], students: [], asked: [asked(ANNA, null)] }));

    await openScreen();

    await screen.findByText(reads("⏳ Waiting for an answer (Mysore Room)"));
    expect(pageText()).toContain("(no name)");
    expect(pageText()).not.toContain("Nobody here yet");
  });

  test("an older payload without the field shows no line", async () => {
    stubApi(() => ({ teachers: [lena()], students: [] }));

    await openScreen();

    await screen.findByText("Лена");
    expect(pageText()).not.toContain("Waiting");
    expect(screen.queryByRole("button", { name: "Withdraw…" })).toBeNull();
  });

  test("tells nothing but the name and the shala: no state, date or count", async () => {
    stubApi(() => ({
      teachers: [],
      students: [],
      asked: [asked(ANNA, "Anna"), asked(BORIS, "Boris")],
    }));

    await openScreen();

    await screen.findByText("Boris");
    const card = screen.getByText("Anna").closest(".card");
    const text = plain(card?.textContent);
    const lines = [
      "Anna",
      "Withdraw…",
      "⏳ Waiting for an answer (Mysore Room)",
      "Boris",
      "Withdraw…",
      "⏳ Waiting for an answer (Mysore Room)",
    ];
    expect(text).toBe(lines.join(""));
    expect(text).not.toMatch(/\d/);
    expect(text).not.toMatch(/declin|reject|refus|not your|no answer|expire|ago|since|day/i);
  });

  test("Withdraw: Cancel sends nothing", async () => {
    const seen = stubApi(() => WAITING);
    await openScreen();

    fireEvent.click(await screen.findByRole("button", { name: "Withdraw…" }));

    await waitFor(() => {
      expect(confirmDestructive).toHaveBeenCalledOnce();
    });
    const [message, ok, cancel] = confirmDestructive.mock.calls[0] ?? [];
    expect(plain(message)).toBe(
      "Withdraw your request to Anna? No one gets a message. " +
        "You can ask them again in about a month.",
    );
    expect(ok).toBe("Withdraw");
    expect(cancel).toBe("Cancel");
    expect(seen.filter((r) => r.method === "DELETE")).toHaveLength(0);
    expect(pageText()).toContain("Anna");
  });

  test("Withdraw: confirming deletes the request, and the line goes", async () => {
    confirmDestructive.mockResolvedValue(true);
    let withdrawn = false;
    const seen = stubApi(
      () => (withdrawn ? { ...WAITING, asked: [] } : WAITING),
      (request) => {
        if (request.method !== "DELETE") return undefined;
        withdrawn = true;
        return new Response(null, { status: 204 });
      },
    );
    await openScreen();

    fireEvent.click(await screen.findByRole("button", { name: "Withdraw…" }));

    await waitFor(() => {
      expect(screen.queryByText("Anna")).not.toBeInTheDocument();
    });
    expect(calls(seen, "DELETE", `/api/v1/me/teacher-requests/${ANNA}`)).toHaveLength(1);
    expect(seen.filter((r) => r.method === "DELETE")).toHaveLength(1);
    expect(pageText()).not.toContain("Waiting");
    expect(pageText()).toContain("Лена"); // the teacher on the list is untouched
  });

  test("a failed Withdraw says so and keeps the line", async () => {
    confirmDestructive.mockResolvedValue(true);
    stubApi(
      () => WAITING,
      (request) => (request.method === "DELETE" ? json({ code: "unavailable" }, 503) : undefined),
    );
    await openScreen();

    fireEvent.click(await screen.findByRole("button", { name: "Withdraw…" }));

    const line = await screen.findByRole("alert");
    expect(plain(line.textContent)).toBe("Couldn't save. Try again in a moment.");
    expect(screen.getByRole("button", { name: "Withdraw…" })).toBeEnabled();
  });

  test("the screen offers no way to ask a teacher: that stays in the bot", async () => {
    stubApi(() => WAITING);

    await openScreen();

    await screen.findByText("Anna");
    expect(screen.queryByRole("button", { name: /Ask a teacher|Pick/ })).toBeNull();
  });

  test("Russian, and two long names still fit Telegram's popup", async () => {
    const long = "Я".repeat(64);
    stubApi(() => ({ teachers: [], students: [], asked: [asked(ANNA, long)] }));
    await openScreen("ru");

    await screen.findByText(reads("⏳ Ждём ответа (Mysore Room)"));
    fireEvent.click(screen.getByRole("button", { name: "Отозвать…" }));

    await waitFor(() => {
      expect(confirmDestructive).toHaveBeenCalledOnce();
    });
    const [message = "", ok] = confirmDestructive.mock.calls[0] ?? [];
    expect(plain(message)).toMatch(/^Отозвать запрос: Я+…\? Сообщений никто не получит\. /);
    expect(message.length).toBeLessThanOrEqual(256);
    expect(ok).toBe("Отозвать");
  });
});

// UI-06 stage 4B (spec §3): the order for each kind of person. Each part shows only with
// something in it; the first row is the main one (▶, the filled button); the group is last.
describe("one list in a fixed order", () => {
  /** The root, top to bottom, one entry per part. */
  const outline = () => {
    const root = screen.getByRole("heading", { level: 1, name: "🏛 Shala" }).closest("main");
    if (!root) throw new Error("no root");
    return [...root.children].map((part) => {
      const text = plain(part.textContent);
      if (part.matches("h1")) return "heading";
      if (part.matches("button.btn")) return `▶ ${text}`;
      if (part.matches("button.row-button")) return text;
      if (part.matches("section.waiting")) return "[waiting for my answer]";
      if (part.matches("section.teachers")) return "[teachers]";
      if (part.matches("h2.starts")) return `${text}:`;
      if (part.matches("section.list"))
        return [...part.querySelectorAll(".lrow")].map((row) => plain(row.textContent));
      return text;
    });
  };
  const GROUP = ["For teachers and shalas:", ["Invite students", "Shala and classes"]];
  const settled = (last: string) =>
    screen.findByRole("button", { name: (name) => plain(name) === last });

  test("nobody: the line and the group", async () => {
    stubApi(() => ({ teachers: [], students: [] }));
    await openScreen();
    await settled("Shala and classes");

    expect(outline()).toEqual([
      "heading",
      "Nobody here yet. To add a teacher or join a shala, open the link they send you.",
      ...GROUP,
    ]);
  });

  test("a student of one shala with a teacher: My schedule leads, then the shala, the teacher", async () => {
    mine = [shalaOf(SHALA, "Mysore Room", "student")];
    stubApi(() => ({ teachers: [lena()], students: [] }));
    await openScreen();
    await settled("🗓 My schedule");

    expect(outline()).toEqual([
      "heading",
      "▶ 🗓 My schedule",
      "🏛 Mysore Room",
      "[teachers]",
      ...GROUP,
    ]);
    // The teacher's announcements are the card's last row.
    const card = document.querySelector("main .teachers") as HTMLElement;
    expect([...card.querySelectorAll("button")].at(-1)).toHaveAccessibleName("📣 Announcements");
  });

  test("a student who asked a teacher: the waiting line in the teachers card", async () => {
    mine = [shalaOf(SHALA, "Mysore Room", "student")];
    stubApi(() => ({ teachers: [], students: [], asked: [asked(ANNA, "Anna")] }));
    await openScreen();
    await settled("🗓 My schedule");

    await waitFor(() => {
      expect(outline()).toEqual([
        "heading",
        "▶ 🗓 My schedule",
        "🏛 Mysore Room",
        "[teachers]",
        ...GROUP,
      ]);
    });
    expect(screen.queryByRole("button", { name: "📣 Announcements" })).toBeNull(); // no teacher yet
  });

  test("a student of several shalas: one row per shala, no card title", async () => {
    mine = [shalaOf(SHALA, "Mysore Room", "student"), shalaOf(OTHER, "Ashtanga Almaty", "student")];
    stubApi(() => ({ teachers: [], students: [] }));
    await openScreen();
    await settled("🏛 Ashtanga Almaty");

    expect(outline()).toEqual([
      "heading",
      "▶ 🗓 My schedule",
      "🏛 Mysore Room",
      "🏛 Ashtanga Almaty",
      ...GROUP,
    ]);
  });

  test("a teacher with students and no shala: My students leads", async () => {
    stubApi(() => ({ teachers: [], students: [student(SHIVA, "Shiva")] }));
    await openScreen();
    await settled("👥 My students");

    expect(outline()).toEqual([
      "heading",
      "▶ 👥 My students",
      "For teachers and shalas:",
      ["➕ Invite students", "Shala and classes"],
    ]);
  });

  test("an owner with students: My schedule leads, My students after the shala", async () => {
    mine = [shalaOf(SHALA, "Mysore Room", "staff", true)];
    stubApi(() => ({ teachers: [], students: [student(SHIVA, "Shiva")] }));
    await openScreen();
    await settled("👥 My students");

    expect(outline()).toEqual([
      "heading",
      "▶ 🗓 My schedule",
      "🏛 Mysore Room",
      "👥 My students",
      "For teachers and shalas:",
      ["➕ Invite students", "Shala and classes"],
    ]);
  });

  test("a teacher who is also a student, with someone waiting: the union, the block first", async () => {
    mine = [shalaOf(SHALA, "Mysore Room", "student"), shalaOf(OTHER, "Ashtanga Almaty", "staff")];
    requests = () => [asks(OLGA, "Olga")];
    stubApi(() => ({ teachers: [lena()], students: [student(SHIVA, "Shiva")] }));
    await openScreen();
    await screen.findByRole("button", { name: "✅ Yes, my student" });

    expect(outline()).toEqual([
      "heading",
      "[waiting for my answer]",
      "▶ 🗓 My schedule",
      "🏛 Mysore Room",
      "🏛 Ashtanga Almaty",
      "[teachers]",
      "👥 My students",
      "For teachers and shalas:",
      ["➕ Invite students", "Shala and classes"],
    ]);
  });

  test("only one main row, and it is the first row", async () => {
    mine = [shalaOf(SHALA, "Mysore Room", "staff", true)];
    stubApi(() => ({ teachers: [lena()], students: [student(SHIVA, "Shiva")] }));
    await openScreen();
    await settled("👥 My students");

    const root = screen.getByRole("heading", { level: 1 }).closest("main") as HTMLElement;
    const mains = root.querySelectorAll("button.btn");
    expect(mains).toHaveLength(1);
    expect(within(root).getAllByRole("button")[0]).toBe(mains[0]);
  });

  // My schedule's row is App.test's ("Shala: My schedule is the first row…").
  test("a shala row opens that shala's card; Back returns to the list", async () => {
    mine = [shalaOf(SHALA, "Mysore Room", "student")];
    const seen = stubApi(
      () => ({ teachers: [], students: [] }),
      (request) =>
        new URL(request.url).pathname === `/api/v1/shalas/${SHALA}`
          ? json({ code: "not_found" }, 404)
          : undefined,
    );
    await openScreen();

    fireEvent.click(
      await screen.findByRole("button", { name: (n) => plain(n) === "🏛 Mysore Room" }),
    );

    await screen.findByText(
      "Couldn't load the shala. Try again in a moment.",
      {},
      { timeout: 4000 },
    );
    expect(calls(seen, "GET", `/api/v1/shalas/${SHALA}`).length).toBeGreaterThan(0);
    act(() => {
      telegram.back();
    });
    expect(
      await screen.findByRole("button", { name: (n) => plain(n) === "🏛 Mysore Room" }),
    ).toBeInTheDocument();
  });
});

// ID-05: the directory line's row is the group's last, by its own rule.
describe("the group: For teachers and shalas", () => {
  test("SYC directory listing is its last row while requests are taken", async () => {
    listing = { status: "none", available: true };
    stubApi(() => ({ teachers: [], students: [] }));
    await openScreen();

    const row = await screen.findByRole("button", { name: "SYC directory listing" });
    const list = row.closest("section") as HTMLElement;
    expect(within(list).getAllByRole("button").at(-1)).toBe(row);
  });

  test("no directory row when requests aren't taken and I have none", async () => {
    stubApi(() => ({ teachers: [], students: [] }));
    await openScreen();
    await screen.findByRole("button", { name: "Shala and classes" });

    expect(screen.queryByRole("button", { name: "SYC directory listing" })).toBeNull();
  });

  test("my own request keeps the row while requests aren't taken", async () => {
    listing = { status: "pending", available: false };
    stubApi(() => ({ teachers: [lena()], students: [] }));
    await openScreen();

    expect(await screen.findByRole("button", { name: "SYC directory listing" })).toBeVisible();
  });

  test("one thing open at a time: the form closes the invite", async () => {
    stubApi(() => ({ teachers: [], students: [] }));
    await openScreen();
    await openInvite();

    fireEvent.click(screen.getByRole("button", { name: "Shala and classes" }));

    expect(await screen.findByLabelText("Name")).toHaveFocus();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByRole("button", { name: "Invite students" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  test("the invite start (Today's next step) opens the invite under its row, asked once", async () => {
    const seen = stubApi(
      () => ({ teachers: [], students: [student(SHIVA, "Shiva")] }),
      (request) =>
        new URL(request.url).pathname === "/api/v1/me/next-steps"
          ? json({ steps: [{ kind: "invite_student", shala_id: null }] })
          : undefined,
    );
    await renderApp();

    fireEvent.click(await screen.findByRole("button", { name: "Open the invite" }));

    expect(await screen.findByRole("img", { name: "QR code for your invite link" })).toBeVisible();
    expect(screen.getByRole("button", { name: "➕ Invite students" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    // Last, under the people: the group's place does not change for a start.
    expect(
      screen
        .getByRole("button", { name: "👥 My students" })
        .compareDocumentPosition(screen.getByRole("img")),
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(calls(seen, "POST", "/api/v1/me/invite")).toHaveLength(1);
  });

  test("the create start (the bot's Create a shala) opens the form, ready to type", async () => {
    mine = [shalaOf(SHALA, "Mysore Room", "staff", true)];
    stubApi(() => ({ teachers: [], students: [] }));
    window.history.replaceState(null, "", "/?open=new-shala");
    try {
      vi.resetModules();
      const { App } = await import("../../App");
      render(<App locale="en" firstName="Ash" inTelegram />);

      expect(await screen.findByLabelText("Name")).toHaveFocus();
      expect(screen.getByRole("button", { name: "Shala and classes" })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
      expect(await screen.findByRole("button", { name: "🗓 My schedule" })).toBeInTheDocument();
      expect(screen.queryByText(/Nobody here yet/)).toBeNull();
    } finally {
      window.history.replaceState(null, "", "/");
    }
  });
});

// ID-07 (spec §5, QC): the people who named me as their teacher wait in a block at the top of
// the Shala tab. Each answer is one request; "Not my student" keeps its row for an Undo; the
// block, and its read, are there only when someone waits.
describe("the waiting block", () => {
  const TITLE = /Waiting for your answer|Ждут твоего ответа/;
  /** A name or a text that reads exactly so, whatever Fluent wrapped its numbers in. */
  const reads = (text: string) => (found: string) => plain(found) === text;
  const YES = "✅ Yes, my student";
  const NO = "Not my student";
  const UNDO = "↩️ Undo";
  /** The block, once it's drawn. */
  const block = async () => {
    const title = await screen.findByRole("heading", { level: 2, name: TITLE });
    const card = title.closest("section");
    if (!card) throw new Error("the waiting block is not a section");
    return within(card);
  };
  /** One person's row in the block. */
  const person = (name: string) => {
    const found = screen.getByText(name).closest("li");
    if (!found) throw new Error(`${name} has no row`);
    return within(found);
  };
  const posts = (seen: Request[], rest: string) => calls(seen, "POST", `${REQUESTS}/${rest}`);
  const TWO_WAIT = () => [asks(OLGA, "Olga"), asks(PAVEL, null)];
  /** A teacher with one student, Shiva. */
  const lists = (): LinksBody => ({ teachers: [], students: [student(SHIVA, "Shiva")] });

  test("is absent when nobody waits, and nothing reads who waits", async () => {
    const seen = stubApi(lists);

    await openScreen();

    await screen.findByRole("button", { name: "👥 My students" });
    expect(screen.queryByRole("heading", { level: 2, name: TITLE })).toBeNull();
    expect(screen.queryByRole("button", { name: TITLE })).toBeNull();
    expect(calls(seen, "GET", REQUESTS)).toHaveLength(0);
  });

  test("leads the tab, also with no student yet, and reads one page", async () => {
    requests = TWO_WAIT;
    const seen = stubApi(() => ({ teachers: [], students: [] }));

    await openScreen();

    const card = await block();
    expect(plain(card.getByRole("heading", { level: 2 }).textContent)).toBe(
      "⏳ Waiting for your answer (2)",
    );
    expect(screen.queryByText(/Nobody here yet/)).toBeNull();
    expect(screen.queryByRole("button", { name: "👥 My students" })).toBeNull();
    const read = calls(seen, "GET", REQUESTS)[0];
    expect(new URL(read?.url ?? "").search).toBe("?offset=0&limit=50");
  });

  test("shows each person with their shala and both answers", async () => {
    requests = TWO_WAIT;
    stubApi(lists);

    await openScreen();

    const card = await block();
    expect(person("Olga").getByText("Mysore Room")).toBeInTheDocument();
    expect(person("(no name)").getByText("Mysore Room")).toBeInTheDocument();
    expect(card.getAllByRole("button", { name: YES })).toHaveLength(2);
    expect(card.getAllByRole("button", { name: NO })).toHaveLength(2);
    expect(
      card.getByText(
        'Confirm only people you know. If you tap "Not my student", the person isn\'t told.',
      ),
    ).toBeInTheDocument();
  });

  test("shows a name, a shala and nothing else about the person", async () => {
    requests = () => [asks(OLGA, "Olga")];
    stubApi(lists);

    await openScreen();

    const text = plain((await block()).getByRole("list").textContent);
    expect(text).toBe(`OlgaMysore Room${YES}${NO}`);
  });

  test("Yes, my student: one request, then My students is there", async () => {
    let waiting = TWO_WAIT();
    let students: Student[] = [];
    requests = () => waiting;
    const seen = stubApi(
      () => ({ teachers: [], students }),
      (request) => {
        if (new URL(request.url).pathname !== `${REQUESTS}/${OLGA}/approve`) return undefined;
        waiting = waiting.filter((w) => w.student_id !== OLGA);
        students = [student(OLGA, "Olga")];
        return new Response(null, { status: 204 });
      },
    );
    await openScreen();
    await block();

    fireEvent.click(person("Olga").getByRole("button", { name: YES }));

    expect(await screen.findByRole("button", { name: "👥 My students" })).toBeInTheDocument();
    expect(posts(seen, `${OLGA}/approve`)).toHaveLength(1);
    expect(plain(screen.getByRole("status").textContent)).toBe(
      "👥 Olga is on your list of students now.",
    );
    const card = await block();
    await waitFor(() => {
      expect(plain(card.getByRole("heading", { level: 2 }).textContent)).toBe(
        "⏳ Waiting for your answer (1)",
      );
    });
    expect(card.getAllByRole("button", { name: YES })).toHaveLength(1);
    expect(confirmAction).not.toHaveBeenCalled(); // one person needs no second question
  });

  test("Not my student: the row stays with an Undo, and Undo brings the answers back", async () => {
    let waiting = TWO_WAIT();
    requests = () => waiting;
    const seen = stubApi(lists, (request) => {
      const path = new URL(request.url).pathname;
      if (path === `${REQUESTS}/${OLGA}/decline`) {
        waiting = waiting.filter((w) => w.student_id !== OLGA);
      } else if (path === `${REQUESTS}/${OLGA}/reopen`) {
        waiting = TWO_WAIT();
      }
      return undefined;
    });
    await openScreen();
    await block();

    fireEvent.click(person("Olga").getByRole("button", { name: NO }));

    const undo = await screen.findByRole("button", { name: UNDO });
    expect(posts(seen, `${OLGA}/decline`)).toHaveLength(1);
    expect(
      person("Olga").getByText(reads("Noted: not your student. Olga isn't told.")),
    ).toBeVisible();
    expect(person("Olga").queryByRole("button", { name: YES })).toBeNull();
    expect(person("Olga").queryByRole("button", { name: NO })).toBeNull();
    // Still the first row: it does not jump under the others.
    expect(plain(screen.getAllByRole("listitem")[0]?.textContent)).toContain("Olga");
    await waitFor(() => {
      expect(pageText()).toContain("⏳ Waiting for your answer (1)");
    });

    fireEvent.click(undo);

    await person("Olga").findByRole("button", { name: YES });
    expect(posts(seen, `${OLGA}/reopen`)).toHaveLength(1);
    expect(screen.queryByRole("button", { name: UNDO })).toBeNull();
    await waitFor(() => {
      expect(pageText()).toContain("⏳ Waiting for your answer (2)");
    });
  });

  test("the last person answered with Not my student keeps the Undo on screen", async () => {
    let waiting = [asks(OLGA, "Olga")];
    requests = () => waiting;
    const seen = stubApi(lists, (request) => {
      if (new URL(request.url).pathname === `${REQUESTS}/${OLGA}/decline`) waiting = [];
      return undefined;
    });
    await openScreen();
    await block();

    fireEvent.click(person("Olga").getByRole("button", { name: NO }));

    await screen.findByRole("button", { name: UNDO });
    await screen.findByRole("heading", { level: 2, name: "No one is waiting for your answer." });
    // The lists were read again (nobody waits now) and the block stayed.
    await waitFor(() => {
      expect(calls(seen, "GET", "/api/v1/me/links").length).toBeGreaterThan(1);
    });
    expect(screen.getByRole("button", { name: UNDO })).toBeVisible();
    expect(pageText()).not.toContain("(0)");
  });

  test("leaving the tab ends the Undo: back on it, nobody waits and there is no block", async () => {
    let waiting = [asks(OLGA, "Olga")];
    requests = () => waiting;
    stubApi(lists, (request) => {
      if (new URL(request.url).pathname === `${REQUESTS}/${OLGA}/decline`) waiting = [];
      return undefined;
    });
    await openScreen();
    await block();
    fireEvent.click(person("Olga").getByRole("button", { name: NO }));
    await screen.findByRole("button", { name: UNDO });

    fireEvent.click(await screen.findByRole("button", { name: "👥 My students" }));
    await screen.findByText(/own time zone/);
    act(() => {
      telegram.back();
    });

    await screen.findByRole("button", { name: "👥 My students" });
    expect(screen.queryByRole("button", { name: UNDO })).toBeNull();
    expect(screen.queryByRole("heading", { level: 2, name: TITLE })).toBeNull();
  });

  test("Confirm all shows only when more than one waits", async () => {
    requests = () => [asks(OLGA, "Olga")];
    stubApi(lists);

    await openScreen();

    await block();
    expect(screen.queryByRole("button", { name: /Confirm all/ })).toBeNull();
  });

  test("Confirm all asks first, and Cancel sends nothing", async () => {
    requests = TWO_WAIT;
    const seen = stubApi(lists);
    await openScreen();

    fireEvent.click((await block()).getByRole("button", { name: reads("✅ Confirm all (2)") }));

    await waitFor(() => {
      expect(confirmAction).toHaveBeenCalledTimes(1);
    });
    const [message, ok, cancel] = confirmAction.mock.calls[0] ?? [];
    expect(plain(message)).toBe(
      "Confirm all 2 people as your students? Confirm only if you know each of them.",
    );
    expect(ok).toBe("✅ Yes, confirm all");
    expect(cancel).toBe("Cancel");
    expect(posts(seen, "approve-all")).toHaveLength(0);
    expect(screen.getAllByRole("button", { name: YES })).toHaveLength(2);
  });

  test("confirming sends the list's moment back unchanged and says how many", async () => {
    confirmAction.mockResolvedValue(true);
    let waiting = TWO_WAIT();
    let students: Student[] = [];
    requests = () => waiting;
    const seen = stubApi(
      () => ({ teachers: [], students }),
      (request) => {
        if (new URL(request.url).pathname !== `${REQUESTS}/approve-all`) return undefined;
        waiting = [];
        students = [student(OLGA, "Olga"), student(PAVEL, null)];
        return json({ approved: 2, left: 0 });
      },
    );
    await openScreen();

    fireEvent.click((await block()).getByRole("button", { name: reads("✅ Confirm all (2)") }));

    await screen.findByText(reads("✅ 2 students are on your list now."));
    const [sent] = posts(seen, "approve-all");
    expect(await sent?.json()).toEqual({ as_of: AS_OF });
    await screen.findByRole("button", { name: "👥 My students" });
    await waitFor(() => {
      expect(screen.queryByRole("heading", { level: 2, name: TITLE })).toBeNull();
    });
  });

  test("request_gone: a short line, and the list is read again", async () => {
    let waiting = TWO_WAIT();
    requests = () => waiting;
    const seen = stubApi(lists, (request) => {
      if (new URL(request.url).pathname !== `${REQUESTS}/${OLGA}/approve`) return undefined;
      waiting = waiting.filter((w) => w.student_id !== OLGA);
      return json({ code: "request_gone" }, 404);
    });
    await openScreen();
    await block();

    fireEvent.click(person("Olga").getByRole("button", { name: YES }));

    await screen.findByText(
      "This request is no longer open. If this is your student, send them your own link.",
    );
    await waitFor(() => {
      expect(screen.queryByText("Olga")).toBeNull();
    });
    expect(calls(seen, "GET", REQUESTS)).toHaveLength(2);
    expect(screen.queryByRole("alert")).toBeNull(); // quiet: nothing went wrong on this side
    expect(screen.getAllByRole("button", { name: YES })).toHaveLength(1);
  });

  test("request_gone on Undo drops the row with the same line", async () => {
    let waiting = [asks(OLGA, "Olga")];
    requests = () => waiting;
    stubApi(lists, (request) => {
      const path = new URL(request.url).pathname;
      if (path === `${REQUESTS}/${OLGA}/decline`) waiting = [];
      if (path === `${REQUESTS}/${OLGA}/reopen`) return json({ code: "request_gone" }, 404);
      return undefined;
    });
    await openScreen();
    await block();
    fireEvent.click(person("Olga").getByRole("button", { name: NO }));

    fireEvent.click(await screen.findByRole("button", { name: UNDO }));

    await screen.findByText(
      "This request is no longer open. If this is your student, send them your own link.",
    );
    expect(screen.queryByText("Olga")).toBeNull();
    expect(screen.queryByRole("button", { name: UNDO })).toBeNull();
  });

  test("list_full: a short line, and the row stays", async () => {
    requests = TWO_WAIT;
    const seen = stubApi(lists, (request) =>
      new URL(request.url).pathname === `${REQUESTS}/${OLGA}/approve`
        ? json({ code: "list_full" }, 409)
        : undefined,
    );
    await openScreen();
    await block();

    fireEvent.click(person("Olga").getByRole("button", { name: YES }));

    const line = await screen.findByRole("alert");
    expect(plain(line.textContent)).toBe(
      "This can't be confirmed right now: a list of students or teachers is full. " +
        "The request stays waiting.",
    );
    expect(posts(seen, `${OLGA}/approve`)).toHaveLength(1);
    expect(person("Olga").getByRole("button", { name: YES })).toBeEnabled();
    expect(pageText()).toContain("⏳ Waiting for your answer (2)");
  });

  test("a failed answer says so and keeps the row", async () => {
    requests = TWO_WAIT;
    stubApi(lists, (request) =>
      new URL(request.url).pathname === `${REQUESTS}/${OLGA}/decline`
        ? json({ code: "unavailable" }, 503)
        : undefined,
    );
    await openScreen();
    await block();

    fireEvent.click(person("Olga").getByRole("button", { name: NO }));

    const line = await screen.findByRole("alert");
    expect(plain(line.textContent)).toBe("Couldn't save. Try again in a moment.");
    expect(person("Olga").getByRole("button", { name: NO })).toBeEnabled();
    expect(screen.queryByRole("button", { name: UNDO })).toBeNull();
  });

  test("a failed load says so, and the rest of the tab still shows", async () => {
    requests = TWO_WAIT;
    stubApi(lists, (request) =>
      new URL(request.url).pathname === REQUESTS ? json({ code: "unavailable" }, 503) : undefined,
    );

    await openScreen();

    const line = await screen.findByRole("alert", {}, { timeout: 4000 });
    expect(plain(line.textContent)).toBe("Couldn't load who is waiting. Try again in a moment.");
    expect(screen.getByRole("button", { name: "👥 My students" })).toBeInTheDocument();
  });

  test("Show more reads the next page of people", async () => {
    const many = Array.from({ length: 60 }, (_, n) =>
      asks(`00000000-0000-0000-0000-${String(n).padStart(12, "0")}`, `Person ${String(n + 1)}`),
    );
    requests = () => many;
    const seen = stubApi(lists);
    await openScreen();
    const card = await block();
    expect(card.getAllByRole("listitem")).toHaveLength(50);
    expect(pageText()).toContain("⏳ Waiting for your answer (60)");

    fireEvent.click(card.getByRole("button", { name: "Show more" }));

    await screen.findByText("Person 60");
    expect(card.getAllByRole("listitem")).toHaveLength(60);
    expect(new URL(calls(seen, "GET", REQUESTS)[1]?.url ?? "").search).toBe("?offset=50&limit=50");
    expect(card.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  test("Russian, with a long name on one line at 320 px", async () => {
    const long = "Я".repeat(64);
    requests = () => [asks(OLGA, long), asks(PAVEL, "Павел")];
    stubApi(lists);

    await openScreen("ru");

    const card = await block();
    expect(plain(card.getByRole("heading", { level: 2 }).textContent)).toBe(
      "⏳ Ждут твоего ответа (2)",
    );
    expect(card.getAllByRole("button", { name: "✅ Да, мой ученик" })).toHaveLength(2);
    expect(card.getAllByRole("button", { name: "Не мой ученик" })).toHaveLength(2);
    expect(pageText()).toContain(
      "Подтверждай только тех, кого знаешь. Если нажать «Не мой ученик», человек об этом не узнает.",
    );
    // jsdom has no layout, so this pins the mechanism (as My students' own test does).
    const { readFileSync } = process.getBuiltinModule("node:fs");
    const css = readFileSync(`${process.cwd()}/src/theme/tokens.css`, "utf8").replace(
      /\/\*[\s\S]*?\*\//g,
      "",
    );
    const rules = [...css.matchAll(/([^{}]+)\{([^}]*text-overflow:\s*ellipsis[^}]*)\}/g)];
    const selectors = rules.map((rule) => (rule[1] ?? "").trim()).filter(Boolean);
    expect(selectors.some((selector) => card.getByText(long).matches(selector))).toBe(true);

    fireEvent.click(card.getByRole("button", { name: reads("✅ Подтвердить всех (2)") }));
    await waitFor(() => {
      expect(confirmAction).toHaveBeenCalledTimes(1);
    });
    const [message, ok, cancel] = confirmAction.mock.calls[0] ?? [];
    expect(plain(message)).toBe(
      "Подтвердить всех как своих учеников? В списке: 2. Подтверждай, только если знаешь каждого.",
    );
    expect(ok).toBe("✅ Да, подтвердить всех");
    expect(cancel).toBe("Отмена");
  });

  test("Russian: Not my student and its Undo", async () => {
    let waiting = TWO_WAIT();
    requests = () => waiting;
    stubApi(lists, (request) => {
      if (new URL(request.url).pathname === `${REQUESTS}/${OLGA}/decline`) {
        waiting = waiting.filter((w) => w.student_id !== OLGA);
      }
      return undefined;
    });
    await openScreen("ru");
    await block();

    fireEvent.click(person("Olga").getByRole("button", { name: "Не мой ученик" }));

    await screen.findByRole("button", { name: "↩️ Отменить" });
    expect(pageText()).toContain("Отмечено: не твой ученик. Olga об этом не узнает.");
  });

  test.each([
    [1, "✅ 1 ученик теперь в твоём списке."],
    [2, "✅ 2 ученика теперь в твоём списке."],
    [5, "✅ 5 учеников теперь в твоём списке."],
  ])("Russian: Confirm all counts %i through Fluent", async (approved, line) => {
    confirmAction.mockResolvedValue(true);
    requests = TWO_WAIT;
    stubApi(lists, (request) =>
      new URL(request.url).pathname === `${REQUESTS}/approve-all`
        ? json({ approved, left: 0 })
        : undefined,
    );
    await openScreen("ru");

    fireEvent.click(
      (await block()).getByRole("button", { name: reads("✅ Подтвердить всех (2)") }),
    );

    await screen.findByText(reads(line));
  });
});

describe("the chunk", () => {
  test("the Shala tab is lazy, so initial JS gains nothing from it", () => {
    expect(shellSource).toMatch(/lazyRetry\(\(\) => import\("\.\.\/screens\/shalas\/ShalaTab"\)\)/);
    expect(shellSource).not.toMatch(/^import .*shalas\/ShalaTab/m);
  });
});
