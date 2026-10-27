import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import type { Days } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import { enableClosingConfirmation, disableClosingConfirmation } from "../telegram";
import { DayEditor } from "./stats/DayEditor";
import { TodayCard } from "./TodayCard";

// PR-07 (spec §6, ADR-0025): the diary note block in the Today card (any status, or none)
// and the day editor. Collapsed: the note + Edit, or a quiet "Add a note" link. Editing is a
// textarea with explicit Save / Cancel (never save-on-blur), a counter from 1800 code points,
// closing confirmation while dirty, not optimistic for the text (a failed save keeps it open),
// blank Save sends DELETE, Remove asks inline first. No drafts in localStorage.

vi.mock("../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  enableClosingConfirmation: vi.fn(),
  disableClosingConfirmation: vi.fn(),
}));

const TODAY = "2026-10-27";
const EARLIER = "2026-10-20";
const DEVICE_NOW = new Date("2026-10-29T12:00:00Z"); // never used: the server's today wins
const NOTE = "Felt light today. Teacher said: soft gaze in Marichyasana C.";
const UNREADABLE = "This note can't be read right now. You can write a new one or remove it.";
const REMOVED =
  "Removed from your diary.";

const ME = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Ash",
  locale: "en",
  timezone: "Asia/Almaty",
  name_from_telegram: true,
  locale_from_telegram: true,
  day_off: null,
  hide_ladies: false,
  offer_check_in: false,
};

interface NoteOut {
  date: string;
  text: string | null;
  unreadable: boolean;
}

const note = (date: string, text: string | null = NOTE): NoteOut => ({
  date,
  text,
  unreadable: text === null,
});

function day(date: string, status = "rest") {
  return { date, status, practices: [], check_ins: [] };
}

/** `notes: null` = an older server's payload, without the field. */
function days(list: unknown[], notes: NoteOut[] | null = []): Days {
  const base = {
    today: TODAY,
    timezone_known: true,
    auto: [],
    moon_location: "mysuru",
    days: list,
    periods: [],
    practice_on: false,
  };
  return (notes === null ? base : { ...base, notes }) as unknown as Days;
}

const json = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

interface Stub {
  days?: Days;
  /** How PUT …/note answers: 200 saves (trimmed), 0 never answers, else an error. */
  putStatus?: number;
}

const notePath = (date: string) => `/api/v1/me/days/${date}/note`;

