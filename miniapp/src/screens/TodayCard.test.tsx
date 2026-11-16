import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { Days, PracticePresets } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import { haptics } from "../telegram";
import { TodayCard } from "./TodayCard";

// UI-06 stage 2 (spec §5): the one day card on Today. Three choices, one per row, as the bot's
// Today; "Other…" opens the reasons in place; a logged or auto-rest day leads with that fact;
// after "Practiced" the card stays small and nothing opens by itself.

vi.mock("../telegram", () => ({
  useBackButton: vi.fn(),
  enableClosingConfirmation: vi.fn(),
  disableClosingConfirmation: vi.fn(),
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
}));

const TODAY = "2026-10-18"; // a Sunday

const ME = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Ash",
  locale: "en",
  timezone: "Asia/Almaty",
  hide_ladies: false,
  offer_check_in: true,
};

const LAST: PracticePresets["last"] = {
  slot: 1,
  context: "led",
  online: false,
  length: { series: ["primary"], end: null, first_part: null },
  duration_min: 90,
  start_time: "06:30", // never copied
  timezone: "Asia/Almaty",
};

const CATALOG = {
  version: "v1",
  milestone_items: [],
  check_in_tags: [
    { key: "light", group: "body" },
    { key: "calm", group: "mind" },
  ],
  series: [
    {
      slug: "primary",
      number: 1,
      name_en: "Primary series",
      name_ru: "Первая серия",
      halves_split: "navasana",
      stops: [{ key: "navasana", latin: "Navasana", ru: "Навасана" }],
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Older fixtures predate WH-01: `periods` / `practice_on` default to none / off. */
type DaysFixture = Omit<Days, "periods" | "practice_on" | "notes"> & Partial<Days>;

interface Stub {
  /** How writes answer: 0 never answers. */
  writeStatus?: number;
  /** Merged into the day save's answer. */
  saved?: Record<string, unknown>;
  me?: Record<string, unknown>;
  /** The previous practice, for "Same as last time". */
  last?: PracticePresets["last"];
}

/** A small stateful server: GET /me/days returns `fixture` with what was saved since; records
 * every request. */
function stubApi(
  fixture: DaysFixture,
  { writeStatus = 200, saved = {}, me = ME, last = null }: Stub = {},
): Request[] {
  let days: Days = { periods: [], practice_on: false, notes: [], ...fixture };
  const others = () => days.days.filter((d) => d.date !== TODAY);
  const today = () => days.days.find((d) => d.date === TODAY);
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request);
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/me") return json(me);
      if (path === "/api/v1/catalog") return json(CATALOG);
      if (path.endsWith("/practice-presets")) return json({ last, presets: [] });
      if (path === "/api/v1/me/moon-days")
        return json({ location: { slug: "mysuru", explicit: false }, today: TODAY, days: [] });
      if (path === "/api/v1/moon/cities") return json([]);
      if (request.method === "GET") return json(days);
      if (writeStatus === 0) return new Promise<Response>(() => undefined);
      if (writeStatus !== 200 && writeStatus !== 204)
        return json({ code: "unavailable" }, writeStatus);
      if (request.method === "DELETE") {
        days = { ...days, days: others() };
        return json(null, 204);
      }
      const body = (await request.clone().json()) as Record<string, unknown>;
      if (path.includes("/practices/")) {
        const practice = { slot: 1, timezone: null, ...body };
        days = {
          ...days,
          days: [...others(), { ...today(), practices: [practice] }],
        } as Days;
        return json(practice);
      }
      const day = { date: TODAY, status: body.status, practices: [], check_ins: [] };
      days = { ...days, days: [...others(), day] } as Days;
      return json({ ...day, ...saved });
    }),
  );
  return seen;
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale="en">
        <TodayCard zone="Asia/Almaty" locale="en" />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const visible = (el: HTMLElement) => el.textContent.replace(/[⁨⁩]/g, "");
const labels = (buttons: HTMLElement[]) => buttons.map(visible);
/** Every control on the card, top to bottom. */
const controls = () => labels(within(screen.getByRole("region")).getAllByRole("button"));

