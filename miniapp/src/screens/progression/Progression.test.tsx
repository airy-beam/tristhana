import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { Catalog, Progression as ProgressionValue } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import { haptics } from "../../telegram";
import { PracticeDetails } from "../PracticeDetails";
import Progression from "./Progression";

// PR-08 (spec §6): "🧘 My asanas" unset (suggestion, choose) and set (current line, next,
// another, items, change, history with Undo on the newest), not optimistic, the
// celebration card with haptics, 409 refetch, and the "New asana? 🎉" banner on
// PracticeDetails ("Yes, new" celebrates; "Not new" posts the dismissal).

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
}));

const TODAY = "2026-10-27";

const CATALOG: Catalog = {
  version: "v1",
  check_in_tags: [],
  milestone_items: [
    { key: "drop-backs", latin: "Drop-backs", ru: "Дроп-бэки" },
    { key: "standing-up", latin: "Standing up", ru: "Вставание из моста" },
  ],
  series: [
    {
      slug: "primary",
      number: 1,
      name_en: "Primary series",
      name_ru: "Первая серия",
      halves_split: "navasana",
      traditional: { key: "primary", latin: "Yoga Chikitsa", ru: "Йога Чикитса" },
      stops: [
        { key: "navasana", latin: "Navasana", ru: "Навасана" },
        { key: "bhujapidasana", latin: "Bhujapidasana", ru: "Бхуджапидасана" },
        { key: "kurmasana", latin: "Kurmasana", ru: "Курмасана" },
        { key: "setu-bandhasana", latin: "Setu Bandhasana", ru: "Сету Бандхасана" },
      ],
    },
    {
      slug: "intermediate",
      number: 2,
      name_en: "Intermediate series",
      name_ru: "Вторая серия",
      halves_split: null,
      traditional: { key: "intermediate", latin: "Nadi Shodhana", ru: "Нади Шодхана" },
      stops: [{ key: "pasasana", latin: "Pasasana", ru: "Пашасана" }],
    },
  ],
};

const P = (series: string | null, last: string | null) => ({ series, last });

function unset(over: Partial<ProgressionValue> = {}): ProgressionValue {
  return {
    set: false,
    position: null,
    length: null,
    by_series: [],
    items: [],
    next: null,
    later: [],
    suggested: null,
    suggested_length: null,
    events: [],
    last_event_id: null,
    today: TODAY,
    ...over,
  };
}

const AT_NAVASANA: ProgressionValue = unset({
  set: true,
  position: P("primary", "navasana"),
  length: { series: ["primary"], end: "navasana", first_part: null },
  next: P("primary", "bhujapidasana"),
  later: [
    P("primary", "bhujapidasana"),
    P("primary", "kurmasana"),
    P("primary", "setu-bandhasana"),
  ],
  events: [
    {
      id: 7,
      kind: "start",
      occurred_on: "2026-10-20",
      from: null,
      to: P("primary", "navasana"),
      item: null,
      marked_by_self: true,
    },
  ],
  last_event_id: 7,
});

const json = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

interface Stub {
  progression?: ProgressionValue;
  /** How POST …/events answers: a ChangeOut body, or an error status. */
  post?: unknown;
  postStatus?: number;
}

function stubApi({ progression = AT_NAVASANA, post, postStatus = 201 }: Stub = {}) {
  const seen: { method: string; path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname;
      const method = request.method;
      const text = method === "GET" ? "" : await request.clone().text();
      seen.push({ method, path, body: text ? JSON.parse(text) : null });
      if (path === "/api/v1/catalog") return json(CATALOG);
      if (path === "/api/v1/me/progression") return json(progression);
      if (path === "/api/v1/me/progression/events" && method === "POST") {
        if (postStatus !== 201) return json({ code: "progression_changed" }, postStatus);
        return json(post, 201);
      }
      if (path.startsWith("/api/v1/me/progression/events/") && method === "DELETE")
        return json(unset());
      if (path === "/api/v1/me/progression/hint-dismissals") return json(null, 204);
      if (path.endsWith("/practice-presets")) return json({ last: null, presets: [] });
      if (path.includes("/practices/1") && method === "PUT") {
        const body = JSON.parse(text) as Record<string, unknown>;
        return json({
          ...body,
          slot: 1,
          timezone: null,
          new_asana_hint: P("primary", "kurmasana"),
        });
      }
      return json({});
    }),
  );
  return seen;
}

function renderWith(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale="en">{node}</L10nProvider>
    </QueryClientProvider>,
  );
}

const posts = (seen: ReturnType<typeof stubApi>) =>
  seen.filter((r) => r.method === "POST" && r.path.endsWith("/events")).map((r) => r.body);

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

test("unset: the suggestion sets a start without celebrating", async () => {
  const seen = stubApi({
    progression: unset({
      suggested: P("primary", "kurmasana"),
      suggested_length: { series: ["primary"], end: "kurmasana", first_part: null },
    }),
    post: { progression: AT_NAVASANA, event: AT_NAVASANA.events[0], celebrations: [] },
  });
  renderWith(<Progression locale="en" onBack={vi.fn()} />);

  expect(await screen.findByText(/Set it once/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "From your log: Primary → Kurmasana" }));

  await waitFor(() => {
    expect(posts(seen)).toEqual([
      {
        kind: "set",
        series: "primary",
        last: "kurmasana",
        occurred_on: null,
        expected_event_id: null,
      },
    ]);
  });
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(haptics.notify).not.toHaveBeenCalledWith("success");
});

