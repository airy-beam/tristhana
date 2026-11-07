import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

// ID-04 (spec §2, §4): the 👥 Settings row opens a lazy screen with the bot's three parts and
// its ⭐ and takeover rules. Writes wait for the server, a 409 refetches, the QR comes from the
// API, and the link is never built here. Driven through App, so the file doesn't care where
// the screen lives. App keeps one QueryClient per module, so each test imports a fresh App.

const telegram = vi.hoisted(() => ({
  openSettings: vi.fn() as () => void,
  confirmDestructive: vi.fn<(message: string, ok: string, cancel: string) => Promise<boolean>>(),
  openTelegramLink: vi.fn<(url: string) => void>(),
}));
const { confirmDestructive, openTelegramLink } = telegram;

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  markReady: vi.fn(),
  useMainButton: vi.fn(),
  useSettingsButton: (open: () => void) => {
    telegram.openSettings = open;
  },
  enableClosingConfirmation: vi.fn(),
  disableClosingConfirmation: vi.fn(),
  confirmDestructive: telegram.confirmDestructive,
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
interface LinksBody {
  teachers: Teacher[];
  students: Student[];
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

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function background(path: string): unknown {
  if (path === "/api/v1/me") return ME;
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

/** Serves `links`; `answer` may take over a write. Every API request lands in the result. */
function stubApi(links: () => LinksBody, answer: Answer = () => undefined): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request.clone());
      const custom = await answer(request);
      if (custom) return custom;
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/me/links") return json(links());
      if (path === "/api/v1/me/invite") return json({ url: URL_1, qr: QR_1 });
      if (request.method === "DELETE") return new Response(null, { status: 204 });
      return json(background(path));
    }),
  );
  return seen;
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
const pageText = () => plain(document.body.textContent);
const calls = (seen: Request[], method: string, path: string) =>
  seen.filter((r) => r.method === method && new URL(r.url).pathname === path);

const homeLoaded = () => screen.findByRole("button", { name: /^⚙️ / });

async function renderApp(locale: "en" | "ru" = "en") {
  vi.resetModules();
  const { App } = await import("../../App");
  render(<App locale={locale} firstName="Ash" inTelegram />);
  await homeLoaded();
}

async function openScreen(locale: "en" | "ru" = "en") {
  await renderApp(locale);
  act(() => {
    telegram.openSettings();
  });
  const row = locale === "en" ? "👥 Teachers and students" : "👥 Учителя и ученики";
  fireEvent.click(await screen.findByRole("button", { name: row }));
  await waitFor(() => {
    expect(screen.queryByRole("button", { name: row })).not.toBeInTheDocument();
  });
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("onboard.tour", "1");
  confirmDestructive.mockReset();
  confirmDestructive.mockResolvedValue(false);
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

test("the Settings row opens the lazy screen, and Home has no row", async () => {
  const seen = stubApi(() => TWO);
  await renderApp();
  expect(screen.queryByRole("button", { name: "👥 Teachers and students" })).toBeNull();
  expect(calls(seen, "GET", "/api/v1/me/links")).toHaveLength(0);

  act(() => {
    telegram.openSettings();
  });
  fireEvent.click(await screen.findByRole("button", { name: "👥 Teachers and students" }));

  await screen.findByText("Лена");
  expect(screen.getByRole("heading", { name: "👥 Teachers and students" })).toBeInTheDocument();
  expect(calls(seen, "GET", "/api/v1/me/links")).toHaveLength(1);
});

test("both lists, with a fallback for no name", async () => {
  stubApi(() => ({
    teachers: [lena(), teacher(BORIS, null)],
    students: [student(SHIVA, "Shiva")],
  }));

  await openScreen();

  await screen.findByText("Shiva");
  expect(pageText()).toContain("Лена");
  expect(pageText()).toContain("(no name)");
});

test("empty states say so without a nudge", async () => {
  stubApi(() => ({ teachers: [], students: [] }));

  await openScreen();

  await screen.findByText("No teachers on your list. Your log works the same either way.");
  expect(screen.getByText("No students on your list.")).toBeInTheDocument();
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

test("removing a student confirms with the student's own words", async () => {
  confirmDestructive.mockResolvedValue(true);
  const seen = stubApi(() => ({ teachers: [], students: [student(SHIVA, "Shiva")] }));
  await openScreen();

  fireEvent.click(await screen.findByRole("button", { name: "Remove…" }));

  await waitFor(() => {
    expect(calls(seen, "DELETE", `/api/v1/me/students/${SHIVA}`)).toHaveLength(1);
  });
  const [message] = confirmDestructive.mock.calls[0] ?? [];
  expect(plain(message)).toBe("Remove Shiva from your students? They won't get a message.");
});

test("a teacher's view of a student shows no primary marks", async () => {
  stubApi(() => ({ teachers: [], students: [student(SHIVA, "Shiva")] }));

  await openScreen();

  await screen.findByText("Shiva");
  expect(pageText()).not.toContain("⭐");
  expect(pageText().toLowerCase()).not.toContain("main teacher");
});

test("with 0 students the invite button is the 'I teach' label", async () => {
  stubApi(() => ({ teachers: [lena()], students: [] }));

  await openScreen();

  await screen.findByRole("button", { name: "I teach: invite students" });
  expect(screen.queryByRole("button", { name: "➕ Invite students" })).toBeNull();
});

test("with students the button is the plain invite", async () => {
  stubApi(() => ({ teachers: [], students: [student(SHIVA, "Shiva")] }));

  await openScreen();

  await screen.findByRole("button", { name: "➕ Invite students" });
  expect(screen.queryByRole("button", { name: "I teach: invite students" })).toBeNull();
});

async function openInvite() {
  fireEvent.click(await screen.findByRole("button", { name: "I teach: invite students" }));
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

  await screen.findByRole("button", { name: "Я преподаю: пригласить учеников" });
  expect(screen.getByRole("heading", { name: "👥 Учителя и ученики" })).toBeInTheDocument();
  expect(screen.getByText("Учеников в списке нет.")).toBeInTheDocument();
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
