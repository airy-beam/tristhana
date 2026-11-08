import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type {
  Catalog,
  ProgressionEvent,
  ProgressionPosition,
  Progression as ProgressionValue,
} from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import Progression from "./Progression";

// PR-08 Phase 3 (spec §5, §7, ADR-0037): "🧘 My asanas" after a teacher's mark. A teacher's
// history entry ends "· Anna" while linked, "· a teacher" after; the current line gets "Marked
// by …" from `marked`; Undo sits on every `undoable` entry (a teacher's mark after later items
// too) and on nothing else; a 409 `not_latest` refetches and says the practice has moved on;
// an older payload (no `by` / `undoable` / `marked`) still renders.
//
// Types come from the generated client (`npm run gen:api`); only the older-payload test casts,
// to drop the new fields.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
}));

const TODAY = "2026-11-08";

const CATALOG: Catalog = {
  version: "v1",
  check_in_tags: [],
  milestone_items: [
    { key: "drop-backs", latin: "Drop-backs", ru: "Дроп-бэки" },
    { key: "standing-up", latin: "Standing up", ru: "Вставание из моста" },
  ],
  series: [
    {
      slug: "intermediate",
      number: 2,
      name_en: "Intermediate series",
      name_ru: "Вторая серия",
      halves_split: null,
      traditional: { key: "intermediate", latin: "Nadi Shodhana", ru: "Нади Шодхана" },
      stops: [
        { key: "kapotasana-b", latin: "Kapotasana B", ru: "Капотасана B" },
        { key: "supta-vajrasana", latin: "Supta Vajrasana", ru: "Супта Ваджрасана" },
        { key: "bakasana-b", latin: "Bakasana B", ru: "Бакасана B" },
        { key: "bharadvajasana", latin: "Bharadvajasana", ru: "Бхарадваджасана" },
      ],
    },
  ],
};

const P = (series: string | null, last: string | null): ProgressionPosition => ({ series, last });

function event(
  id: number,
  kind: "start" | "given" | "changed" | "item_given",
  over: Partial<Pick<ProgressionEvent, "by" | "by_name" | "undoable" | "to" | "item">> = {},
): ProgressionEvent {
  const by = over.by ?? "self";
  return {
    id,
    kind,
    occurred_on: "2026-11-0" + String(id % 9 || 1),
    from: kind === "start" || kind === "item_given" ? null : P("intermediate", "kapotasana-b"),
    to: kind === "item_given" ? null : (over.to ?? P("intermediate", "bharadvajasana")),
    item: over.item ?? (kind === "item_given" ? "standing-up" : null),
    marked_by_self: by === "self",
    by,
    by_name: over.by_name ?? null,
    undoable: over.undoable ?? false,
  };
}

/** A teacher (Anna) marked three stops at once; the student then ticked standing up. */
function marked(over: Partial<ProgressionValue> = {}): ProgressionValue {
  return {
    set: true,
    position: P("intermediate", "bharadvajasana"),
    length: { series: ["intermediate"], end: "bharadvajasana", first_part: null },
    by_series: [],
    items: ["drop-backs", "standing-up"],
    next: P("intermediate", "ardha-matsyendrasana"),
    later: [],
    suggested: null,
    suggested_length: null,
    events: [
      event(9, "item_given", { undoable: true }),
      event(8, "given", { by: "teacher", by_name: "Anna", undoable: true }),
      event(7, "item_given", { item: "drop-backs" }),
      event(6, "start", { to: P("intermediate", "kapotasana-b") }),
    ],
    last_event_id: 9,
    today: TODAY,
    marked: { event_id: 8, by_name: "Anna", undoable: true },
    ...over,
  };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Stub {
  /** What each GET returns, in turn (the last one repeats). */
  reads?: ProgressionValue[];
  deleteStatus?: number;
}

function stubApi({ reads = [marked()], deleteStatus = 200 }: Stub = {}) {
  const seen: { method: string; path: string }[] = [];
  let n = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      const path = new URL(request.url).pathname;
      seen.push({ method: request.method, path });
      if (path === "/api/v1/catalog") return json(CATALOG);
      if (path === "/api/v1/me/progression") {
        const found = reads[Math.min(n, reads.length - 1)];
        n += 1;
        return json(found);
      }
      if (path.startsWith("/api/v1/me/progression/events/") && request.method === "DELETE") {
        if (deleteStatus !== 200) return json({ code: "not_latest" }, deleteStatus);
        return json(marked({ events: [], marked: null }));
      }
      return json({});
    }),
  );
  return seen;
}