test("set: current line, next, items, history with Undo", async () => {
  stubApi();
  renderWith(<Progression locale="en" onBack={vi.fn()} />);

  expect(await screen.findByText("Your practice: Primary → Navasana")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "🎉 New asana: Bhujapidasana" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "🎉 Drop-backs" })).toBeInTheDocument();
  expect(screen.getByText("Started at Navasana")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "↩︎ Undo" })).toBeInTheDocument();
});

test("a new asana sends the expected id and shows the celebration card", async () => {
  const after = { ...AT_NAVASANA, position: P("primary", "bhujapidasana"), last_event_id: 8 };
  const seen = stubApi({
    post: {
      progression: after,
      event: { ...AT_NAVASANA.events[0], id: 8, kind: "given", to: P("primary", "bhujapidasana") },
      celebrations: [{ kind: "new_asana", series: "primary", key: "bhujapidasana", first: null }],
    },
  });
  renderWith(<Progression locale="en" onBack={vi.fn()} />);

  fireEvent.click(await screen.findByRole("button", { name: "🎉 New asana: Bhujapidasana" }));

  expect(await screen.findByRole("status")).toHaveTextContent(
    "🎉 New asana: Bhujapidasana. Enjoy it!",
  );
  expect(posts(seen)[0]).toMatchObject({
    kind: "given",
    last: "bhujapidasana",
    expected_event_id: 7,
  });
  expect(haptics.notify).toHaveBeenCalledWith("success");
});

test("series celebrations use the traditional name", async () => {
  stubApi({
    post: {
      progression: AT_NAVASANA,
      event: AT_NAVASANA.events[0],
      celebrations: [
        { kind: "new_asana", series: "intermediate", key: "pasasana", first: null },
        { kind: "series_begins", series: "intermediate", key: null, first: null },
      ],
    },
  });
  renderWith(<Progression locale="en" onBack={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "🎉 New asana: Bhujapidasana" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "🎉 Intermediate begins: Nadi Shodhana.",
  );
});

test("a 409 says it changed elsewhere and refetches", async () => {
  const seen = stubApi({ postStatus: 409 });
  renderWith(<Progression locale="en" onBack={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "🎉 New asana: Bhujapidasana" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("This changed on another device");
  await waitFor(() => {
    expect(seen.filter((r) => r.path === "/api/v1/me/progression").length).toBe(2);
  });
});

test("Undo deletes the newest event", async () => {
  const seen = stubApi();
  renderWith(<Progression locale="en" onBack={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "↩︎ Undo" }));
  await waitFor(() => {
    expect(seen.some((r) => r.method === "DELETE" && r.path.endsWith("/events/7"))).toBe(true);
  });
});

test("Change sets a corrected position without celebrating", async () => {
  const seen = stubApi({
    post: { progression: AT_NAVASANA, event: AT_NAVASANA.events[0], celebrations: [] },
  });
  renderWith(<Progression locale="en" onBack={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "✏️ Change" }));
  fireEvent.change(screen.getByLabelText("Last asana"), { target: { value: "kurmasana" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => {
    expect(posts(seen)[0]).toMatchObject({ kind: "set", series: "primary", last: "kurmasana" });
  });
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("PracticeDetails asks after a length past the last asana; Yes celebrates", async () => {
  const seen = stubApi({
    post: {
      progression: AT_NAVASANA,
      event: AT_NAVASANA.events[0],
      celebrations: [
        {
          kind: "new_asana",
          series: "primary",
          key: "kurmasana",
          first: { series: "primary", last: "bhujapidasana" },
        },
      ],
    },
  });
  renderWith(<PracticeDetails date={TODAY} practice={null} zone={null} locale="en" />);

  fireEvent.click(await screen.findByRole("button", { name: "🎯 Other…" }));
  fireEvent.change(screen.getByLabelText("Last asana"), { target: { value: "kurmasana" } });

  expect(
    await screen.findByText("Kurmasana goes beyond your last asana. New asana? 🎉"),
  ).toBeInTheDocument();
  const yes = screen.getByRole("button", { name: "🎉 Yes, new" });
  await waitFor(() => {
    expect(yes).toBeEnabled(); // waits for the progression read (expected id)
  });
  fireEvent.click(yes);

  expect(await screen.findByRole("status")).toHaveTextContent(
    "🎉 New asanas: Bhujapidasana → Kurmasana",
  );
  expect(posts(seen)[0]).toMatchObject({
    kind: "given",
    series: "primary",
    last: "kurmasana",
    occurred_on: TODAY,
    expected_event_id: 7,
  });
});

test("PracticeDetails: Not new posts the dismissal and hides the question", async () => {
  const seen = stubApi();
  renderWith(<PracticeDetails date={TODAY} practice={null} zone={null} locale="en" />);
  fireEvent.click(await screen.findByRole("button", { name: "🎯 Other…" }));
  fireEvent.change(screen.getByLabelText("Last asana"), { target: { value: "kurmasana" } });
  fireEvent.click(await screen.findByRole("button", { name: "Not new" }));

  expect(screen.queryByText(/goes beyond/)).not.toBeInTheDocument();
  await waitFor(() => {
    expect(seen.find((r) => r.path.endsWith("/hint-dismissals"))?.body).toEqual({
      series: "primary",
      last: "kurmasana",
    });
  });
});
