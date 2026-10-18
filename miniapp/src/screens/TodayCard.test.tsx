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
function stubApi(days: Days, writeStatus = 200): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      seen.push(request);
      if (request.method === "GET") return Promise.resolve(json(days));
      if (writeStatus === 0) return new Promise<Response>(() => undefined);
      if (writeStatus !== 200 && writeStatus !== 204)
        return Promise.resolve(json({ code: "unavailable" }, writeStatus));
      return Promise.resolve(
        request.method === "DELETE" ? json(null, 204) : json({ date: TODAY, status: "rest" }),
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
        <TodayCard />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const visible = (el: HTMLElement) => el.textContent.replace(/[⁨⁩]/g, "");

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TodayCard", () => {
  it("highlights today's status from the server", async () => {
    stubApi({
      today: TODAY,
      timezone_known: true,
      days: [
        { date: "2026-10-17", status: "rest" },
        { date: TODAY, status: "moon" },
      ],
    });

    renderCard();

    const pressed = await screen.findByRole("button", { pressed: true });
    expect(visible(pressed)).toBe("🌙 Moon day");
    expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(6);
  });

  it("saves a tap optimistically with haptic feedback", async () => {
    const seen = stubApi({ today: TODAY, timezone_known: true, days: [] }, 0);
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
    stubApi({ today: TODAY, timezone_known: true, days: [] }, 503);
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
      days: [{ date: TODAY, status: "ladies" }],
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
});