const empty: DaysFixture = {
  today: TODAY,
  timezone_known: true,
  auto: [],
  moon_location: "mysuru",
  days: [],
};
const logged = (status: string, more: Record<string, unknown> = {}): DaysFixture =>
  ({
    ...empty,
    days: [{ date: TODAY, status, practices: [], check_ins: [], ...more }],
  }) as DaysFixture;

const PROMPT = "Practice or rest? Both go in your log.";
const CHOICES = ["🧘 Practiced", "😌 Rest day", "Other…"];

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("TodayCard: three choices", () => {
  it("an unanswered day: the server's date, the question, exactly three choices", async () => {
    stubApi(empty);
    renderCard();

    expect(
      await screen.findByRole("heading", { level: 2, name: "Today, Sun, Oct 18" }),
    ).toBeInTheDocument();
    expect(screen.getByText(PROMPT)).toBeInTheDocument();
    expect(controls()).toEqual(CHOICES);
    expect(screen.queryAllByRole("button", { pressed: true })).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Other…" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("Other… opens the reasons in the bot's order; a reason saves and closes", async () => {
    const seen = stubApi(empty);
    renderCard();
    const other = await screen.findByRole("button", { name: "Other…" });

    fireEvent.click(other);

    expect(other).toHaveAttribute("aria-expanded", "true");
    const reasons = screen.getByRole("group", {
      name: "Pick what fits. Any day belongs in your log.",
    });
    expect(labels(within(reasons).getAllByRole("button"))).toEqual([
      "🌙 Moon day",
      "🌸 Ladies' holiday",
      "🤒 Sick / injury",
      "✈️ Travel",
      "🌱 No practice",
    ]);
    expect(seen.some((r) => r.method === "PUT")).toBe(false); // opening saves nothing
    fireEvent.click(within(reasons).getByRole("button", { name: "🤒 Sick / injury" }));

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PUT")).toBe(true);
    });
    expect(await seen.find((r) => r.method === "PUT")?.json()).toEqual({ status: "sick" });
    expect(screen.queryByRole("button", { name: "🤒 Sick / injury" })).not.toBeInTheDocument();
    expect(other).toHaveAttribute("aria-expanded", "false");
    expect(other).toHaveAttribute("aria-pressed", "true");
    expect(visible(await screen.findByText(/In your log/))).toBe("✓ In your log: 🤒 Sick / injury");
  });

  it("leaves 🌸 out under 'Hide the 🌸 button': four reasons", async () => {
    stubApi(empty, { me: { ...ME, hide_ladies: true } });
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "Other…" }));

    await vi.waitFor(() => {
      expect(screen.queryByRole("button", { name: "🌸 Ladies' holiday" })).not.toBeInTheDocument();
    });
    expect(
      labels(within(screen.getByRole("group", { name: /Pick what fits/ })).getAllByRole("button")),
    ).toEqual(["🌙 Moon day", "🤒 Sick / injury", "✈️ Travel", "🌱 No practice"]);
  });

  it("keeps 🌸 among the reasons while it is the logged status", async () => {
    stubApi(logged("ladies"), { me: { ...ME, hide_ladies: true } });
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "Other…" }));

    expect(screen.getByRole("button", { name: "🌸 Ladies' holiday" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("a logged day leads with the fact: no question, the logged choice pressed", async () => {
    stubApi({
      ...empty,
      days: [
        { date: "2026-10-17", status: "rest", practices: [], check_ins: [] },
        { date: TODAY, status: "moon", practices: [], check_ins: [] },
      ],
    });
    renderCard();

    expect(visible(await screen.findByText(/In your log/))).toBe("✓ In your log: 🌙 Moon day");
    expect(screen.queryByText(PROMPT)).not.toBeInTheDocument();
    // A reason sits behind "Other…", which carries the mark.
    expect(labels(screen.getAllByRole("button", { pressed: true }))).toEqual(["Other…"]);
    expect(controls()).toEqual([...CHOICES, "Add a note", "Clear"]);
  });

  it("saves a tap optimistically with haptic feedback", async () => {
    const seen = stubApi(empty, { writeStatus: 0 });
    renderCard();
    const rest = await screen.findByRole("button", { name: /Rest day/ });

    fireEvent.click(rest);

    expect(haptics.impact).toHaveBeenCalledWith("light");
    // Pressed although the server never answers this PUT.
    await vi.waitFor(() => {
      expect(rest).toHaveAttribute("aria-pressed", "true");
    });
    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PUT")).toBe(true);
    });
    const put = seen.find((r) => r.method === "PUT");
    expect(new URL(put?.url ?? "").pathname).toBe(`/api/v1/me/days/${TODAY}`);
    expect(await put?.json()).toEqual({ status: "rest" });
  });

  it("rolls back and says so when saving fails", async () => {
    stubApi(empty, { writeStatus: 503 });
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: /Practiced/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Couldn't save/);
    expect(screen.queryByRole("button", { pressed: true })).not.toBeInTheDocument();
    expect(haptics.notify).toHaveBeenCalledWith("error");
  });

  it("celebrates a practice count from the server's answer, then dismisses (GM-01)", async () => {
    stubApi(empty, {
      saved: {
        celebrations: [
          { kind: "practice_count", series: null, key: null, first: null, count: 1000 },
        ],
      },
    });
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: /Practiced/ }));

    const card = await screen.findByText(/practices in your log/);
    expect(visible(card)).toBe("🎉 1,000 practices in your log. Thank you for coming to the mat.");
    expect(haptics.notify).toHaveBeenCalledWith("success");
    fireEvent.click(card);
    expect(screen.queryByText(/practices in your log/)).not.toBeInTheDocument();
  });

  it("shows no card when the save celebrates nothing", async () => {
    stubApi(empty, { saved: { celebrations: [] } });
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: /Practiced/ }));

    await vi.waitFor(() => {
      expect(haptics.impact).toHaveBeenCalled();
    });
    expect(screen.queryByText(/practices in your log/)).not.toBeInTheDocument();
    expect(haptics.notify).not.toHaveBeenCalledWith("success");
  });

  it("shows the privacy note for a ladies' holiday and can clear it", async () => {
    const seen = stubApi(logged("ladies"));
    renderCard();

    expect(await screen.findByText(/Only you see this/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "DELETE")).toBe(true);
    });
    expect(screen.queryByText(/Only you see this/)).not.toBeInTheDocument();
    expect(await screen.findByText(PROMPT)).toBeInTheDocument(); // unanswered again
  });

  it("says so when today's status can't be loaded", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(json({ code: "unavailable" }, 503))),
    );

    renderCard();

    expect(await screen.findByRole("status")).toHaveTextContent(/Couldn't load/);
  });

  // Offline: the save fails, and so does the refetch after it. The card had its days: it
  // stays, with the note being typed, and says the save failed.
  it("keeps the card and a typed note when a save and the refetch after it both fail", async () => {
    stubApi(logged("rest"));
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "Add a note" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Diary" }), {
      target: { value: "Kapotasana felt lighter" },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );

    fireEvent.click(screen.getByRole("button", { name: "🧘 Practiced" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't save. Try again in a moment.",
    );
    await new Promise((resolve) => setTimeout(resolve, 30)); // the refetch has failed too
    expect(screen.getByRole("textbox", { name: "Diary" })).toHaveValue("Kapotasana felt lighter");
    expect(screen.getByRole("heading", { level: 2, name: /^Today, / })).toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load/)).not.toBeInTheDocument();
    // Back as it was before the tap.
    expect(screen.getByRole("button", { name: "😌 Rest day", pressed: true })).toBeInTheDocument();
  });

  it("renders nothing until the days are loaded", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => undefined)),
    );

    const { container } = renderCard();

    expect(container).toBeEmptyDOMElement();
  });

  describe("the first step", () => {
    it("is the card itself: the question shows until the day is answered", async () => {
      stubApi(empty);
      renderCard();

      expect(await screen.findByText(PROMPT)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "😌 Rest day" }));

      // The pressed button is the answer: no line repeats it.
      expect(
        await screen.findByRole("button", { name: "😌 Rest day", pressed: true }),
      ).toBeInTheDocument();
      expect(screen.queryByText(PROMPT)).not.toBeInTheDocument();
      expect(screen.queryByText(/In your log/)).not.toBeInTheDocument();
      // The old first-log hint and its device flag are gone.
      expect(screen.queryByText(/Start by logging today/)).not.toBeInTheDocument();
      expect(localStorage.getItem("onboard.logged")).toBeNull();
    });

    it("asks someone who already logs (e.g. in the bot) the same question", async () => {
      stubApi({
        ...empty,
        days: [{ date: "2026-10-17", status: "practiced", practices: [], check_ins: [] }], // yesterday
      });
      renderCard();

      expect(await screen.findByText(PROMPT)).toBeInTheDocument();
      expect(controls()).toEqual(CHOICES);
    });
  });
});

