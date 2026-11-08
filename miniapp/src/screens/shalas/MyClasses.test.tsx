import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import MyClasses from "./MyClasses";

// SC-02 "My classes": a teacher's next 7 days per staff shala, each in the shala's zone, with
// who covers whom; the empty state. The API and the Telegram SDK are mocked.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
}));

const SHALA = "00000000-0000-0000-0000-0000000000c1";
const CLASS = "00000000-0000-0000-0000-0000000000d1";
const ME = "00000000-0000-0000-0000-000000000001";
const ANNA = "00000000-0000-0000-0000-0000000000a1";

const mine = (over: Record<string, unknown> = {}) => ({
  class_id: CLASS,
  key: "2026-11-09",
  on: "2026-11-09",
  start: "06:00",
  end: "09:30",
  starts_at: "2026-11-09T01:00:00Z",
  type: "mysore",
  title: null,
  online: false,
  teacher: { id: ME, name: "Ash" },
  substitute: false,
  cancelled: null,
  moved: false,
  swapped_from: null,
  held: false,
  usual_teacher: { id: ME, name: "Ash" },
  role: "teaching",
  ...over,
});

const WEEK = [
  {
    shala_id: SHALA,
    name: "Ashtanga Almaty",
    zone: "Asia/Almaty",
    today: "2026-11-07",
    classes: [
      mine(),
      mine({
        key: "2026-11-10",
        on: "2026-11-10",
        starts_at: "2026-11-10T01:00:00Z",
        teacher: { id: ANNA, name: "Anna" },
        substitute: true,
        role: "covered",
      }),
      mine({
        class_id: "00000000-0000-0000-0000-0000000000d2",
        key: "2026-11-10",
        on: "2026-11-10",
        start: "07:00",
        end: "08:30",
        starts_at: "2026-11-10T02:00:00Z",
        type: "led",
        substitute: true,
        usual_teacher: { id: ANNA, name: "Anna" },
        role: "covering",
      }),
      mine({
        key: "2026-11-11",
        on: "2026-11-11",
        starts_at: "2026-11-11T01:00:00Z",
        cancelled: "moon",
      }),
    ],
  },
];

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

function stubApi(week: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      await Promise.resolve();
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/me/classes") return json(week);
      if (path === "/api/v1/me")
        return json({ id: ME, display_name: "Ash", locale: "en", timezone: "Asia/Almaty" });
      return json({});
    }),
  );
}

function renderWith(locale: Locale = "en") {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <L10nProvider locale={locale}>
        <MyClasses locale={locale} onBack={vi.fn()} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
const rows = () => [...document.querySelectorAll(".link-person")].map((p) => plain(p.textContent));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("my classes", () => {
  it("lists my week per shala, in its zone, with who covers whom", async () => {
    stubApi(WEEK);
    renderWith();

    expect(await screen.findByRole("heading", { name: "Ashtanga Almaty" })).toBeInTheDocument();
    expect(screen.getByText("Almaty (UTC+5)")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(3);
    expect(rows()).toEqual([
      "06:00–09:30 Mysore",
      "06:00–09:30 Mysore · Anna is covering",
      "07:00–08:30 Led · you're covering for Anna",
      "❌ 06:00–09:30 Mysore (moon day)",
    ]);
  });

  it("speaks Russian", async () => {
    stubApi(WEEK);
    renderWith("ru");

    await screen.findByRole("heading", { name: "Ashtanga Almaty" });
    expect(rows()).toContain("06:00–09:30 Майсор · тебя заменяет Anna");
    expect(rows().some((r) => /^07:00–08:30 .+ · ты заменяешь Anna$/.test(r))).toBe(true);
  });

  it("says so when there are none", async () => {
    stubApi([]);
    renderWith();

    expect(await screen.findByText(/No classes of yours in the next 7 days/)).toBeInTheDocument();
  });
});
