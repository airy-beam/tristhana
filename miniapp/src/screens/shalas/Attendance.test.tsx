import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { MyRow, MySchedule as Week, Roster } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import Attendance from "./Attendance";
import MySchedule from "./MySchedule";

// SC-05 attendance: "🙋 I was there" on My schedule rows (claim, "🧘 Log this day" only after
// asana or pranayama practice, Q196; remove after an ask; week −1), and the staff roster
// (counts, ticks sent as one PATCH of deltas, confirm all, a closed occurrence). API and the
// Telegram SDK mocked.

const tg = vi.hoisted(() => ({
  confirmDestructive: vi.fn(async () => Promise.resolve(true)),
}));

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  confirmDestructive: tg.confirmDestructive,
}));

const SHALA = "00000000-0000-0000-0000-0000000000c1";
const CLASS = "00000000-0000-0000-0000-0000000000d1";
const CONF = "00000000-0000-0000-0000-0000000000d2";
const ME = "00000000-0000-0000-0000-000000000001";
const VERA = "00000000-0000-0000-0000-0000000000b1";
const DANA = "00000000-0000-0000-0000-0000000000b2";
const TARA = "00000000-0000-0000-0000-0000000000b3";
const ANNA = { id: "00000000-0000-0000-0000-0000000000a1", name: "Anna" };

const row = (over: Partial<MyRow> = {}): MyRow => ({
  class_id: CLASS,
  key: "2026-11-09",
  on: "2026-11-09",
  start: "06:00",
  end: "09:30",
  starts_at: "2026-11-09T01:00:00Z",
  type: "mysore",
  title: null,
  online: false,
  teacher: ANNA,
  substitute: false,
  cancelled: null,
  moved: false,
  swapped_from: null,
  held: false,
  usual_teacher: ANNA,
  moon: false,
  swapped_to: null,
  shala_id: SHALA,
  zone: "Asia/Almaty",
  city: "almaty",
  role: null,
  my_teacher: false,
  planned: "06:00",
  attendance: null,
  can_claim: true,
  attendance_counts: null,
  ...over,
});

const WEEK: Week = {
  zone: "Asia/Almaty",
  zone_known: true,
  today: "2026-11-09",
  moon_city: "almaty",
  days: Array.from({ length: 7 }, (_, i) => ({
    date: `2026-11-${String(9 + i).padStart(2, "0")}`,
    my_moon: false,
  })),
  shalas: [
    { id: SHALA, name: "Ashtanga Almaty", city: "almaty", zone: "Asia/Almaty", staff: false },
  ],
  has_teachers: false,
  is_staff: false,
  shifts: [],
  occurrences: [
    row(),
    row({
      class_id: CONF,
      type: "conference",
      start: "10:00",
      end: "11:00",
      starts_at: "2026-11-09T05:00:00Z",
    }),
    row({
      key: "2026-11-08",
      on: "2026-11-10",
      starts_at: "2026-11-10T01:00:00Z",
      can_claim: false,
    }),
  ],
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Seen {
  method: string;
  path: string;
  search: string;
  body: unknown;
}
let seen: Seen[] = [];

function stubApi(routes: (r: Seen) => Response | undefined) {
  seen = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const url = new URL(request.url);
      const text = request.method === "GET" ? "" : await request.text();
      const r = {
        method: request.method,
        path: url.pathname,
        search: url.search,
        body: text ? (JSON.parse(text) as unknown) : null,
      };
      seen.push(r);
      const found = routes(r);
      if (found) return found;
      if (url.pathname === "/api/v1/me")
        return json({ id: ME, display_name: "Ash", locale: "en", timezone: "Asia/Almaty" });
      return json({});
    }),
  );
}

const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });
const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");

afterEach(() => {
  vi.unstubAllGlobals();
  tg.confirmDestructive.mockClear();
});

