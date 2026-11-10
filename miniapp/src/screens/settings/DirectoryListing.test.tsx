import { FluentBundle, FluentResource } from "@fluent/bundle";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import enApp from "../../locales/en/app.ftl?raw";
import ruApp from "../../locales/ru/app.ftl?raw";
import enListing from "../../locales/en/listing.ftl?raw";
import ruListing from "../../locales/ru/listing.ftl?raw";
import { checkedMonth } from "./listing";

// ID-05 (spec §2, §3, §11, §12a): the "listed in the SYC directory" line. A teacher asks for it
// in a lazy form; a student sees it as its own element under the teacher's name, with the
// self-declared level only behind a tap. A teacher without the line looks complete. Driven
// through App (one QueryClient per module, so each test imports a fresh App).

// Node's, at test time only (the app's types have no `process`).
declare const process: { env: Record<string, string | undefined> };

const telegram = vi.hoisted(() => ({
  openSettings: vi.fn() as () => void,
  confirmDestructive: vi.fn<(message: string, ok: string, cancel: string) => Promise<boolean>>(),
  confirmAction: vi.fn<(message: string, ok: string, cancel: string) => Promise<boolean>>(),
  mainButton: false,
  main: null as { text: string; press: () => void; loading: boolean; visible: boolean } | null,
}));
const { confirmDestructive, confirmAction } = telegram;

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  markReady: vi.fn(),
  mainButtonAvailable: () => telegram.mainButton,
  useMainButton: (text: string, press: () => void, loading = false, visible = true) => {
    telegram.main = { text, press, loading, visible };
  },
  useSettingsButton: (open: () => void) => {
    telegram.openSettings = open;
  },
  enableClosingConfirmation: vi.fn(),
  disableClosingConfirmation: vi.fn(),
  confirmDestructive: telegram.confirmDestructive,
  confirmAction: telegram.confirmAction,
  allowBotMessages: vi.fn(() => Promise.resolve(false)),
  closeApp: vi.fn(),
  openTelegramLink: vi.fn(),
}));

const TODAY = "2026-11-11";
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
const PATH = "/api/v1/me/directory-listing";

type Level = "authorised" | "authorised-1" | "authorised-2" | "certified";
interface Mark {
  name_as_listed: string;
  checked_on: string;
  declared_level: Level | null;
}
interface Teacher {
  id: string;
  name: string | null;
  primary: boolean;
  primary_chosen: boolean;
  linked_at: string;
  listing: Mark | null;
}
interface ListingBody {
  status: "none" | "pending" | "listed" | "not_found" | "withdrawn";
  name_as_listed: string | null;
  region: string | null;
  declared_level: Level | null;
  note: string | null;
  requested_at: string | null;
  checked_on: string | null;
  can_send: boolean;
  available: boolean;
}

const teacher = (id: string, name: string, mark: Mark | null = null): Teacher => ({
  id,
  name,
  primary: id === LENA,
  primary_chosen: false,
  linked_at: "2026-11-01T06:00:00Z",
  listing: mark,
});
const MARK: Mark = {
  name_as_listed: "Anna Petrova",
  checked_on: "2026-11-01",
  declared_level: "authorised-2",
};

