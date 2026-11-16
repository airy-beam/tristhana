import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import { L10nProvider } from "../i18n/L10nProvider";
import { haptics } from "../telegram";
import { TodayCard } from "./TodayCard";

// UI-06 stage 2 (spec §5, §8): details and the check-in editor live in their own chunk
// (`dayExtras`). On a weak connection that chunk may fail to load: the card must stay as it
// is, say so, and load the panel on the next tap.

const chunk = vi.hoisted(() => ({ fails: true }));

vi.mock("./dayExtras", async (original) => {
  if (chunk.fails) throw new Error("Failed to fetch dynamically imported module");
  return original();
});

vi.mock("../telegram", () => ({
  useBackButton: vi.fn(),
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
}));

const TODAY = "2026-10-18";

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined); // React reports what it caught
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/me") return Promise.resolve(json({ offer_check_in: true }));
      if (path === "/api/v1/catalog")
        return Promise.resolve(json({ version: "v1", series: [], check_in_tags: [] }));
      if (path.endsWith("/practice-presets"))
        return Promise.resolve(json({ last: null, presets: [] }));
      if (path === "/api/v1/me/moon-days")
        return Promise.resolve(
          json({ location: { slug: "mysuru", explicit: false }, today: TODAY, days: [] }),
        );
      if (path === "/api/v1/moon/cities") return Promise.resolve(json([]));
      return Promise.resolve(
        json({
          today: TODAY,
          timezone_known: true,
          auto: [],
          moon_location: "mysuru",
          periods: [],
          practice_on: false,
          notes: [],
          days: [{ date: TODAY, status: "practiced", practices: [], check_ins: [] }],
        }),
      );
    }),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  chunk.fails = true;
});

test("a details chunk that fails to load keeps the card; the next tap loads it", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <L10nProvider locale="en">
        <TodayCard zone="Asia/Almaty" locale="en" />
      </L10nProvider>
    </QueryClientProvider>,
  );
  const entry = await screen.findByRole("button", { name: "📝 Add details" });

  fireEvent.click(entry);

  expect(await screen.findByRole("alert")).toHaveTextContent(/Couldn't load/);
  expect(haptics.notify).toHaveBeenCalledWith("error");
  // The card is whole: the day, its choices and the entries, with the entry folded again.
  expect(screen.getByRole("heading", { level: 2, name: "Today, Sun, Oct 18" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "🧘 Practiced" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(entry).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByRole("button", { name: "✨ How do you feel?" })).toBeInTheDocument();

  chunk.fails = false; // the connection is back
  fireEvent.click(entry);

  expect(await screen.findByRole("button", { name: "Mysore" })).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
