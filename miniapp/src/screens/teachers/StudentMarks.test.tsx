import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type { ProgressionPosition, StudentCard } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import { haptics } from "../../telegram";
import Students from "./Students";

// PR-08 Phase 3 (spec §5, §7): on the student card, "🎉 Mark new asana" opens an inline list of
// `next_asanas` (one stop, or a range from the first new stop), a pick asks once through the
// native confirm (`confirmAction`, not destructive), the POST sends `{from: last_asana, to}`,
// the response replaces the card (not optimistic) with a status line and a light haptic; 409
// refetches with the stale line, 404 goes back to the list; an unset card has a neutral line
// and no button; an older payload without `next_asanas` renders without one.
//
// Types come from the generated client (`npm run gen:api`); `Card` only lets a test drop
// `next_asanas` to stand for an older payload.

const telegram = vi.hoisted(() => ({
  confirmAction: vi.fn<(message: string, ok: string, cancel: string) => Promise<boolean>>(),
  confirmDestructive: vi.fn<(message: string, ok: string, cancel: string) => Promise<boolean>>(),
}));
const { confirmAction } = telegram;

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  confirmAction: telegram.confirmAction,
  confirmDestructive: telegram.confirmDestructive,
}));

const TODAY = "2026-11-08";
const ANNA = "00000000-0000-0000-0000-0000000000a1";
const CARD_PATH = `/api/v1/me/students/${ANNA}`;
const MARK_PATH = `${CARD_PATH}/new-asana`;
const CATALOG = {
  version: "v1",
  check_in_tags: [],
  milestone_items: [],
  series: [
    {
      slug: "primary",
      number: 1,
      name_en: "Primary series",
      name_ru: "Первая серия",
      halves_split: "navasana",
      stops: [
        {
          key: "urdhva-mukha-paschimottanasana",
          latin: "Urdhva Mukha Paschimottanasana",
          ru: "Урдхва Мукха Пасчимоттанасана",
        },
        { key: "setu-bandhasana", latin: "Setu Bandhasana", ru: "Сету Бандхасана" },
      ],
    },
    {
      slug: "intermediate",
      number: 2,
      name_en: "Intermediate series",
      name_ru: "Вторая серия",
      halves_split: null,
      stops: [
        { key: "pasasana", latin: "Pasasana", ru: "Пашасана" },
        { key: "krounchasana", latin: "Krounchasana", ru: "Краунчасана" },
        { key: "kapotasana-b", latin: "Kapotasana B", ru: "Капотасана B" },
        { key: "supta-vajrasana", latin: "Supta Vajrasana", ru: "Супта Ваджрасана" },
        { key: "bakasana-b", latin: "Bakasana B", ru: "Бакасана B" },
        { key: "bharadvajasana", latin: "Bharadvajasana", ru: "Бхарадваджасана" },
      ],
    },
  ],
};

const P = (series: string | null, last: string | null): ProgressionPosition => ({ series, last });
const KAPOTASANA_B = P("intermediate", "kapotasana-b");
const SUPTA_VAJRASANA = P("intermediate", "supta-vajrasana");
const BAKASANA_B = P("intermediate", "bakasana-b");
const BHARADVAJASANA = P("intermediate", "bharadvajasana");

type Card = Omit<StudentCard, "next_asanas"> & Partial<Pick<StudentCard, "next_asanas">>;

function week(): Card["days"] {
  const end = Date.parse(`${TODAY}T00:00:00Z`);
  return [6, 5, 4, 3, 2, 1, 0].map((back) => ({
    date: new Date(end - back * 86_400_000).toISOString().slice(0, 10),
    state: null,
    length: null,
  }));
}

const card = (over: Partial<Card> = {}): Card => ({
  id: ANNA,
  name: "Anna",
  days: week(),
  last_asana: KAPOTASANA_B,
  next_asanas: [SUPTA_VAJRASANA, BAKASANA_B, BHARADVAJASANA],
  quiet: false,
  ...over,
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Seen {
  method: string;
  path: string;
  body: unknown;
}

interface Stub {
  /** The card each GET returns, in turn (the last one repeats). */
  cards?: Card[];
  /** How the POST answers: a card, or an error status with its code. */
  post?: Card | { status: number; code: string };
}

function stubApi({ cards = [card()], post }: Stub = {}) {
  const seen: Seen[] = [];
  let reads = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname;
      const method = request.method;
      const text = method === "GET" ? "" : await request.clone().text();
      seen.push({ method, path, body: text ? JSON.parse(text) : null });
      if (path === "/api/v1/catalog") return json(CATALOG);
      if (path === "/api/v1/me/students") {
        return json({ students: [{ id: ANNA, name: "Anna", today: null }], total: 1 });
      }
      if (path === CARD_PATH && method === "GET") {
        const found = cards[Math.min(reads, cards.length - 1)];
        reads += 1;
        return json(found);
      }
      if (path === MARK_PATH && method === "POST") {
        if (post && "status" in post) return json({ code: post.code }, post.status);
        return json(post ?? card());
      }
      return json({});
    }),
  );
  return seen;
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
const pageText = () => plain(document.body.textContent);
const posts = (seen: Seen[]) => seen.filter((r) => r.method === "POST" && r.path === MARK_PATH);
const cardReads = (seen: Seen[]) =>
  seen.filter((r) => r.method === "GET" && r.path === CARD_PATH).length;

