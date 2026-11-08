import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import CalendarFeedCard from "./CalendarFeedCard";

// SC-06: the calendar subscription card. Off → create; on → the link to copy, Google and
// Apple/Outlook via https only, the 🔒 line and the last check; a new link and turning off ask
// first (Telegram's popup). Hidden when the server offers no links. API and SDK mocked.

const tg = vi.hoisted(() => ({
  openLink: vi.fn(),
  confirmDestructive: vi.fn(async () => Promise.resolve(true)),
}));

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  openLink: tg.openLink,
  confirmDestructive: tg.confirmDestructive,
}));

const PUBLIC = "https://tristhana-api.example.run.app";
const TOKEN = "Xy3kP9qR2sT5uV8wZ1aB4cD7eF0gH3iJ6kL9mN2oP5q";
const NEW = "Qm7nB4vC1xZ8lK5jH2gF9dS6aP3oI0uY7tR4eW1q-_A";

const on = (token: string, fetched: string | null = null) => ({
  on: true,
  available: true,
  url: `${PUBLIC}/ical/v1/${token}.ics`,
  google_url: `https://calendar.google.com/calendar/r?cid=webcal%3A%2F%2Fx%2F${token}`,
  subscribe_url: `${PUBLIC}/ical/v1/${token}/subscribe`,
  created_at: "2026-11-01T09:15:00Z",
  fetched_on: fetched,
});
const OFF = {
  on: false,
  available: true,
  url: null,
  google_url: null,
  subscribe_url: null,
  created_at: null,
  fetched_on: null,
};

const json = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

let calls: string[] = [];

function stubApi(state: unknown, shalas: unknown[] = [{ id: "s1" }]) {
  calls = [];
  let current = state;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      await Promise.resolve();
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/me/calendar-feed/rotate") {
        calls.push("ROTATE");
        current = on(NEW);
        return json(current);
      }
      if (path === "/api/v1/me/calendar-feed") {
        calls.push(request.method);
        if (request.method === "POST" && !(current as { on: boolean }).on) current = on(NEW);
        if (request.method === "DELETE") {
          current = OFF;
          return json(null, 204);
        }
        return json(current);
      }
      if (path === "/api/v1/me/shalas") return json(shalas);
      return json({});
    }),
  );
}

function renderWith(locale: Locale = "en") {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <L10nProvider locale={locale}>
        <CalendarFeedCard locale={locale} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const flat = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");

beforeEach(() => {
  tg.openLink.mockClear();
  tg.confirmDestructive.mockClear();
  tg.confirmDestructive.mockImplementation(async () => Promise.resolve(true));
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("calendar subscription", () => {
  it("is hidden when the server offers no links", async () => {
    stubApi({ ...OFF, available: false });
    const { container } = renderWith();

    await waitFor(() => {
      expect(calls).toContain("GET");
    });
    expect(container).toBeEmptyDOMElement();
  });

  it("offers to create the link, then shows it", async () => {
    stubApi(OFF);
    renderWith();

    fireEvent.click(await screen.findByRole("button", { name: "📅 Create my link" }));

    expect(await screen.findByText(`${PUBLIC}/ical/v1/${NEW}.ics`)).toBeInTheDocument();
    expect(calls).toContain("POST");
    expect(screen.getByText("Not used by a calendar yet")).toBeInTheDocument();
  });

  it("says moon days come alone without a shala", async () => {
    stubApi(OFF, []);
    renderWith();

    expect(
      await screen.findByText("Join a shala to see its classes here too."),
    ).toBeInTheDocument();
  });

  it("opens Google and Apple/Outlook by https only, and copies the link", async () => {
    stubApi(on(TOKEN, "2026-11-07"));
    const writeText = vi.fn(async () => Promise.resolve());
    Object.assign(navigator, { clipboard: { writeText } });
    renderWith();

    fireEvent.click(await screen.findByRole("button", { name: "Add to Google Calendar" }));
    fireEvent.click(screen.getByRole("button", { name: "Add to Apple / Outlook" }));
    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));

    const opened = tg.openLink.mock.calls.map((c: unknown[]) => String(c[0]));
    expect(opened).toEqual([on(TOKEN).google_url, on(TOKEN).subscribe_url]);
    expect(opened.every((u) => u.startsWith("https://"))).toBe(true);
    expect(await screen.findByRole("button", { name: "✓ Copied" })).toBeInTheDocument();
    // Q161: a phone can't subscribe through Google's link, so the card says how.
    expect(screen.getByText(/Do it once on a computer/)).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(`${PUBLIC}/ical/v1/${TOKEN}.ics`);
    expect(flat(screen.getByText(/Last checked by a calendar/).textContent)).toBe(
      "Last checked by a calendar: Sat, Nov 7",
    );
    const stored = Object.keys(localStorage).map((k) => localStorage.getItem(k) ?? "");
    expect(stored.join(" ")).not.toContain(TOKEN);
  });

  it("asks before a new link", async () => {
    stubApi(on(TOKEN));
    renderWith();

    tg.confirmDestructive.mockImplementationOnce(async () => Promise.resolve(false));
    fireEvent.click(await screen.findByRole("button", { name: "🔄 New link" }));
    await waitFor(() => {
      expect(tg.confirmDestructive).toHaveBeenCalledTimes(1);
    });
    expect(calls).not.toContain("ROTATE");

    fireEvent.click(screen.getByRole("button", { name: "🔄 New link" }));

    expect(await screen.findByText(`${PUBLIC}/ical/v1/${NEW}.ics`)).toBeInTheDocument();
  });

  it("asks before turning off", async () => {
    stubApi(on(TOKEN));
    renderWith();

    fireEvent.click(await screen.findByRole("button", { name: "Turn off" }));

    expect(await screen.findByRole("button", { name: "📅 Create my link" })).toBeInTheDocument();
    expect(calls).toContain("DELETE");
    expect(tg.confirmDestructive).toHaveBeenCalledTimes(1);
  });

  it("says when an action failed", async () => {
    stubApi(OFF);
    const ok = globalThis.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) =>
        request.method === "POST"
          ? new Response("{}", { status: 503, headers: { "Content-Type": "application/json" } })
          : ok(request),
      ),
    );
    renderWith();

    fireEvent.click(await screen.findByRole("button", { name: "📅 Create my link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/didn.t work/);
  });

  it("speaks Russian", async () => {
    stubApi(on(TOKEN));
    renderWith("ru");

    expect(
      await screen.findByRole("button", { name: "Добавить в Google Календарь" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Скопировать ссылку" })).toBeInTheDocument();
    expect(screen.getByText("Календарь ещё не подключён")).toBeInTheDocument();
  });
});