describe("TodayCard: after Practiced", () => {
  it("stays small: a summary line and quiet entries, nothing expanded", async () => {
    stubApi(empty, { last: LAST });
    renderCard();
    await screen.findByText(PROMPT);
    expect(controls()).toHaveLength(3); // before the tap

    fireEvent.click(screen.getByRole("button", { name: "🧘 Practiced" }));

    // The pressed button says it: the label is repeated only for a reason behind "Other…".
    expect(
      await screen.findByRole("button", { name: "🧘 Practiced", pressed: true }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/In your log/)).not.toBeInTheDocument();

    // What "Same as last time" would copy: never the start time.
    expect(visible(await screen.findByText(/^Last time/))).toBe(
      "Last time: Led · Full Primary · 90 min",
    );
    expect(controls()).toEqual([
      ...CHOICES,
      "🔁 Same as last time",
      "📝 Add details",
      "✨ How do you feel?",
      "Add a note",
      "Clear",
    ]);
    expect(screen.queryAllByRole("button", { expanded: true })).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Mysore" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mood 3 of 5" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("Same as last time copies type, length and duration, never the start time", async () => {
    const seen = stubApi(logged("practiced"), { last: LAST });
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: "🔁 Same as last time" }));

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PUT")).toBe(true);
    });
    const put = seen.find((r) => r.method === "PUT");
    expect(new URL(put?.url ?? "").pathname).toBe(`/api/v1/me/days/${TODAY}/practices/1`);
    expect(await put?.json()).toEqual({
      context: "led",
      online: false,
      length: { series: ["primary"], end: null, first_part: null },
      duration_min: 90,
      start_time: null,
    });
    // Details exist now: the line is the day's own, and the copy is no longer offered.
    await vi.waitFor(() => {
      expect(screen.queryByRole("button", { name: "🔁 Same as last time" })).toBeNull();
    });
    expect(visible(screen.getByText(/^Led · /))).toBe("Led · Full Primary · 90 min");
    expect(screen.getByRole("button", { name: "📝 Details" })).toBeInTheDocument();
  });

  it("a failed Same as last time says so and stays offered", async () => {
    stubApi(logged("practiced"), { last: LAST, writeStatus: 503 });
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: "🔁 Same as last time" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't save. Try again in a moment.",
    );
    expect(haptics.notify).toHaveBeenCalledWith("error");
    expect(screen.getByRole("button", { name: "🔁 Same as last time" })).toBeInTheDocument();
  });

  it("offers no copy without a previous practice", async () => {
    stubApi(logged("practiced"));
    renderCard();

    await screen.findByRole("button", { name: "📝 Add details" });
    expect(screen.queryByRole("button", { name: "🔁 Same as last time" })).not.toBeInTheDocument();
    expect(screen.queryByText(/^Last time/)).not.toBeInTheDocument();
  });

  it("Add details loads the panel on the tap, the start time with it", async () => {
    stubApi(logged("practiced"));
    renderCard();
    const entry = await screen.findByRole("button", { name: "📝 Add details" });
    expect(entry).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(entry);

    expect(haptics.selection).toHaveBeenCalled();
    expect(entry).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByText("Type of practice")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mysore" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Start time/)).toBeInTheDocument();

    fireEvent.click(entry); // a second tap folds it again
    expect(screen.queryByRole("button", { name: "Mysore" })).not.toBeInTheDocument();
  });

  it("one panel at a time: opening the check-in folds the details", async () => {
    stubApi(logged("practiced"));
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "📝 Add details" }));
    await screen.findByRole("button", { name: "Mysore" });

    fireEvent.click(screen.getByRole("button", { name: "✨ How do you feel?" }));

    expect(await screen.findByRole("button", { name: "Mood 3 of 5" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mysore" })).not.toBeInTheDocument();
  });

  it("the setting hides the check-in entry", async () => {
    stubApi(logged("practiced"), { me: { ...ME, offer_check_in: false } });
    renderCard();

    await screen.findByRole("button", { name: "📝 Add details" });
    expect(screen.queryByRole("button", { name: /How do you feel/ })).not.toBeInTheDocument();
  });

  it("a check-in that exists stays editable whatever the setting, with its summary", async () => {
    stubApi(
      logged("practiced", {
        check_ins: [{ slot: 1, mood: 4, energy: 4, effort: null, tags: ["calm", "light"] }],
      }),
      { me: { ...ME, offer_check_in: false } },
    );
    renderCard();

    const entry = await screen.findByRole("button", { name: /How do you feel/ });
    await vi.waitFor(() => {
      // Tags in the catalog's order, as the bot's line.
      expect(visible(entry)).toBe("✨ How do you feel?🙂 · ⚡ energy 4/5 · Light, Calm");
    });
    expect(entry).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(entry);
    expect(await screen.findByRole("button", { name: "Mood 4 of 5" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

describe("TodayCard: the note entry", () => {
  const note = { date: TODAY, text: "Tight hamstrings.", unreadable: false };

  it("is not offered on an unanswered day", async () => {
    stubApi(empty);
    renderCard();

    await screen.findByText(PROMPT);
    expect(screen.queryByRole("button", { name: "Add a note" })).not.toBeInTheDocument();
  });

  it("shows a note that exists, logged day or not", async () => {
    stubApi({ ...empty, notes: [note] });
    renderCard();

    expect(await screen.findByText("Tight hamstrings.")).toBeInTheDocument();
    expect(screen.getByText(PROMPT)).toBeInTheDocument();
  });

  it("is a quiet entry on a logged day, and opens only on its tap", async () => {
    stubApi(logged("rest"));
    renderCard();

    const add = await screen.findByRole("button", { name: "Add a note" });
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    fireEvent.click(add);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });
});

describe("TodayCard auto-rest (PR-09)", () => {
  function stubAuto(auto: Days["auto"]) {
    vi.stubGlobal(
      "fetch",
      vi.fn((request: Request) => {
        const path = new URL(request.url).pathname;
        if (path === "/api/v1/me") return Promise.resolve(json(ME));
        if (path === "/api/v1/me/moon-days")
          return Promise.resolve(
            json({
              location: { slug: "mysuru", explicit: false },
              today: TODAY,
              days: [{ date: TODAY, phase: "purnima" }],
            }),
          );
        if (path === "/api/v1/moon/cities")
          return Promise.resolve(
            json([
              { slug: "mysuru", name_en: "Mysuru", name_ru: "Майсур", timezone: "Asia/Kolkata" },
            ]),
          );
        return Promise.resolve(
          json({ today: TODAY, timezone_known: true, auto, moon_location: "mysuru", days: [] }),
        );
      }),
    );
  }

  it("names the moon day once: no question after it, nothing pressed", async () => {
    stubAuto([{ date: TODAY, kind: "moon", also_day_off: true }]);
    renderCard();

    const note = await screen.findByText(/a traditional rest day/);
    expect(visible(note)).toBe(
      "🌙 Moon day (📍 Mysuru), a traditional rest day and your weekly day off too. If you practiced, log it below.",
    );
    expect(screen.queryByText(/Full moon today/)).not.toBeInTheDocument();
    expect(screen.queryByText(PROMPT)).not.toBeInTheDocument();
    expect(controls()).toEqual(CHOICES);
    expect(screen.queryAllByRole("button", { pressed: true })).toHaveLength(0);
  });

  it("shows the day off as rest until something is logged", async () => {
    stubAuto([{ date: TODAY, kind: "day_off", also_day_off: false }]);
    renderCard();

    expect(await screen.findByText(/Your weekly day off, shown as rest/)).toBeInTheDocument();
    expect(screen.queryByText(PROMPT)).not.toBeInTheDocument();
    expect(screen.queryAllByRole("button", { pressed: true })).toHaveLength(0);
  });
});