function renderMine(locale: Locale = "en") {
  return render(
    <QueryClientProvider client={client()}>
      <L10nProvider locale={locale}>
        <MySchedule locale={locale} onBack={vi.fn()} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

describe("my schedule: I was there", () => {
  it("claims a started row and offers Log this day", async () => {
    stubApi((r) => {
      if (r.path === "/api/v1/me/schedule") return json(WEEK);
      if (r.method === "PUT")
        return json({
          class_id: CLASS,
          key: "2026-11-09",
          state: "claimed",
          day: "2026-11-09",
          log_day: true,
        });
      return undefined;
    });
    renderMine();

    const buttons = await screen.findAllByRole("button", { name: "🙋 I was there" });
    expect(buttons).toHaveLength(2); // the third row hasn't started
    fireEvent.click(buttons[0] as HTMLElement);

    const status = await screen.findByRole("status");
    expect(plain(status.textContent)).toContain("🙋 Marked:");
    expect(plain(status.textContent)).toContain("The shala's staff can confirm it.");
    expect(seen.some((r) => r.method === "PUT" && r.path.endsWith(`/${CLASS}/2026-11-09`))).toBe(
      true,
    );
    expect(screen.getByRole("button", { name: "🧘 Log this day" })).toBeInTheDocument();
  });

  it("offers no Log this day after a conference (Q196)", async () => {
    stubApi((r) => {
      if (r.path === "/api/v1/me/schedule") return json(WEEK);
      if (r.method === "PUT")
        return json({
          class_id: CONF,
          key: "2026-11-09",
          state: "claimed",
          day: "2026-11-09",
          log_day: false,
        });
      return undefined;
    });
    renderMine();

    const buttons = await screen.findAllByRole("button", { name: "🙋 I was there" });
    fireEvent.click(buttons[1] as HTMLElement);

    await screen.findByRole("status");
    expect(screen.queryByRole("button", { name: "🧘 Log this day" })).not.toBeInTheDocument();
  });

  it("asks before removing my mark", async () => {
    const marked = {
      ...WEEK,
      occurrences: [row({ attendance: "confirmed" })],
    };
    stubApi((r) => (r.path === "/api/v1/me/schedule" ? json(marked) : undefined));
    renderMine();

    fireEvent.click(await screen.findByRole("button", { name: "✅ confirmed" }));

    await waitFor(() => {
      expect(seen.some((r) => r.method === "DELETE")).toBe(true);
    });
    expect(tg.confirmDestructive).toHaveBeenCalledWith("Remove your mark?", "Remove", "Cancel");
  });

  it("pages down to last week", async () => {
    stubApi((r) => (r.path === "/api/v1/me/schedule" ? json(WEEK) : undefined));
    renderMine();

    const prev = await screen.findByRole("button", { name: "◀" });
    expect(prev).toBeEnabled();
    fireEvent.click(prev);

    await waitFor(() => {
      expect(seen.some((r) => r.search.includes("from=2026-11-02"))).toBe(true);
    });
  });

  it("speaks Russian", async () => {
    stubApi((r) => (r.path === "/api/v1/me/schedule" ? json(WEEK) : undefined));
    renderMine("ru");

    expect(await screen.findAllByRole("button", { name: "🙋 Отметиться" })).toHaveLength(2);
  });
});

const ROSTER: Roster = {
  shala_id: SHALA,
  shala_name: "Ashtanga Almaty",
  occurrence: {
    key: "2026-11-09",
    on: "2026-11-09",
    start: "06:00",
    end: "09:30",
    starts_at: "2026-11-09T01:00:00Z",
    zone: "Asia/Almaty",
    city: "almaty",
    type: "mysore",
    title: null,
    cancelled: false,
  },
  attendable: true,
  confirmed: 1,
  claimed: 1,
  people: [
    { account_id: DANA, name: "Dana", state: "claimed", staff: false },
    { account_id: TARA, name: "Tara", state: "confirmed", staff: true },
    { account_id: VERA, name: "Vera", state: null, staff: false },
  ],
  more: false,
};

function renderRoster(locale: Locale = "en") {
  return render(
    <QueryClientProvider client={client()}>
      <L10nProvider locale={locale}>
        <Attendance
          shalaId={SHALA}
          classId={CLASS}
          occurrenceKey="2026-11-09"
          locale={locale}
          onClose={vi.fn()}
        />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const rosterPath = `/api/v1/shalas/${SHALA}/classes/${CLASS}/occurrences/2026-11-09/attendance`;

describe("staff roster", () => {
  it("shows counts and people, and saves ticks as one delta", async () => {
    stubApi((r) => {
      if (r.path === rosterPath && r.method === "GET") return json(ROSTER);
      if (r.path === rosterPath && r.method === "PATCH") return json({ confirmed: 2, claimed: 1 });
      return undefined;
    });
    renderRoster();

    expect(await screen.findByText("✅ 1 · 🙋 1 to confirm")).toBeInTheDocument();
    expect(screen.getByText("staff")).toBeInTheDocument();
    expect(screen.getByText(/Almaty \(UTC\+5\)/)).toBeInTheDocument();
    const vera = screen.getByRole("checkbox", { name: /Vera/ });
    const tara = screen.getByRole("checkbox", { name: /Tara/ });
    expect(tara).toBeChecked();
    fireEvent.click(vera);
    fireEvent.click(tara);

    fireEvent.click(screen.getByRole("button", { name: "Save (2 changes)" }));

    await waitFor(() => {
      const patch = seen.find((r) => r.method === "PATCH");
      expect(patch?.body).toEqual({ confirm_claims: false, present: [VERA], removed: [TARA] });
    });
  });

  it("confirms every claim", async () => {
    stubApi((r) => {
      if (r.path === rosterPath && r.method === "GET") return json(ROSTER);
      if (r.method === "PATCH") return json({ confirmed: 2, claimed: 0 });
      return undefined;
    });
    renderRoster();

    fireEvent.click(await screen.findByRole("button", { name: "✅ Confirm all 🙋 (1)" }));

    await waitFor(() => {
      expect(seen.find((r) => r.method === "PATCH")?.body).toEqual({ confirm_claims: true });
    });
  });

  it("says when the class can't be marked any more", async () => {
    stubApi((r) => {
      if (r.path === rosterPath && r.method === "GET") return json(ROSTER);
      if (r.method === "PATCH") return json({ code: "not_attendable" }, 409);
      return undefined;
    });
    renderRoster();

    fireEvent.click(await screen.findByRole("checkbox", { name: /Vera/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save (1 change)" }));

    expect(await screen.findByText(/can't be marked now/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Vera/ })).toBeDisabled();
  });

  it("sends pending ticks with Confirm all, then clears them", async () => {
    stubApi((r) => {
      if (r.path === rosterPath && r.method === "GET") return json(ROSTER);
      if (r.method === "PATCH") return json({ confirmed: 3, claimed: 0 });
      return undefined;
    });
    renderRoster();

    fireEvent.click(await screen.findByRole("checkbox", { name: /Vera/ }));
    expect(screen.getByRole("button", { name: "Save (1 change)" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "✅ Confirm all 🙋 (1)" }));

    await waitFor(() => {
      expect(seen.find((r) => r.method === "PATCH")?.body).toEqual({
        confirm_claims: true,
        present: [VERA],
      });
    });
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /^Save/ })).not.toBeInTheDocument();
    });
  });

  it.each([
    ["a 422", () => json({ code: "invalid_attendance" }, 422)],
    ["a 500", () => json({ code: "internal" }, 500)],
    [
      "a network error",
      () => {
        throw new TypeError("Failed to fetch");
      },
    ],
  ])("says when saving fails with %s and keeps the ticks", async (_, fail) => {
    stubApi((r) => {
      if (r.path === rosterPath && r.method === "GET") return json(ROSTER);
      if (r.method === "PATCH") return fail();
      return undefined;
    });
    renderRoster();

    fireEvent.click(await screen.findByRole("checkbox", { name: /Vera/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save (1 change)" }));

    expect(await screen.findByText("Couldn't save the mark. Try again in a moment.")).toBeVisible();
    expect(screen.getByRole("checkbox", { name: /Vera/ })).toBeChecked();
    expect(screen.getByRole("button", { name: "Save (1 change)" })).toBeEnabled();
  });

  it("asks to save first past 100 changes", async () => {
    const many = Array.from({ length: 101 }, (_, i) => ({
      account_id: `00000000-0000-0000-0000-${String(i).padStart(12, "0")}`,
      name: `P${String(i)}`,
      state: null,
      staff: false,
    }));
    stubApi((r) =>
      r.path === rosterPath && r.method === "GET" ? json({ ...ROSTER, people: many }) : undefined,
    );
    renderRoster();

    const boxes = await screen.findAllByRole("checkbox");
    const last = boxes.at(100);
    if (!last) throw new Error("expected 101 checkboxes");
    for (const box of boxes.slice(0, 100)) fireEvent.click(box);
    expect(screen.queryByText(/save these first/)).not.toBeInTheDocument();
    fireEvent.click(last);

    expect(screen.getByText("Up to 100 changes at a time: save these first.")).toBeVisible();
    expect(last).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Save (100 changes)" })).toBeInTheDocument();
  });

  it("speaks Russian with plurals", async () => {
    stubApi((r) => (r.path === rosterPath ? json({ ...ROSTER, claimed: 3 }) : undefined));
    renderRoster("ru");

    expect(await screen.findByText("✅ 1 · 🙋 3 ждут подтверждения")).toBeInTheDocument();
    expect(screen.getByText("из команды")).toBeInTheDocument();
  });
});