/** A small stateful server: note writes change what GET /me/days returns afterwards. */
function stubApi({ days: d = days([day(TODAY)]), putStatus = 200 }: Stub = {}) {
  const seen: Request[] = [];
  let served = d;
  const setNote = (date: string, value: NoteOut | null) => {
    const current = ((served as unknown as { notes?: NoteOut[] }).notes ?? []).filter(
      (n) => n.date !== date,
    );
    const notes = value ? [...current, value] : current;
    served = { ...served, notes };
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request);
      const path = new URL(request.url).pathname;
      const method = request.method;
      if (path === "/api/v1/me" && method === "GET") return json(ME);
      if (path === "/api/v1/me/moon-days")
        return json({ location: { slug: "mysuru", explicit: false }, today: TODAY, days: [] });
      if (path === "/api/v1/moon/cities") return json([]);
      if (path === "/api/v1/catalog") return json({ version: "t", series: [], check_in_tags: [] });
      if (path.endsWith("/practice-presets")) return json({ last: null, presets: [] });
      if (path === "/api/v1/me/notification-settings") return json({});
      const date = path.split("/")[5] ?? "";
      if (path.endsWith("/note") && method === "PUT") {
        if (putStatus === 0) return new Promise<Response>(() => undefined);
        if (putStatus !== 200) return json({ code: "unavailable" }, putStatus);
        const body = (await request.clone().json()) as { text: string };
        const text = body.text.trim() || null;
        const saved = { date, text, unreadable: false };
        setNote(date, text === null ? null : saved);
        return json(saved);
      }
      if (path.endsWith("/note") && method === "DELETE") {
        setNote(date, null);
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

const noteRequests = (seen: Request[], method: string, date = TODAY) =>
  seen.filter((r) => r.method === method && new URL(r.url).pathname === notePath(date));

async function sent(seen: Request[], method: string, date = TODAY): Promise<Request[]> {
  await vi.waitFor(() => {
    expect(noteRequests(seen, method, date).length).toBeGreaterThan(0);
  });
  return noteRequests(seen, method, date);
}

const addLink = () => screen.findByRole("button", { name: "Add a note" });
const editButton = () => screen.findByRole("button", { name: /edit/i });
const saveButton = () => screen.getByRole("button", { name: /^save$/i });
const cancelButton = () => screen.getByRole("button", { name: /^cancel$/i });
const textarea = () => screen.getByRole<HTMLTextAreaElement>("textbox");

const type = (text: string) => {
  fireEvent.change(textarea(), { target: { value: text } });
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: DEVICE_NOW });
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("DiaryNote: where and how it shows", () => {
  it("shows the note collapsed with Edit on the Today card", async () => {
    stubApi({ days: days([day(TODAY)], [note(TODAY)]) });
    renderToday();

    expect(await screen.findByText(NOTE)).toBeInTheDocument();
    expect(await editButton()).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("Edit opens the textarea with the note", async () => {
    stubApi({ days: days([day(TODAY)], [note(TODAY)]) });
    renderToday();

    fireEvent.click(await editButton());

    expect(textarea().value).toBe(NOTE);
    expect(saveButton()).toBeInTheDocument();
    expect(cancelButton()).toBeInTheDocument();
    expect(screen.getByText("Your diary is private: teachers don't see it.")).toBeInTheDocument();
  });

  it("an absent note is only a quiet Add link", async () => {
    stubApi();
    renderToday();

    const link = await addLink();
    const block = link.parentElement?.textContent ?? "";
    expect(block).not.toMatch(/yet|\?|\d/i);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it.each(["practiced", "rest", "moon", "ladies", "sick", "travel", "skipped"])(
    "is there on a %s day",
    async (status) => {
      stubApi({ days: days([day(TODAY, status)]) });
      renderToday();

      expect(await addLink()).toBeInTheDocument();
    },
  );

  it("is there on a day never logged, with its note", async () => {
    stubApi({ days: days([], [note(TODAY, "Rested, read the Yoga Mala.")]) });
    renderToday();

    expect(await screen.findByText("Rested, read the Yoga Mala.")).toBeInTheDocument();
  });

  it("an unreadable note says so and can be removed", async () => {
    stubApi({ days: days([day(TODAY)], [note(TODAY, null)]) });
    renderToday();

    expect(await screen.findByText(UNREADABLE)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove note" })).toBeInTheDocument();
  });

  it("renders a payload from an older server without notes", async () => {
    stubApi({ days: days([day(TODAY)], null) });
    renderToday();

    expect(await addLink()).toBeInTheDocument();
  });

  it("the day editor shows that day's note, logged or not", async () => {
    stubApi({ days: days([], [note(EARLIER, "Led class, counted vinyasa.")]) });
    renderEditor(EARLIER);

    expect(await screen.findByText("Led class, counted vinyasa.")).toBeInTheDocument();
  });
});

describe("DiaryNote: editing", () => {
  it("Save PUTs the text in the body and shows the server's value", async () => {
    const seen = stubApi();
    renderToday();
    fireEvent.click(await addLink());

    type("  Felt open in backbends.  ");
    fireEvent.click(saveButton());

    const [put] = await sent(seen, "PUT");
    expect(await put?.clone().json()).toEqual({ text: "  Felt open in backbends.  " });
    expect(put?.url).not.toContain("Felt");
    expect(await screen.findByText("Felt open in backbends.")).toBeInTheDocument();
    await vi.waitFor(() => {
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    });
  });

  it("never saves on blur", async () => {
    const seen = stubApi();
    renderToday();
    fireEvent.click(await addLink());

    type("half a thought");
    fireEvent.blur(textarea());
    await new Promise((resolve) => setTimeout(resolve, 30));

    expect(noteRequests(seen, "PUT")).toEqual([]);
    expect(textarea().value).toBe("half a thought");
  });

  it("Cancel discards the change", async () => {
    const seen = stubApi({ days: days([day(TODAY)], [note(TODAY)]) });
    renderToday();
    fireEvent.click(await editButton());

    type("something else");
    fireEvent.click(cancelButton());

    expect(await screen.findByText(NOTE)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(noteRequests(seen, "PUT")).toEqual([]);
    expect(noteRequests(seen, "DELETE")).toEqual([]);
  });

  it("a failed save keeps the textarea open with the text and says so", async () => {
    stubApi({ putStatus: 503 });
    renderToday();
    fireEvent.click(await addLink());

    type("words worth keeping");
    fireEvent.click(saveButton());

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(textarea().value).toBe("words worth keeping");
    expect(screen.queryByText("words worth keeping", { selector: "p" })).not.toBeInTheDocument();
  });

  it("is not optimistic for the text while saving", async () => {
    stubApi({ putStatus: 0 }); // the server never answers
    renderToday();
    fireEvent.click(await addLink());

    type("pending words");
    fireEvent.click(saveButton());
    await new Promise((resolve) => setTimeout(resolve, 30));

    expect(textarea().value).toBe("pending words");
  });

  it("a blank Save sends DELETE, not an empty PUT", async () => {
    const seen = stubApi({ days: days([day(TODAY)], [note(TODAY)]) });
    renderToday();
    fireEvent.click(await editButton());

    type("   \n  ");
    fireEvent.click(saveButton());

    await sent(seen, "DELETE");
    expect(noteRequests(seen, "PUT")).toEqual([]);
    expect(await addLink()).toBeInTheDocument();
  });

  it("the day editor saves to its own date", async () => {
    const seen = stubApi({ days: days([day(EARLIER)]) });
    renderEditor(EARLIER);
    fireEvent.click(await addLink());

    type("an earlier day");
    fireEvent.click(saveButton());

    const [put] = await sent(seen, "PUT", EARLIER);
    expect(await put?.clone().json()).toEqual({ text: "an earlier day" });
  });

  it("asks before closing the app while there are unsaved changes", async () => {
    stubApi();
    renderToday();
    fireEvent.click(await addLink());
    expect(enableClosingConfirmation).not.toHaveBeenCalled();

    type("dirty");
    expect(enableClosingConfirmation).toHaveBeenCalled();
    fireEvent.click(cancelButton());

    expect(disableClosingConfirmation).toHaveBeenCalled();
  });

  it("keeps no draft in localStorage", async () => {
    stubApi();
    renderToday();
    fireEvent.click(await addLink());

    type("a private draft");

    const stored = Object.keys(localStorage).map((k) => localStorage.getItem(k) ?? "");
    expect(stored.some((v) => v.includes("private draft"))).toBe(false);
  });
});

describe("DiaryNote: the counter", () => {
  const counter = () => screen.queryByText(/2[,.\s\u00a0\u202f]?000/);

  it("is hidden below 1800 code points", async () => {
    stubApi();
    renderToday();
    fireEvent.click(await addLink());

    type("a".repeat(1799));

    expect(counter()).not.toBeInTheDocument();
  });

  it("shows from 1800 code points", async () => {
    stubApi();
    renderToday();
    fireEvent.click(await addLink());

    type("a".repeat(1800));

    expect(counter()?.textContent).toMatch(/1[,.\s\u00a0\u202f]?800/);
  });

  it("counts code points, not UTF-16 units", async () => {
    stubApi();
    renderToday();
    fireEvent.click(await addLink());

    type("🧘".repeat(1000)); // 2000 UTF-16 units, 1000 code points
    expect(counter()).not.toBeInTheDocument();

    type("🧘".repeat(1900));
    expect(counter()?.textContent).toMatch(/1[,.\s\u00a0\u202f]?900/);
  });
});

describe("DiaryNote: review fixes", () => {
  it("Save is disabled past 2000 code points, and the counter says so", async () => {
    stubApi();
    renderToday();
    fireEvent.click(await addLink());

    type("a".repeat(2001));

    expect(saveButton()).toBeDisabled();
    expect(screen.getByRole("alert").textContent).toMatch(/2[,.\s\u00a0\u202f]?001/);
    type("a".repeat(2000));
    expect(saveButton()).toBeEnabled();
  });

  it("the day editor starts clean on another day: no draft carried over", async () => {
    const seen = stubApi({ days: days([day(EARLIER), day(TODAY)]) });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const editor = (date: string) => (
      <QueryClientProvider client={client}>
        <L10nProvider locale="en">
          <DayEditor
            date={date}
            label="A day"
            zone="Asia/Almaty"
            locale="en"
            showLadies
            onClose={() => undefined}
          />
        </L10nProvider>
      </QueryClientProvider>
    );
    // Visit TODAY first, so its day is cached: going back to it keeps the block mounted.
    const { rerender } = render(editor(TODAY));
    await addLink();
    rerender(editor(EARLIER));
    fireEvent.click(await addLink());
    type("for the earlier day");

    rerender(editor(TODAY));

    expect(await addLink()).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(noteRequests(seen, "PUT", TODAY)).toEqual([]);
  });
});

describe("DiaryNote: removing", () => {
  it("asks inline first, then DELETEs and says so honestly", async () => {
    const seen = stubApi({ days: days([day(TODAY)], [note(TODAY)]) });
    renderToday();
    await screen.findByText(NOTE);

    fireEvent.click(screen.getByRole("button", { name: "Remove note" }));

    expect(screen.getByText("Remove this note?")).toBeInTheDocument();
    expect(noteRequests(seen, "DELETE")).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    await sent(seen, "DELETE");
    expect(await screen.findByText(REMOVED)).toBeInTheDocument();
    expect(screen.queryByText(NOTE)).not.toBeInTheDocument();
  });

  it("an unreadable note is removed the same way", async () => {
    const seen = stubApi({ days: days([day(TODAY)], [note(TODAY, null)]) });
    renderToday();
    await screen.findByText(UNREADABLE);

    fireEvent.click(screen.getByRole("button", { name: "Remove note" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    await sent(seen, "DELETE");
  });
});
