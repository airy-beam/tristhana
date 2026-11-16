import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import { haptics, useBackButton } from "../../telegram";
import { DayEditor } from "./DayEditor";

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
}));

const TODAY = "2026-10-30";
const DAY = "2026-03-01"; // a backfill

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** GET /me/days: an empty day, then what was saved; PUT answers with `celebrations`. */
function stubApi(celebrations: unknown[]) {
  let days: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      if (request.method === "PUT") {
        const { status } = (await request.clone().json()) as { status: string };
        const day = { date: DAY, status, practices: [], check_ins: [] };
        days = [day];
        return json({ ...day, celebrations });
      }
      return json({
        today: TODAY,
        timezone_known: true,
        days,
        auto: [],
        moon_location: "mysuru",
        periods: [],
        practice_on: false,
        notes: [],
      });
    }),
  );
}

function renderEditor(onClose: () => void = () => undefined, showLadies = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale="en">
        <DayEditor
          date={DAY}
          label="Mar 1"
          zone="Asia/Almaty"
          locale="en"
          showLadies={showLadies}
          onClose={onClose}
        />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const visible = (el: HTMLElement) => el.textContent.replace(/[⁨⁩]/g, "");

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("DayEditor practice count (GM-01 part 2)", () => {
  it("Telegram's Back closes the editor, not the screen under it", () => {
    stubApi([]);
    const onClose = vi.fn();
    renderEditor(onClose);

    expect(useBackButton).toHaveBeenCalledWith(onClose);
  });

  it("celebrates a backfill that reaches 100, from the server's answer", async () => {
    stubApi([{ kind: "practice_count", series: null, key: null, first: null, count: 100 }]);
    renderEditor();

    fireEvent.click(await screen.findByRole("button", { name: /Practiced/ }));

    const card = await screen.findByText(/practices in your log/);
    expect(visible(card)).toBe("🎉 100 practices in your log. Thank you for coming to the mat.");
    expect(haptics.notify).toHaveBeenCalledWith("success");
    fireEvent.click(card);
    expect(screen.queryByText(/practices in your log/)).not.toBeInTheDocument();
  });

  it("shows no card and no success haptic otherwise", async () => {
    stubApi([{ kind: "item", series: null, key: "drop-backs", first: null, count: null }]);
    renderEditor();

    fireEvent.click(await screen.findByRole("button", { name: /Practiced/ }));

    await vi.waitFor(() => {
      expect(haptics.impact).toHaveBeenCalled();
    });
    expect(screen.queryByText(/practices in your log/)).not.toBeInTheDocument();
    expect(haptics.notify).not.toHaveBeenCalledWith("success");
  });
});

describe("DayEditor: the day's read fails", () => {
  it("says so and still closes with Done: never a dead, busy card", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(new Response(JSON.stringify({ code: "unavailable" }), { status: 503 })),
      ),
    );
    const onClose = vi.fn();
    renderEditor(onClose);

    expect(await screen.findByRole("alert")).toHaveTextContent(/^Couldn't load/);
    const card = screen.getByRole("region", { name: "Mar 1" });
    expect(card).not.toHaveAttribute("aria-busy");
    expect(within(card).getAllByRole("button").map(visible)).toEqual(["Done"]);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("is busy, with no message, while the day loads", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );
    renderEditor();

    expect(screen.getByRole("region", { name: "Mar 1" })).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// UI-06 stage 2 (Q335): the day editor is the same day card as Today's, for that date.
describe("DayEditor: the three-choice card", () => {
  const controls = () =>
    within(screen.getByRole("region", { name: "Mar 1" }))
      .getAllByRole("button")
      .map(visible);

  it("names the day at once; then the question, three choices, the note and Done", async () => {
    stubApi([]);
    const onClose = vi.fn();
    renderEditor(onClose);

    expect(screen.getByRole("heading", { level: 2, name: "Mar 1" })).toBeInTheDocument();
    expect(await screen.findByText("Practice or rest? Both go in your log.")).toBeInTheDocument();
    // An earlier day can get a note before it is logged; nothing to clear yet.
    expect(controls()).toEqual(["🧘 Practiced", "😌 Rest day", "Other…", "📓 Add a note", "Done"]);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("folds onto what was logged, with Change; Clear is behind Change, Done stays", async () => {
    stubApi([]);
    renderEditor();

    fireEvent.click(await screen.findByRole("button", { name: "😌 Rest day" }));

    const change = await screen.findByRole("button", { name: "Change" });
    expect(change).toHaveAccessibleDescription("😌 Rest day"); // the day's one line
    expect(screen.queryByText(/In your log/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Practice or rest/)).not.toBeInTheDocument();
    expect(controls()).toEqual(["Change", "📓 Add a note", "Done"]);

    fireEvent.click(change);

    expect(controls()).toEqual([
      "Change",
      "🧘 Practiced",
      "😌 Rest day",
      "Other…",
      "Clear",
      "📓 Add a note",
      "Done",
    ]);
    expect(screen.getByRole("button", { name: "😌 Rest day" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("has no 🌸 among the reasons while 🌸 days are hidden on this device", async () => {
    stubApi([]);
    renderEditor(undefined, false);

    fireEvent.click(await screen.findByRole("button", { name: "Other…" }));

    const reasons = screen.getByRole("group", { name: /Pick what fits/ });
    expect(within(reasons).getAllByRole("button").map(visible)).toEqual([
      "🌙 Moon day",
      "🤒 Sick / injury",
      "✈️ Travel",
      "🌱 No practice",
    ]);
  });
});