const listing = (over: Partial<ListingBody> = {}): ListingBody => ({
  status: "none",
  name_as_listed: null,
  region: null,
  declared_level: null,
  note: null,
  requested_at: null,
  checked_on: null,
  can_send: true,
  available: true,
  ...over,
});
const PENDING = listing({
  status: "pending",
  name_as_listed: "Anna Petrova",
  region: "Kazakhstan",
  declared_level: "authorised-2",
  note: "annayoga.example",
  requested_at: "2026-11-10T06:00:00Z",
});
const LISTED = listing({
  status: "listed",
  name_as_listed: "Anna Petrova",
  region: "Kazakhstan",
  declared_level: "authorised-2",
  requested_at: "2026-10-30T06:00:00Z",
  checked_on: "2026-11-01",
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let accountLocale: "en" | "ru" = "en";

function background(path: string): unknown {
  if (path === "/api/v1/me" || path === "/api/v1/me/device-timezone") {
    return { ...ME, locale: accountLocale };
  }
  if (path === "/api/v1/health") return { version: "1", commit: "abcdef0" };
  if (path === "/api/v1/moon/cities" || path === "/api/v1/me/shalas") return [];
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

interface Server {
  /** What GET answers now; a Response stands for an error. */
  listing: ListingBody | Response;
  teachers?: Teacher[];
  /** Takes over a PUT; by default the request becomes `pending` with the sent values. */
  put?: (body: Record<string, unknown>) => Response;
}

/** A small stand-in for the API. Every request lands in the result. */
function stubApi(server: Server): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request.clone());
      const path = new URL(request.url).pathname;
      if (path === PATH && request.method === "GET") {
        return server.listing instanceof Response ? server.listing.clone() : json(server.listing);
      }
      if (path === PATH && request.method === "PUT") {
        const body = (await request.json()) as Record<string, unknown>;
        if (server.put) return server.put(body);
        const before = server.listing instanceof Response ? listing() : server.listing;
        const same = before.name_as_listed === body.name_as_listed && before.region === body.region;
        server.listing = {
          ...before,
          ...(body as Partial<ListingBody>),
          status: before.status === "listed" && same ? "listed" : "pending",
          requested_at: before.requested_at ?? "2026-11-11T06:00:00Z",
        };
        return json(server.listing);
      }
      if (path === PATH && request.method === "DELETE") {
        server.listing = listing({ status: "withdrawn", can_send: false });
        return new Response(null, { status: 204 });
      }
      if (path === "/api/v1/me/links") {
        return json({ teachers: server.teachers ?? [], students: [] });
      }
      return json(background(path));
    }),
  );
  return seen;
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
const pageText = () => plain(document.body.textContent);
/** A text or name matcher that ignores Fluent's isolation marks around variables. */
const says = (want: string | RegExp) => (content: string) => {
  const text = plain(content);
  return typeof want === "string" ? text === want : want.test(text);
};
const calls = (seen: Request[], method: string) =>
  seen.filter((r) => r.method === method && new URL(r.url).pathname === PATH);
const sent = async (seen: Request[]) =>
  Promise.all(calls(seen, "PUT").map((r) => r.clone().json() as Promise<unknown>));

const NAME = "Name, exactly as in the directory";
const REGION = "Country or region, as in the directory";
const LEVEL = "Level (optional)";
const NOTE = "How can we tell it's you? (optional)";
const INTRO = /^If your name is in the Sharath Yoga Centre teachers directory/;
const LINE_EN =
  "✔ Listed in the Sharath Yoga Centre teachers directory as Anna Petrova (checked: November 2026)";
const LINE_RU = "✔ Anna Petrova — в списке учителей Sharath Yoga Centre (сверено: ноябрь 2026)";
const ABOUT_EN = /^The name is in the public teachers directory of Sharath Yoga Centre \(SYC\)/;

async function renderApp(locale: "en" | "ru" = "en") {
  accountLocale = locale;
  vi.resetModules();
  const { App } = await import("../../App");
  render(<App locale={locale} firstName="Ash" inTelegram />);
}

/** Settings → 👥 Teachers and students. */
async function openLinks(locale: "en" | "ru" = "en") {
  await renderApp(locale);
  await screen.findByRole("button", { name: /^⚙️ / });
  act(() => {
    telegram.openSettings();
  });
  const row = locale === "en" ? "👥 Teachers and students" : "👥 Учителя и ученики";
  fireEvent.click(await screen.findByRole("button", { name: row }));
  await screen.findByRole("heading", { name: row });
}

/** The form's screen, as the bot's `[Open the app]` opens it. */
async function openListing(locale: "en" | "ru" = "en") {
  window.history.replaceState(null, "", "/?open=listing");
  await renderApp(locale);
  await screen.findByRole("heading", {
    name: locale === "en" ? "SYC directory listing" : "Строка о списке SYC",
  });
}

