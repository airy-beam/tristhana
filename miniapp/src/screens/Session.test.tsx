import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { api, type Me } from "../api/client";
import { rawInitData } from "../telegram";
import { Session } from "./Session";

vi.mock("../telegram", () => ({ rawInitData: vi.fn(() => "user=%7B%7D&hash=abc") }));

const ME: Me = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Аня",
  locale: "ru",
  timezone: null,
  name_from_telegram: true,
  locale_from_telegram: true,
  hide_ladies: false,
  offer_check_in: true, // WH-01 part 2
};

type Route = (request: Request) => Response;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Routes by path; records every request. */
function stubApi(routes: Record<string, Route>): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      seen.push(request);
      const route = routes[new URL(request.url).pathname];
      return Promise.resolve(route ? route(request) : json({}, 404));
    }),
  );
  return seen;
}

function renderSession() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Session launchLocale="en">
        {(me) => <p>{me ? `hello ${me.display_name ?? ""}` : "loading"}</p>}
      </Session>
    </QueryClientProvider>,
  );
}

/** The zone the device reports (CI runners report UTC). */
function deviceZone(timeZone: string) {
  const options = new Intl.DateTimeFormat().resolvedOptions();
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
    ...options,
    timeZone,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Session", () => {
  it("sends the signed initData and passes the account down", async () => {
    const seen = stubApi({
      "/api/v1/me": () => json({ ...ME, timezone: "Asia/Almaty" }),
    });

    renderSession();

    expect(await screen.findByText("hello Аня")).toBeInTheDocument();
    expect(seen[0]?.headers.get("Authorization")).toBe("tma user=%7B%7D&hash=abc");
    expect(document.documentElement.lang).toBe("ru");
  });

  it("reports the device time zone once when the account has none", async () => {
    deviceZone("Asia/Almaty");
    const seen = stubApi({
      "/api/v1/me": () => json(ME),
      "/api/v1/me/device-timezone": () => json({ ...ME, timezone: "Asia/Almaty" }),
    });

    renderSession();
    await screen.findByText("hello Аня");

    await vi.waitFor(() => {
      expect(seen.filter((r) => r.url.endsWith("/device-timezone"))).toHaveLength(1);
    });
    const post = seen.find((r) => r.url.endsWith("/device-timezone"));
    expect(await post?.json()).toEqual({ timezone: "Asia/Almaty" });
  });

  it("does not report UTC, which says nothing about where the person is", async () => {
    deviceZone("UTC");
    const seen = stubApi({ "/api/v1/me": () => json(ME) });

    renderSession();
    await screen.findByText("hello Аня");

    expect(seen.map((r) => new URL(r.url).pathname)).toEqual(["/api/v1/me"]);
  });

  it("refreshes the days once the zone is reported (today may move)", async () => {
    deviceZone("Asia/Almaty");
    const seen = stubApi({
      "/api/v1/me": () => json(ME),
      "/api/v1/me/device-timezone": () => json({ ...ME, timezone: "Asia/Almaty" }),
      "/api/v1/me/days": () =>
        json({
          today: "2026-10-19",
          timezone_known: true,
          auto: [],
          moon_location: "mysuru",
          days: [],
        }),
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(["days", "recent"], {
      today: "2026-10-18",
      timezone_known: false,
      auto: [],
      moon_location: "mysuru",
      days: [],
    });
    render(
      <QueryClientProvider client={client}>
        <Session launchLocale="en">{() => <p>ok</p>}</Session>
      </QueryClientProvider>,
    );

    await vi.waitFor(() => {
      expect(client.getQueryState(["days", "recent"])?.isInvalidated).toBe(true);
    });
    expect(seen.some((r) => r.url.endsWith("/device-timezone"))).toBe(true);
  });

  it("does not report a zone when one is already set", async () => {
    const seen = stubApi({ "/api/v1/me": () => json({ ...ME, timezone: "Europe/Moscow" }) });

    renderSession();
    await screen.findByText("hello Аня");

    expect(seen.map((r) => new URL(r.url).pathname)).toEqual(["/api/v1/me"]);
  });

  it("asks to reopen the app when the session has expired", async () => {
    stubApi({ "/api/v1/me": () => json({ code: "auth_expired" }, 401) });

    renderSession();

    expect(await screen.findByRole("alert")).toHaveTextContent(/session has expired/i);
  });

  it("keeps the launch locale and renders while the server is offline", async () => {
    stubApi({ "/api/v1/me": () => json({ code: "unavailable" }, 503) });

    renderSession();

    expect(await screen.findByText("loading")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
  });
});

it("sends no auth header outside Telegram", async () => {
  vi.mocked(rawInitData).mockReturnValueOnce(undefined);
  const seen = stubApi({
    "/api/v1/health": () => json({ status: "ok", version: "1", commit: "x" }),
  });

  await api.GET("/api/v1/health");

  expect(seen[0]?.headers.has("Authorization")).toBe(false);
  vi.unstubAllGlobals();
});
