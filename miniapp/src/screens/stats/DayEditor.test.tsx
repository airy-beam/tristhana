import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import { haptics } from "../../telegram";
import { DayEditor } from "./DayEditor";

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
}));

const TODAY = "2026-10-30";
const DAY = "2026-03-01"; // a backfill

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** GET /me/days: an empty day; PUT answers with `celebrations`. */
function stubApi(celebrations: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      if (request.method === "PUT") {
        return Promise.resolve(
          json({ date: DAY, status: "practiced", practices: [], check_ins: [], celebrations }),
        );
      }
      return Promise.resolve(
        json({
          today: TODAY,
          timezone_known: true,
          days: [],
          auto: [],
          moon_location: "mysuru",
          periods: [],
          practice_on: false,
          notes: [],
        }),
      );
    }),
  );
}

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale="en">
        <DayEditor
          date={DAY}
          label="Mar 1"
          zone="Asia/Almaty"
          locale="en"
          showLadies
          onClose={() => undefined}
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
