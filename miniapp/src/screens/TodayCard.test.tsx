import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import type { Days } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import { haptics } from "../telegram";
import { TodayCard } from "./TodayCard";

vi.mock("../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
}));

const TODAY = "2026-10-18";

function json(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** GET /me/days returns `days`; writes answer with `writeStatus` (0 = never answer).
 * Records every request. */
/** Older fixtures predate WH-01: `periods` / `practice_on` default to none / off. */
type DaysFixture = Omit<Days, "periods" | "practice_on"> & Partial<Days>;

function stubApi(fixture: DaysFixture, writeStatus = 200): Request[] {
  const days: Days = { periods: [], practice_on: false, ...fixture };
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      seen.push(request);
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/me/moon-days")
        return Promise.resolve(
          json({ location: { slug: "mysuru", explicit: false }, today: TODAY, days: [] }),
        );
      if (path === "/api/v1/moon/cities") return Promise.resolve(json([]));
      if (request.method === "GET") {
        const deleted = seen.some((r) => r.method === "DELETE");
        return Promise.resolve(json(deleted ? { ...days, days: [] } : days));
      }
      if (writeStatus === 0) return new Promise<Response>(() => undefined);
      if (writeStatus !== 200 && writeStatus !== 204)
        return Promise.resolve(json({ code: "unavailable" }, writeStatus));
      return Promise.resolve(
        request.method === "DELETE"
          ? json(null, 204)
          : json({ date: TODAY, status: "rest", practices: [], check_ins: [] }),
      );
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

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("TodayCard", () => {
  it("highlights today's status from the server", async () => {
    stubApi({
      today: TODAY,
      timezone_known: true,
      auto: [],
      moon_location: "mysuru",
      days: [
        { date: "2026-10-17", status: "rest", practices: [], check_ins: [] },
        { date: TODAY, status: "moon", practices: [], check_ins: [] },
      ],
    });

    renderCard();

    const pressed = await screen.findByRole("button", { pressed: true });
    expect(visible(pressed)).toBe("🌙 Moon day");
    expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(6);
  });

  it("saves a tap optimistically with haptic feedback", async () => {
    const seen = stubApi(
      { today: TODAY, timezone_known: true, auto: [], moon_location: "mysuru", days: [] },
      0,
    );
    renderCard();
    const rest = await screen.findByRole("button", { name: /Rest day/ });

    fireEvent.click(rest);

    expect(haptics.impact).toHaveBeenCalledWith("light");
    // Highlighted although the server never answers this PUT.
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
    stubApi(
      { today: TODAY, timezone_known: true, auto: [], moon_location: "mysuru", days: [] },
      503,
    );
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: /Practiced/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Couldn't save/);
    expect(screen.queryByRole("button", { pressed: true })).not.toBeInTheDocument();
    expect(haptics.notify).toHaveBeenCalledWith("error");
  });

  it("shows the privacy note for a ladies' holiday and can clear it", async () => {
    const seen = stubApi({
      today: TODAY,
      timezone_known: true,
      auto: [],
      moon_location: "mysuru",
      days: [{ date: TODAY, status: "ladies", practices: [], check_ins: [] }],
    });
    renderCard();

    expect(await screen.findByText(/Only you see this/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "DELETE")).toBe(true);
    });
    expect(screen.queryByText(/Only you see this/)).not.toBeInTheDocument();
  });

  it("says so when today's status can't be loaded", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(json({ code: "unavailable" }, 503))),
    );

    renderCard();

    expect(await screen.findByRole("status")).toHaveTextContent(/Couldn't load/);
  });

  it("renders nothing until the days are loaded", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => undefined)),
    );

    const { container } = renderCard();

    expect(container).toBeEmptyDOMElement();
  });

  describe("first-log hint", () => {
    const empty: DaysFixture = {
      today: TODAY,
      timezone_known: true,
      auto: [],
      moon_location: "mysuru",
      days: [],
    };
    const hint = "Start by logging today: practice or rest.";

    it("shows until this device saves a day, and stays hidden after", async () => {
      stubApi(empty);
      const { unmount } = renderCard();

      expect(await screen.findByText(hint)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "😌 Rest day" }));
      await vi.waitFor(() => {
        expect(localStorage.getItem("onboard.logged")).toBe("1");
      });
      unmount();

      stubApi(empty);
      renderCard();
      await screen.findByRole("button", { name: "😌 Rest day" });
      expect(screen.queryByText(hint)).not.toBeInTheDocument();
    });

    it("never shows to someone who already logs (e.g. in the bot)", async () => {
      stubApi({
        today: TODAY,
        timezone_known: true,
        auto: [],
        moon_location: "mysuru",
        days: [{ date: "2026-10-17", status: "practiced", practices: [], check_ins: [] }], // yesterday
      });
      renderCard();

      await screen.findByRole("button", { name: "😌 Rest day" });
      expect(screen.queryByText(hint)).not.toBeInTheDocument();
    });
  });
});

describe("TodayCard auto-rest (PR-09)", () => {
  function stubAuto(auto: Days["auto"]) {
    vi.stubGlobal(
      "fetch",
      vi.fn((request: Request) => {
        const path = new URL(request.url).pathname;
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

  it("names the moon day once, with no chip pressed", async () => {
    stubAuto([{ date: TODAY, kind: "moon", also_day_off: true }]);
    renderCard();

    const note = await screen.findByText(/a traditional rest day/);
    expect(visible(note)).toBe(
      "🌙 Moon day (📍 Mysuru), a traditional rest day and your weekly day off too. If you practiced, log it below.",
    );
    expect(screen.queryByText(/Full moon today/)).not.toBeInTheDocument();
    expect(screen.queryAllByRole("button", { pressed: true })).toHaveLength(0);
  });

  it("shows the day off as rest until something is logged", async () => {
    stubAuto([{ date: TODAY, kind: "day_off", also_day_off: false }]);
    renderCard();

    expect(await screen.findByText(/Your weekly day off, shown as rest/)).toBeInTheDocument();
  });
});