function renderStudents(locale: "en" | "ru" = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <Students locale={locale} onBack={vi.fn()} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

async function openCard(locale: "en" | "ru" = "en") {
  renderStudents(locale);
  fireEvent.click(await screen.findByRole("button", { name: /Anna/ }));
  await screen.findByText(locale === "en" ? "Last 7 days" : "Последние 7 дней");
}

const markButton = (locale: "en" | "ru" = "en") =>
  screen.findByRole("button", {
    name: locale === "en" ? "🎉 Mark new asana" : "🎉 Отметить новую асану",
  });

async function openPicker(locale: "en" | "ru" = "en") {
  await openCard(locale);
  fireEvent.click(await markButton(locale));
}

beforeEach(() => {
  confirmAction.mockReset();
  confirmAction.mockResolvedValue(true);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("the pick list", () => {
  test("lists next_asanas in order; a range button names only its last stop", async () => {
    stubApi();

    await openPicker();

    expect(screen.getByRole("button", { name: "Supta Vajrasana" })).toBeInTheDocument();
    const picks = ["Supta Vajrasana", "→ Bakasana B", "→ Bharadvajasana"];
    const found = picks.map((name) => screen.getByRole("button", { name }));
    const order = found.map((b) => pageText().indexOf(plain(b.textContent)));
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  test("reads in Russian with the catalog's Cyrillic names", async () => {
    stubApi();

    await openPicker("ru");

    expect(screen.getByRole("button", { name: "→ Бхарадваджасана" })).toBeInTheDocument();
  });

  test("an unset card has the neutral line and no button", async () => {
    stubApi({ cards: [card({ last_asana: null, next_asanas: [] })] });

    await openCard();

    expect(pageText()).toContain(
      "No last asana set yet. Once they set it in My asanas, you can mark new ones here.",
    );
    expect(screen.queryByRole("button", { name: "🎉 Mark new asana" })).toBeNull();
  });

  test("at the end of the confirmed series there is no button", async () => {
    stubApi({ cards: [card({ next_asanas: [] })] });

    await openCard();

    expect(screen.queryByRole("button", { name: "🎉 Mark new asana" })).toBeNull();
    expect(pageText()).not.toContain("hasn't set");
  });

  test("an older payload without next_asanas renders without the button", async () => {
    const old = card();
    delete old.next_asanas;
    stubApi({ cards: [old] });

    await openCard();

    expect(pageText()).toContain("Last asana, as marked in their log: Kapotasana B");
    expect(screen.queryByRole("button", { name: "🎉 Mark new asana" })).toBeNull();
  });
});

describe("confirm and mark", () => {
  test("a pick asks once, naming the student and the asana", async () => {
    stubApi();
    await openPicker();

    fireEvent.click(screen.getByRole("button", { name: "Supta Vajrasana" }));

    await waitFor(() => {
      expect(confirmAction).toHaveBeenCalledTimes(1);
    });
    const [message, ok] = confirmAction.mock.calls[0] ?? [];
    expect(plain(message)).toBe(
      "Anna: the next asana is Supta Vajrasana (Intermediate). Mark it as new? Anna gets a message from the bot and can undo it.",
    );
    expect(plain(ok)).toBe("🎉 Yes, mark");
    expect(telegram.confirmDestructive).not.toHaveBeenCalled();
  });

  test("a range asks with the range copy", async () => {
    stubApi();
    await openPicker();

    fireEvent.click(screen.getByRole("button", { name: "→ Bharadvajasana" }));

    await waitFor(() => {
      expect(confirmAction).toHaveBeenCalledTimes(1);
    });
    expect(plain(confirmAction.mock.calls[0]?.[0])).toBe(
      "Anna: new asanas Supta Vajrasana → Bharadvajasana (Intermediate). Mark them? Anna gets one message from the bot and can undo it.",
    );
  });

  test("cancel posts nothing", async () => {
    confirmAction.mockResolvedValue(false);
    const seen = stubApi();
    await openPicker();

    fireEvent.click(screen.getByRole("button", { name: "Supta Vajrasana" }));

    await waitFor(() => {
      expect(confirmAction).toHaveBeenCalled();
    });
    await Promise.resolve();
    expect(posts(seen)).toEqual([]);
  });

  test("confirm posts {from: last_asana, to} and the response replaces the card", async () => {
    const after = card({
      last_asana: BHARADVAJASANA,
      next_asanas: [P("intermediate", "ardha-matsyendrasana")],
    });
    const seen = stubApi({ post: after });
    await openPicker();

    fireEvent.click(screen.getByRole("button", { name: "→ Bharadvajasana" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "✅ Marked: Supta Vajrasana → Bharadvajasana.",
    );
    expect(posts(seen).map((r) => r.body)).toEqual([{ from: KAPOTASANA_B, to: BHARADVAJASANA }]);
    expect(pageText()).toContain("Last asana, as marked in their log: Bharadvajasana");
    expect(cardReads(seen)).toBe(1); // the POST's card, no refetch
    expect(haptics.impact).toHaveBeenCalledWith("light");
  });

  test("one stop says so in the status line", async () => {
    stubApi({ post: card({ last_asana: SUPTA_VAJRASANA }) });
    await openPicker();

    fireEvent.click(screen.getByRole("button", { name: "Supta Vajrasana" }));

    expect(await screen.findByRole("status")).toHaveTextContent("✅ Marked: Supta Vajrasana.");
  });

  test("not optimistic: the card keeps its old line until the response", async () => {
    let release: (r: Response) => void = () => undefined;
    stubApi();
    const original = globalThis.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) =>
        request.method === "POST"
          ? new Promise<Response>((r) => {
              release = r;
            })
          : original(request),
      ),
    );
    await openPicker();

    fireEvent.click(screen.getByRole("button", { name: "Supta Vajrasana" }));

    await waitFor(() => {
      expect(confirmAction).toHaveBeenCalled();
    });
    expect(pageText()).toContain("Last asana, as marked in their log: Kapotasana B");
    release(json(card({ last_asana: SUPTA_VAJRASANA })));
    await screen.findByRole("status");
  });

  test("a 409 refetches the card and shows the stale line", async () => {
    const moved = card({ last_asana: BAKASANA_B, next_asanas: [BHARADVAJASANA] });
    const seen = stubApi({
      cards: [card(), moved],
      post: { status: 409, code: "progression_changed" },
    });
    await openPicker();

    fireEvent.click(screen.getByRole("button", { name: "Supta Vajrasana" }));

    expect(
      await screen.findByText("This card was out of date, so nothing was marked. Here it is now."),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(cardReads(seen)).toBe(2);
    });
    expect(
      await screen.findByText(/Last asana, as marked in their log: Bakasana B/),
    ).toBeInTheDocument();
    expect(pageText()).not.toContain("✅ Marked");
  });

  test("a range across a series boundary names both series", async () => {
    const UMP = P("primary", "urdhva-mukha-paschimottanasana");
    const SETU = P("primary", "setu-bandhasana");
    const KROUNCHASANA = P("intermediate", "krounchasana");
    stubApi({
      cards: [
        card({ last_asana: UMP, next_asanas: [SETU, P("intermediate", "pasasana"), KROUNCHASANA] }),
      ],
    });
    await openPicker();

    fireEvent.click(screen.getByRole("button", { name: "→ Krounchasana" }));

    await waitFor(() => {
      expect(confirmAction).toHaveBeenCalledTimes(1);
    });
    expect(plain(confirmAction.mock.calls[0]?.[0])).toBe(
      "Anna: new asanas Setu Bandhasana (Primary) → Krounchasana (Intermediate). Mark them? Anna gets one message from the bot and can undo it.",
    );
  });

  test("a failure other than 409 says so, without the stale line or a refetch", async () => {
    const seen = stubApi({ post: { status: 503, code: "unavailable" } });
    await openPicker();

    fireEvent.click(screen.getByRole("button", { name: "Supta Vajrasana" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't save. Please try once more.",
    );
    expect(pageText()).not.toContain("out of date");
    expect(cardReads(seen)).toBe(1);
    expect(screen.getByRole("button", { name: "Supta Vajrasana" })).toBeInTheDocument(); // retry
  });

  test("a 404 goes back to the list", async () => {
    stubApi({ post: { status: 404, code: "not_linked" } });
    await openPicker();

    fireEvent.click(screen.getByRole("button", { name: "Supta Vajrasana" }));

    await waitFor(() => {
      expect(screen.queryByText("Last 7 days")).toBeNull();
    });
    expect(await screen.findByRole("button", { name: /Anna/ })).toBeInTheDocument();
  });

  test("the card never shows a celebration, events or who marked before", async () => {
    stubApi({ post: card({ last_asana: SUPTA_VAJRASANA }) });
    await openPicker();

    fireEvent.click(screen.getByRole("button", { name: "Supta Vajrasana" }));

    const status = await screen.findByRole("status");
    expect(within(status).queryByText(/🎉|Enjoy|Undo/)).toBeNull();
    expect(pageText()).not.toMatch(/Marked by|Undo/);
  });
});
