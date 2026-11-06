import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import { TodayCard } from "../TodayCard";
import { TourOffer } from "./TourOffer";

// UI-02: offered once, after the first log, decided when Home opens, one question at a time.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  enableClosingConfirmation: vi.fn(),
  disableClosingConfirmation: vi.fn(),
}));

const TODAY = "2026-11-06";
const OFFER = "Want a quick look around? It takes a minute.";
const HINT = "Start by logging today: practice or rest.";
const logged = [{ date: TODAY, status: "rest", practices: [], check_ins: [] }];

function stubApi(days: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: Request) => {
      const path = new URL(input.url).pathname;
      const body = path.endsWith("/moon/cities")
        ? []
        : path.endsWith("/me/days")
          ? {
              today: TODAY,
              timezone_known: true,
              days,
              auto: [],
              moon_location: "mysuru",
              notes: [],
              periods: [],
            }
          : path.includes("/days/")
            ? { date: TODAY, status: "rest", practices: [], check_ins: [] }
            : { days: [], location: { slug: "mysuru", explicit: false } };
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }),
  );
}

function renderOffer(zone: string | null = null, onStart = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale="en">
        <TodayCard zone={zone} locale="en" />
        <TourOffer zone={zone} onStart={onStart} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("a newcomer gets the first-log hint, never the offer", async () => {
  stubApi([]);
  renderOffer();
  await screen.findByText(HINT);

  expect(screen.queryByText(OFFER)).not.toBeInTheDocument();
});

test("someone with days from the bot gets it on the first open, without the hint", async () => {
  stubApi(logged);
  renderOffer();

  expect(await screen.findByText(OFFER)).toBeInTheDocument();
  expect(screen.queryByText(HINT)).not.toBeInTheDocument();
});

test("a log on this device brings it the next time Home opens, not under the thumb", async () => {
  stubApi([]);
  const first = renderOffer();
  await screen.findByText(HINT);
  fireEvent.click(screen.getByRole("button", { name: /Rest day/ }));
  await settle();
  expect(screen.queryByText(OFFER)).not.toBeInTheDocument();
  first.unmount();

  renderOffer();

  expect(await screen.findByText(OFFER)).toBeInTheDocument();
});

test("Not now is remembered and starts nothing", async () => {
  stubApi(logged);
  const onStart = vi.fn();
  const first = renderOffer(null, onStart);
  fireEvent.click(await screen.findByRole("button", { name: "Not now" }));

  expect(screen.queryByText(OFFER)).not.toBeInTheDocument();
  expect(onStart).not.toHaveBeenCalled();
  first.unmount();
  renderOffer();
  await settle();
  expect(screen.queryByText(OFFER)).not.toBeInTheDocument();
});

test("Show me starts the tour and is remembered too", async () => {
  stubApi(logged);
  const onStart = vi.fn();
  renderOffer(null, onStart);
  fireEvent.click(await screen.findByRole("button", { name: "Show me" }));

  expect(onStart).toHaveBeenCalledOnce();
  expect(localStorage.getItem("onboard.tour")).toBe("1");
});

test("a pending travel prompt goes first", async () => {
  stubApi(logged);
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
    timeZone: "Asia/Bangkok",
  } as Intl.ResolvedDateTimeFormatOptions);
  renderOffer("Asia/Almaty");
  await settle();

  expect(screen.queryByText(OFFER)).not.toBeInTheDocument();
});

test("blocked storage means no offer", async () => {
  stubApi(logged);
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  renderOffer();
  await settle();

  expect(screen.queryByText(OFFER)).not.toBeInTheDocument();
});
