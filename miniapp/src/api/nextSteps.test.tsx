import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import { useInvite, useRemoveShalaMember, useRemoveStudent, useSetDay, type Days } from "./client";

// UI-06 (spec §6): the Today tab's next step is derived by the server, so the app asks again
// exactly when something it is derived from changed: no more, no less.

vi.mock("../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  allowBotMessages: vi.fn(() => Promise.resolve(false)),
}));

const NEXT_STEPS = ["next-steps"];
const TODAY = "2026-11-16";
const SHALA = "00000000-0000-0000-0000-0000000000c1";
const SOMEONE = "00000000-0000-0000-0000-0000000000b1";

const json = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const days = (status: string | null): Days =>
  ({
    today: TODAY,
    timezone_known: true,
    days: status ? [{ date: TODAY, status, practices: [], check_ins: [] }] : [],
    auto: [],
    moon_location: "mysuru",
    notes: [],
    periods: [],
    practice_on: false,
  }) as Days;

/** A cache that holds the steps (fresh) and, with `logged`, today's day. */
function setup(logged?: string | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(NEXT_STEPS, []);
  if (logged !== undefined) client.setQueryData(["days", "recent"], days(logged));
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { wrapper, stale: () => client.getQueryState(NEXT_STEPS)?.isInvalidated === true };
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) =>
      Promise.resolve(
        request.method === "DELETE"
          ? json(null, 204)
          : json({ date: TODAY, status: "practiced", url: "https://t.me/x", qr: "" }),
      ),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("what makes the app ask for the next steps again", () => {
  it("the invite link: making it opens the invite step", async () => {
    const { wrapper, stale } = setup();
    const { result } = renderHook(() => useInvite(), { wrapper });

    await act(() => result.current.mutateAsync(false));

    expect(stale()).toBe(true);
  });

  it("removing a student: the last one gone brings the invite step back", async () => {
    const { wrapper, stale } = setup();
    const { result } = renderHook(() => useRemoveStudent(), { wrapper });

    await act(() => result.current.mutateAsync(SOMEONE));

    expect(stale()).toBe(true);
  });

  it("removing a shala's student: its last one gone brings the shala invite step back", async () => {
    const { wrapper, stale } = setup();
    const { result } = renderHook(() => useRemoveShalaMember(SHALA), { wrapper });

    await act(() => result.current.mutateAsync({ account: SOMEONE, side: "students" }));

    expect(stale()).toBe(true);
  });
});

describe("a day tap", () => {
  it.each([
    ["the first log of the day", null, "rest", true],
    ["a cleared day", "rest", null, true],
    ["another status on a logged day", "rest", "practiced", false],
    ["a reason on a logged day", "practiced", "sick", false],
  ] as const)("%s", async (_name, before, status, asks) => {
    const { wrapper, stale } = setup(before);
    const { result } = renderHook(() => useSetDay(), { wrapper });

    await act(() => result.current.mutateAsync({ date: TODAY, status }));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    // The steps follow "has any logged day", not which status a day has.
    expect(stale()).toBe(asks);
  });

  it("asks again when no cached range knows the day", async () => {
    const { wrapper, stale } = setup();
    const { result } = renderHook(() => useSetDay(), { wrapper });

    await act(() => result.current.mutateAsync({ date: TODAY, status: "practiced" }));

    expect(stale()).toBe(true);
  });
});