function renderIt(locale: "en" | "ru" = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <Progression locale={locale} onBack={vi.fn()} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
const entries = () => screen.getAllByRole("listitem").map((li) => plain(li.textContent));
const UNDO = /^↩︎ Undo: /; // each Undo's label names its entry
const undos = () => screen.queryAllByRole("button", { name: UNDO });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

test("a teacher's entry ends with their name while linked", async () => {
  stubApi();
  renderIt();

  await screen.findByText("Your practice: Intermediate → Bharadvajasana");

  const teacher = entries().find((t) => t.includes("Bharadvajasana"));
  expect(teacher).toMatch(/· Anna/);
  expect(entries().filter((t) => t.includes("·"))).toHaveLength(1); // own entries carry no name
});

test("after an unlink or a deletion it reads a teacher", async () => {
  stubApi({
    reads: [
      marked({
        events: [
          event(8, "given", { by: "teacher", by_name: null, undoable: true }),
          event(6, "start", { to: P("intermediate", "kapotasana-b") }),
        ],
        marked: { event_id: 8, by_name: null, undoable: true },
      }),
    ],
  });
  renderIt();

  await screen.findByText("Your practice: Intermediate → Bharadvajasana");

  expect(entries()[0]).toMatch(/· a teacher/);
  expect(document.body.textContent).toContain("Marked by a teacher");
});

test("the current line says who marked it", async () => {
  stubApi();
  renderIt();

  await screen.findByText("Your practice: Intermediate → Bharadvajasana");

  expect(plain(document.body.textContent)).toContain("Marked by Anna");
});

test("Russian: the name and the fallback", async () => {
  stubApi({
    reads: [
      marked({
        events: [event(8, "given", { by: "teacher", by_name: null, undoable: true })],
        marked: { event_id: 8, by_name: null, undoable: true },
      }),
    ],
  });
  renderIt("ru");

  await waitFor(() => {
    expect(plain(document.body.textContent)).toContain("Отметка: учитель");
  });
  expect(entries()[0]).toMatch(/· учитель/);
});

test("Undo sits on every undoable entry, the teacher's mark included", async () => {
  stubApi();
  renderIt();

  await screen.findByText("Your practice: Intermediate → Bharadvajasana");

  expect(undos()).toHaveLength(2);
});

test("Undo on the teacher's (non-newest) entry deletes that event", async () => {
  const seen = stubApi();
  renderIt();
  await screen.findByText("Your practice: Intermediate → Bharadvajasana");
  const teacherEntry = screen
    .getAllByRole("listitem")
    .find((li) => plain(li.textContent).includes("· Anna"));
  expect(teacherEntry).toBeDefined();

  const undo =
    (teacherEntry && within(teacherEntry).queryByRole("button", { name: UNDO })) ?? undos()[1];
  expect(undo).toBeDefined();
  fireEvent.click(undo as HTMLElement);

  await waitFor(() => {
    expect(
      seen.some((r) => r.method === "DELETE" && r.path === "/api/v1/me/progression/events/8"),
    ).toBe(true);
  });
});

test("each Undo's label names the entry it undoes", async () => {
  stubApi();
  renderIt();

  await screen.findByText("Your practice: Intermediate → Bharadvajasana");

  const names = undos().map((b) => plain(b.getAttribute("aria-label")));
  expect(names).toHaveLength(2);
  expect(names[0]).toMatch(/^↩︎ Undo: .+: 🎉 Standing up/);
  expect(names[1]).toMatch(/^↩︎ Undo: .+: 🎉 Bharadvajasana · Anna$/);
  expect(undos().every((b) => plain(b.textContent) === "↩︎ Undo")).toBe(true);
});

test("no Undo on a mark the practice has moved on from", async () => {
  stubApi({
    reads: [
      marked({
        position: P("intermediate", "ardha-matsyendrasana"),
        events: [
          event(10, "given", { undoable: true, to: P("intermediate", "ardha-matsyendrasana") }),
          event(8, "given", { by: "teacher", by_name: "Anna", undoable: false }),
        ],
        marked: null,
      }),
    ],
  });
  renderIt();

  await screen.findByText(/Your practice:/);

  expect(undos()).toHaveLength(1);
  expect(plain(document.body.textContent)).not.toContain("Marked by");
  expect(entries()[1]).toMatch(/· Anna/); // the history still says who
});

test("a 409 not_latest refetches and says the practice has moved on", async () => {
  const moved = marked({
    events: [event(10, "changed", { undoable: true }), event(8, "given", { by: "teacher" })],
    marked: null,
  });
  const seen = stubApi({ reads: [marked(), moved], deleteStatus: 409 });
  renderIt();
  await screen.findByText("Your practice: Intermediate → Bharadvajasana");

  fireEvent.click(undos()[1] as HTMLElement);

  expect(
    await screen.findByText(
      "Your practice has changed since this mark, so nothing was undone. To set where it ends now, use ✏️ Change.",
    ),
  ).toBeInTheDocument();
  await waitFor(() => {
    expect(seen.filter((r) => r.path === "/api/v1/me/progression").length).toBe(2);
  });
});

test("an older payload without by, undoable or marked still renders", async () => {
  const old = marked();
  const bare = old as unknown as Record<string, unknown>;
  delete bare.marked;
  bare.events = old.events.map((e) => {
    const rest: Partial<ProgressionEvent> = { ...e };
    delete rest.by;
    delete rest.by_name;
    delete rest.undoable;
    return rest;
  });
  stubApi({ reads: [bare as unknown as ProgressionValue] });
  renderIt();

  await screen.findByText("Your practice: Intermediate → Bharadvajasana");

  expect(entries()).toHaveLength(4);
  expect(undos().length).toBeGreaterThanOrEqual(1); // the newest, as before
  expect(plain(document.body.textContent)).not.toContain("Marked by");
});