const type = (label: string, value: string) => {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
};
const value = (label: string) =>
  screen.getByLabelText<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(label).value;

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("onboard.tour", "1");
  telegram.mainButton = false;
  telegram.main = null;
  confirmDestructive.mockReset();
  confirmDestructive.mockResolvedValue(false);
  confirmAction.mockReset();
  confirmAction.mockResolvedValue(false);
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
  window.history.replaceState(null, "", "/");
});

describe("the way in", () => {
  test("a quiet row in the invite part opens the form", async () => {
    stubApi({ listing: listing() });

    await openLinks();
    const row = await screen.findByRole("button", { name: "SYC directory listing" });
    const invite = screen.getByRole("button", { name: "I teach: invite students" });
    expect(invite.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(row);

    await screen.findByText(says(INTRO));
    expect(screen.getByLabelText(NAME)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "👥 Teachers and students" })).toBeNull();
  });

  test("requests aren't taken (available false): the row is hidden, on a 200", async () => {
    const seen = stubApi({
      listing: listing({ available: false }),
      teachers: [teacher(LENA, "Лена")],
    });

    await openLinks();
    await screen.findByText(says("Лена"));
    await waitFor(() => {
      expect(calls(seen, "GET")).toHaveLength(1);
    });
    await screen.findByRole("button", { name: "I teach: invite students" });

    expect(screen.queryByRole("button", { name: "SYC directory listing" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("available false with a line of my own: I can open it and remove it, never edit", async () => {
    const LISTED_OFF = listing({
      status: "listed",
      name_as_listed: "Anna Petrova",
      region: "Kazakhstan",
      checked_on: "2026-11-01",
      available: false,
    });
    const seen = stubApi({ listing: LISTED_OFF, teachers: [teacher(LENA, "Лена")] });

    await openLinks();
    fireEvent.click(await screen.findByRole("button", { name: "SYC directory listing" }));

    await screen.findByText(says(LINE_EN));
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByLabelText(NAME)).toBeNull();
    confirmDestructive.mockResolvedValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Remove…" }));
    await waitFor(() => {
      expect(calls(seen, "DELETE")).toHaveLength(1);
    });
  });

  test("a failed load (503) hides the row, and the screen shows no error", async () => {
    const seen = stubApi({
      listing: json({ code: "unavailable" }, 503),
      teachers: [teacher(LENA, "Лена")],
    });

    await openLinks();
    await screen.findByText(says("Лена"));
    await waitFor(() => {
      expect(calls(seen, "GET")).toHaveLength(1);
    });
    await screen.findByRole("button", { name: "I teach: invite students" });

    expect(screen.queryByRole("button", { name: "SYC directory listing" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(calls(seen, "GET")).toHaveLength(1); // no retry
  });

  test("?open=listing opens the form directly", async () => {
    const seen = stubApi({ listing: listing() });

    await openListing();

    await screen.findByLabelText(NAME);
    expect(screen.getByText(says(INTRO))).toBeInTheDocument();
    expect(calls(seen, "GET")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /^⚙️ / })).toBeNull();
  });
});

describe("the form", () => {
  test("says who sees the name, and that the directory isn't everything", async () => {
    stubApi({ listing: listing() });

    await openListing();
    await screen.findByLabelText(NAME);

    expect(screen.getByText(says("Students will see this name in the line."))).toBeInTheDocument();
    expect(pageText()).toContain("Many experienced teachers are not in this directory");
    expect(pageText()).toContain("everything here works the same without the line");
    expect(pageText()).toContain("it can take a few days");
    expect(pageText()).toContain("Only the person who checks sees it");
    expect(screen.getByLabelText(NAME)).toHaveAttribute("maxlength", "100");
    expect(screen.getByLabelText(REGION)).toHaveAttribute("maxlength", "60");
    expect(screen.getByLabelText(NOTE)).toHaveAttribute("maxlength", "300");
    expect(
      within(screen.getByLabelText(LEVEL))
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual([
      "Not stated",
      "Authorised",
      "Authorised Level 1",
      "Authorised Level 2",
      "Certified",
    ]);
  });

  test("an empty name or region gets a hint by its field, and nothing is sent", async () => {
    const seen = stubApi({ listing: listing() });

    await openListing();
    await screen.findByLabelText(NAME);
    type(NAME, "   ");
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText(
      says("Write the name as the directory shows it, up to 100 characters."),
    );
    expect(
      screen.getByText(
        says("Write the country or region as the directory shows it, up to 60 characters."),
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(NAME)).toHaveAttribute("aria-invalid", "true");
    expect(calls(seen, "PUT")).toHaveLength(0);

    type(NAME, "Anna Petrova");
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => {
      expect(screen.getByLabelText(NAME)).toHaveAttribute("aria-invalid", "false");
    });
    expect(screen.getByLabelText(REGION)).toHaveAttribute("aria-invalid", "true");
    expect(calls(seen, "PUT")).toHaveLength(0);
  });

  test("sending shows that a person will look it up", async () => {
    const seen = stubApi({ listing: listing() });

    await openListing();
    await screen.findByLabelText(NAME);
    type(NAME, " Anna Petrova ");
    type(REGION, "Kazakhstan");
    type(LEVEL, "authorised-2");
    type(NOTE, "annayoga.example");
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText(says("Sent: «Anna Petrova». A person will look it up by hand."));
    expect(await sent(seen)).toEqual([
      {
        name_as_listed: "Anna Petrova",
        region: "Kazakhstan",
        declared_level: "authorised-2",
        note: "annayoga.example",
      },
    ]);
    expect(confirmAction).not.toHaveBeenCalled();
    expect(screen.queryByLabelText(NAME)).toBeNull();
  });

  test("no level and no note go as null", async () => {
    const seen = stubApi({ listing: listing() });

    await openListing();
    await screen.findByLabelText(NAME);
    type(NAME, "Anna Petrova");
    type(REGION, "Kazakhstan");
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText(says(/^Sent: «Anna Petrova»/));
    expect(await sent(seen)).toEqual([
      { name_as_listed: "Anna Petrova", region: "Kazakhstan", declared_level: null, note: null },
    ]);
  });

  test("409 listing_wait says when, and keeps what was typed", async () => {
    stubApi({ listing: listing(), put: () => json({ code: "listing_wait" }, 409) });

    await openListing();
    await screen.findByLabelText(NAME);
    type(NAME, "Anna Petrova");
    type(REGION, "Kazakhstan");
    type(NOTE, "annayoga.example");
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("You can send it again in a day.");
    expect(value(NAME)).toBe("Anna Petrova");
    expect(value(REGION)).toBe("Kazakhstan");
    expect(value(NOTE)).toBe("annayoga.example");
  });

  test("422 invalid_listing points at the fields", async () => {
    stubApi({ listing: listing(), put: () => json({ code: "invalid_listing" }, 422) });

    await openListing();
    await screen.findByLabelText(NAME);
    type(NAME, "‮");
    type(REGION, "Kazakhstan");
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText(
      says("Write the name as the directory shows it, up to 100 characters."),
    );
    expect(screen.getByLabelText(NAME)).toHaveAttribute("aria-invalid", "true");
    expect(pageText()).not.toContain("Couldn't save");
  });

  test("a failed save keeps the text", async () => {
    stubApi({ listing: listing(), put: () => json({}, 500) });

    await openListing();
    await screen.findByLabelText(NAME);
    type(NAME, "Anna Petrova");
    type(REGION, "Kazakhstan");
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't save. Try again in a moment.",
    );
    expect(value(NAME)).toBe("Anna Petrova");
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  test("can_send false: the wait line shows and Send is off", async () => {
    const seen = stubApi({ listing: listing({ status: "withdrawn", can_send: false }) });

    await openListing();
    await screen.findByLabelText(NAME);

    expect(screen.getByText(says("You can send it again in a day."))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(telegram.main?.visible).toBe(false);
    act(() => {
      telegram.main?.press();
    });
    expect(calls(seen, "PUT")).toHaveLength(0);
  });

  test("in Telegram the main button sends, and the page has no second button", async () => {
    telegram.mainButton = true;
    const seen = stubApi({ listing: listing() });

    await openListing();
    await screen.findByLabelText(NAME);
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
    expect(telegram.main).toMatchObject({ text: "Send", visible: true, loading: false });

    type(NAME, "Anna Petrova");
    type(REGION, "Kazakhstan");
    act(() => {
      telegram.main?.press();
    });

    await screen.findByText(says(/^Sent: «Anna Petrova»/));
    expect(calls(seen, "PUT")).toHaveLength(1);
  });
});

describe("status views", () => {
  test("withdrawn reads like the start: the intro and an empty form", async () => {
    stubApi({ listing: listing({ status: "withdrawn" }) });

    await openListing();

    await screen.findByText(says(INTRO));
    expect(value(NAME)).toBe("");
    expect(value(REGION)).toBe("");
    expect(screen.queryByRole("button", { name: "Remove…" })).toBeNull();
  });

  test("pending: what was sent, Edit and Remove", async () => {
    stubApi({ listing: PENDING });

    await openListing();

    await screen.findByText(says("Sent: «Anna Petrova». A person will look it up by hand."));
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove…" })).toBeInTheDocument();
    expect(screen.queryByLabelText(NAME)).toBeNull();
    expect(pageText()).not.toContain("✔");
  });

  test("pending: an edit saves in place, without a question", async () => {
    const seen = stubApi({ listing: PENDING });

    await openListing();
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    expect(value(NAME)).toBe("Anna Petrova");
    expect(value(REGION)).toBe("Kazakhstan");
    expect(value(LEVEL)).toBe("authorised-2");
    expect(value(NOTE)).toBe("annayoga.example");
    type(NAME, "Anna V. Petrova");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByText(says("Sent: «Anna V. Petrova». A person will look it up by hand."));
    expect(confirmAction).not.toHaveBeenCalled();
    expect(calls(seen, "PUT")).toHaveLength(1);
  });

  test("listed: the line and the level line, Edit and Remove", async () => {
    stubApi({ listing: LISTED });

    await openListing();

    await screen.findByText(says(LINE_EN));
    expect(
      screen.getByText(says("Level (in the teacher's own words): Authorised Level 2")),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove…" })).toBeInTheDocument();
  });

  test("listed: a new level alone saves with no question", async () => {
    const seen = stubApi({ listing: LISTED });

    await openListing();
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    type(LEVEL, "certified");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByText(says("Level (in the teacher's own words): Certified"));
    expect(screen.getByText(says(LINE_EN))).toBeInTheDocument();
    expect(confirmAction).not.toHaveBeenCalled();
    expect(await sent(seen)).toEqual([
      {
        name_as_listed: "Anna Petrova",
        region: "Kazakhstan",
        declared_level: "certified",
        note: null,
      },
    ]);
  });

  test("listed: a new name asks once; No sends nothing and keeps the text", async () => {
    const seen = stubApi({ listing: LISTED });

    await openListing();
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    type(NAME, "Anna V. Petrova");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(confirmAction).toHaveBeenCalledTimes(1);
    });
    expect(confirmAction).toHaveBeenCalledWith(
      "Send the new details? The line hides until it is checked again.",
      "Send",
      "Cancel",
    );
    expect(calls(seen, "PUT")).toHaveLength(0);
    expect(value(NAME)).toBe("Anna V. Petrova");
  });

  test("listed: a new region, confirmed, goes back to waiting", async () => {
    confirmAction.mockResolvedValue(true);
    const seen = stubApi({ listing: LISTED });

    await openListing();
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    type(REGION, "Almaty, Kazakhstan");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByText(says("Sent: «Anna Petrova». A person will look it up by hand."));
    expect(confirmAction).toHaveBeenCalledTimes(1);
    expect(calls(seen, "PUT")).toHaveLength(1);
    expect(pageText()).not.toContain("✔");
  });

  test("not_found: the gentle text and the form with what was sent", async () => {
    stubApi({
      listing: listing({
        status: "not_found",
        name_as_listed: "Anna Petrova",
        region: "Kazakhstan",
        requested_at: "2026-11-01T06:00:00Z",
      }),
    });

    await openListing();

    await screen.findByText(
      says(/^I couldn't confirm the entry «Anna Petrova» for this account yet\./),
    );
    expect(value(NAME)).toBe("Anna Petrova");
    expect(value(REGION)).toBe("Kazakhstan");
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
    expect(pageText()).not.toMatch(/not (in|found)/i);
  });

  test("Remove asks once, deletes, and returns to the intro and the form", async () => {
    confirmDestructive.mockResolvedValue(true);
    const seen = stubApi({ listing: LISTED });

    await openListing();
    fireEvent.click(await screen.findByRole("button", { name: "Remove…" }));

    await screen.findByText(says(INTRO));
    expect(confirmDestructive).toHaveBeenCalledTimes(1);
    expect(confirmDestructive).toHaveBeenCalledWith(
      "Remove the directory line? Students will no longer see it. You can ask again later.",
      "Remove",
      "Cancel",
    );
    expect(calls(seen, "DELETE")).toHaveLength(1);
    expect(value(NAME)).toBe("");
    expect(pageText()).not.toContain("✔");
  });

  test("Remove, declined, changes nothing", async () => {
    const seen = stubApi({ listing: PENDING });

    await openListing();
    fireEvent.click(await screen.findByRole("button", { name: "Remove…" }));

    await waitFor(() => {
      expect(confirmDestructive).toHaveBeenCalledTimes(1);
    });
    expect(calls(seen, "DELETE")).toHaveLength(0);
    expect(screen.getByText(says(/^Sent: «Anna Petrova»/))).toBeInTheDocument();
  });

  test("RU: the status copy", async () => {
    stubApi({ listing: LISTED });

    await openListing("ru");

    await screen.findByText(says(LINE_RU));
    expect(
      screen.getByText(
        says("Уровень (со слов учителя): Authorised Level 2 (авторизация, уровень 2)"),
      ),
    ).toBeInTheDocument();
  });
});

describe("the line on a student's list of teachers", () => {
  const mark = () => document.querySelectorAll(".listing-mark");

  test("its own element under the name; the level only after a tap", async () => {
    stubApi({ listing: listing(), teachers: [teacher(LENA, "Лена", MARK)] });

    await openLinks();
    const line = await screen.findByRole("button", { name: says(LINE_EN) });

    const name = screen.getByText(says("Лена"));
    expect(name.textContent).toBe("Лена"); // never inside the name
    expect(name.contains(line)).toBe(false);
    expect(line.closest(".link-person")).toBeNull(); // not in the row with the name's buttons
    expect(line).toHaveAttribute("aria-expanded", "false");
    expect(line).not.toHaveClass("link"); // the normal text colour, not the link blue
    expect(pageText()).not.toContain("Level (in the teacher's own words)");
    expect(pageText()).not.toContain("Authorised");
    expect(screen.queryByText(says(ABOUT_EN))).toBeNull();
    for (const button of screen.getAllByRole("button")) {
      if (button !== line) expect(button.textContent).not.toContain("✔");
    }

    fireEvent.click(line);

    expect(line).toHaveAttribute("aria-expanded", "true");
    const level = screen.getByText(says("Level (in the teacher's own words): Authorised Level 2"));
    expect(level.textContent).not.toContain("✔");
    const about = screen.getByText(says(ABOUT_EN));
    expect(plain(about.textContent)).toContain("This is not an endorsement by SYC");
    expect(plain(about.textContent)).toContain(
      "the line says nothing about a teacher who doesn't have it.",
    );

    fireEvent.click(line);
    expect(pageText()).not.toContain("Level (in the teacher's own words)");
  });

  test("no level: the tap shows the explanation and no level line", async () => {
    stubApi({
      listing: listing(),
      teachers: [teacher(LENA, "Лена", { ...MARK, declared_level: null })],
    });

    await openLinks();
    fireEvent.click(await screen.findByRole("button", { name: says(LINE_EN) }));

    expect(screen.getByText(says(ABOUT_EN))).toBeInTheDocument();
    expect(pageText()).not.toContain("Level (in the teacher's own words)");
  });

  test("a teacher without the line is complete: no element, no placeholder, same order", async () => {
    stubApi({
      listing: listing(),
      teachers: [teacher(LENA, "Лена"), teacher(BORIS, "Boris", MARK)],
    });

    await openLinks();
    await screen.findByRole("button", { name: says(LINE_EN) });

    expect(mark()).toHaveLength(1);
    const rows = [...document.querySelectorAll(".link-person")];
    expect(rows.map((r) => r.querySelector("span")?.textContent)).toEqual(["Лена", "Boris"]);
    const [lena, boris] = rows;
    // Лена's row is followed directly by Boris's: nothing sits where a line would be.
    expect(lena?.nextElementSibling).toBe(boris);
    expect(boris?.nextElementSibling).toBe(mark()[0]);
    expect(lena?.querySelectorAll("button")).toHaveLength(1); // Remove… (she is the main one)
    expect(pageText()).not.toMatch(/not listed|unverified|not in the directory/i);
  });

  test("no teacher has it: nothing about the directory on their rows at all", async () => {
    stubApi({
      listing: json({ code: "unavailable" }, 503),
      teachers: [teacher(LENA, "Лена"), teacher(BORIS, "Boris")],
    });

    await openLinks();
    await screen.findByText(says("Boris"));

    expect(mark()).toHaveLength(0);
    expect(pageText()).not.toContain("✔");
    expect(pageText()).not.toMatch(/directory|SYC|Level/);
  });

  test("RU: the line, the level names and the explanation", async () => {
    stubApi({ listing: listing(), teachers: [teacher(LENA, "Лена", MARK)] });

    await openLinks("ru");
    const line = await screen.findByRole("button", { name: says(LINE_RU) });
    expect(pageText()).not.toContain("Уровень");

    fireEvent.click(line);

    expect(
      screen.getByText(
        says("Уровень (со слов учителя): Authorised Level 2 (авторизация, уровень 2)"),
      ),
    ).toBeInTheDocument();
    expect(pageText()).toContain("Это не рекомендация от SYC");
    expect(pageText()).toContain("отсутствие строки ничего не говорит об учителе.");
    expect(screen.getByRole("button", { name: "Строка о списке SYC" })).toBeInTheDocument();
  });
});

describe("checked: month and year", () => {
  const zone = process.env.TZ;
  afterEach(() => {
    if (zone === undefined) delete process.env.TZ;
    else process.env.TZ = zone;
  });

  // A date, not an instant: the first of the month stays in that month wherever the phone is.
  test.each(["UTC", "Pacific/Pago_Pago", "Pacific/Kiritimati"])("in %s", (tz) => {
    process.env.TZ = tz;
    expect(checkedMonth("2026-11-01", "en")).toBe("November 2026");
    expect(checkedMonth("2026-11-01", "ru")).toBe("ноябрь 2026");
    expect(checkedMonth("2026-11-30", "en")).toBe("November 2026");
    expect(checkedMonth("2027-01-01", "ru")).toBe("январь 2027");
  });

  test("the far-west zone really is in force in this test", () => {
    process.env.TZ = "Pacific/Pago_Pago";
    expect(new Date("2026-11-01T00:00:00Z").getMonth()).toBe(9); // October there
  });
});

describe("listing copy", () => {
  const SOURCES = { en: [enApp, enListing], ru: [ruApp, ruListing] } as const;
  const LEVELS = ["authorised", "authorised-1", "authorised-2", "certified"];

  function bundle(locale: "en" | "ru", sources: readonly string[]): FluentBundle {
    const b = new FluentBundle(locale, { useIsolating: false });
    for (const source of sources) b.addResource(new FluentResource(source));
    return b;
  }
  const ids = (source: string) =>
    new FluentResource(source).body.map((m) => m.id).filter((id) => id.startsWith("listing-"));

  function lines(locale: "en" | "ru"): string[] {
    const b = bundle(locale, SOURCES[locale]);
    return SOURCES[locale].flatMap(ids).flatMap((id) => {
      const pattern = b.getMessage(id)?.value;
      if (!pattern) return [];
      return LEVELS.map((level) =>
        b.formatPattern(pattern, { listed: "Anna Petrova", when: "November 2026", level }),
      );
    });
  }

  it("listing.ftl has the same messages and variables in en and ru", () => {
    expect(ids(ruListing).sort()).toEqual(ids(enListing).sort());
    expect(ids(ruApp).sort()).toEqual(ids(enApp).sort());
    expect(ids(enApp).sort()).toEqual([
      "listing-about",
      "listing-level",
      "listing-level-name",
      "listing-mark",
      "listing-open",
    ]);
    for (const source of [enListing, ruListing]) {
      const defined = [...source.matchAll(/^[a-z][a-z0-9-]*\s*=/gm)].length;
      expect(ids(source)).toHaveLength(defined); // Fluent drops junk silently
    }
    const vars = (source: string): Record<string, string[]> =>
      Object.fromEntries(
        [...source.matchAll(/^(listing-[a-z-]+) = (.*)$/gm)].map(([, id, text]) => [
          id ?? "",
          [...(text ?? "").matchAll(/\{ \$([a-z]+)/g)].map((m) => m[1] ?? "").sort(),
        ]),
      );
    expect(vars(ruListing)).toEqual(vars(enListing));
  });

  it("the line and the level names read as the spec has them", () => {
    const en = bundle("en", SOURCES.en);
    const ru = bundle("ru", SOURCES.ru);
    const say = (b: FluentBundle, id: string, args: Record<string, string>) =>
      b.formatPattern(b.getMessage(id)?.value ?? "", args);
    expect(LEVELS.map((level) => say(en, "listing-level-name", { level }))).toEqual([
      "Authorised",
      "Authorised Level 1",
      "Authorised Level 2",
      "Certified",
    ]);
    expect(LEVELS.map((level) => say(ru, "listing-level-name", { level }))).toEqual([
      "Authorised (авторизация)",
      "Authorised Level 1 (авторизация, уровень 1)",
      "Authorised Level 2 (авторизация, уровень 2)",
      "Certified (сертификация SYC)",
    ]);
    expect(say(en, "listing-mark", { listed: "Anna Petrova", when: "November 2026" })).toBe(
      LINE_EN,
    );
    expect(say(ru, "listing-mark", { listed: "Anna Petrova", when: "ноябрь 2026" })).toBe(LINE_RU);
    expect(say(ru, "listing-open", {})).toBe("Строка о списке SYC");
  });

  const AVOID = {
    en: ["badge", "verified", "unverified", "certified by", "approved", "official", "endorse", "guru"],
    ru: ["значок", "значк", "подтвержд", "официальн", "одобрен", "гуру"],
  }; // prettier-ignore

  it.each(["en", "ru"] as const)("%s: never the words the line must not use", (locale) => {
    const all = lines(locale).map((l) =>
      l.toLowerCase().replace("this is not an endorsement by syc", ""),
    );
    expect(all.length).toBeGreaterThan(80);
    for (const word of AVOID[locale]) {
      expect(all.filter((l) => l.includes(word))).toEqual([]);
    }
  });

  it("RU: informal, and no gendered past tense about the person", () => {
    expect(ruListing).not.toMatch(/\bты\s+\S+л[аи]?\b/i);
    expect(ruListing).not.toContain("(а)");
    expect(ruListing).not.toMatch(/\b[Вв]ы\b|\b[Вв]аш/);
  });
});
