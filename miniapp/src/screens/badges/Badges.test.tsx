import { FluentBundle, FluentResource } from "@fluent/bundle";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { Badge, Catalog } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import enBadges from "../../locales/en/badges.ftl?raw";
import ruBadges from "../../locales/ru/badges.ftl?raw";
import BadgesScreen, { SEEN_KEY } from "./Badges";

// GM-02 (spec §6, §7, §9): two groups in server order; dates (UTC, never shifted by the device
// zone) or "from the record start"; tap shows the meaning; the New pill until seen on this
// device (storage failures tolerated); unknown keys skipped; the empty state; RU plurals;
// series names paired; stop names without the variant letter; the avoid-word grep; en/ru parity.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
}));

const CATALOG: Catalog = {
  version: "v1",
  check_in_tags: [],
  milestone_items: [
    { key: "drop-backs", latin: "Drop-backs", ru: "Дроп-бэки" },
    { key: "viparita-chakrasana", latin: "Viparita Chakrasana", ru: "Випарита Чакрасана" },
  ],
  series: [
    {
      slug: "primary",
      number: 1,
      name_en: "Primary series",
      name_ru: "Первая серия",
      halves_split: "navasana",
      traditional: { key: "primary", latin: "Yoga Chikitsa", ru: "Йога Чикитса" },
      stops: [{ key: "supta-kurmasana", latin: "Supta Kurmasana", ru: "Супта Курмасана" }],
    },
    {
      slug: "intermediate",
      number: 2,
      name_en: "Intermediate series",
      name_ru: "Вторая серия",
      halves_split: null,
      traditional: { key: "intermediate", latin: "Nadi Shodhana", ru: "Нади Шодхана" },
      stops: [{ key: "kapotasana-b", latin: "Kapotasana B", ru: "Капотасана B" }],
    },
  ],
};

function badge(over: Partial<Badge> & Pick<Badge, "key">): Badge {
  return {
    group: "practice",
    icon: "*",
    earned_on: "2026-03-01",
    at_record_start: false,
    count: null,
    days: null,
    before: null,
    series: null,
    stop: null,
    item: null,
    ...over,
  };
}

const ALL: Badge[] = [
  badge({ key: "ekam", icon: "🌅", earned_on: "2025-01-01", count: 1 }),
  badge({ key: "shatam", icon: "💯", earned_on: null, count: 100 }),
  badge({ key: "count-108", icon: "📿", count: 108 }),
  badge({ key: "sahasra", icon: "✨", count: 1000 }),
  badge({ key: "before-dawn", icon: "🌄", count: 10, before: "06:00" }),
  badge({ key: "from-the-future", icon: "?", count: 3 }), // an older app has no copy for it
  badge({
    key: "nadi-shodhana",
    group: "asanas",
    icon: "2️⃣",
    earned_on: "2024-05-01",
    at_record_start: true,
    series: "intermediate",
  }),
  badge({
    key: "kapotasana",
    group: "asanas",
    icon: "🕊",
    series: "intermediate",
    stop: "kapotasana-b",
  }),
  badge({ key: "tic-tacs", group: "asanas", icon: "🔄", item: "viparita-chakrasana" }),
];

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

function stubApi(badges: Badge[] = ALL, catalogStatus = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/catalog")
        return Promise.resolve(
          catalogStatus === 200
            ? json(CATALOG)
            : new Response(JSON.stringify({ code: null }), {
                status: catalogStatus,
                headers: { "Content-Type": "application/json" },
              }),
        );
      if (path === "/api/v1/me/badges") return Promise.resolve(json({ badges }));
      return Promise.resolve(json({}));
    }),
  );
}

function renderBadges(locale: Locale = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <BadgesScreen locale={locale} onBack={vi.fn()} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
const rows = (group: string) =>
  within(screen.getByRole("heading", { name: group }).closest("section") as HTMLElement)
    .getAllByRole("button")
    .map((b) => plain(b.textContent));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("Badges screen", () => {
  it("lists two groups in server order, skipping unknown keys", async () => {
    stubApi();
    renderBadges();
    await screen.findByRole("heading", { name: "Practice" });

    expect(rows("Practice")).toEqual([
      "🌅Ekam NewJan 1, 2025",
      "💯Shatam New",
      "📿108 NewMar 1, 2026",
      "✨Sahasra NewMar 1, 2026",
      "🌄Before dawn NewMar 1, 2026",
    ]);
    expect(rows("Asanas")).toEqual([
      "2️⃣Nadi Shodhana · Intermediate begins NewFrom the start of your log",
      "🕊Kapotasana NewMar 1, 2026",
      "🔄Viparita Chakrasana (tic-tacs) NewMar 1, 2026",
    ]);
    expect(screen.queryByText(/from-the-future/)).toBeNull();
    expect(screen.getByText("Badges are just for you; teachers don't see them.")).toBeVisible();
  });

  it("shows the meaning on tap, with the count and the threshold", async () => {
    stubApi();
    renderBadges();
    const dawn = await screen.findByRole("button", { name: /Before dawn/ });
    expect(dawn).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(dawn);

    expect(dawn).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("10 practices started before 06:00 local time.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Sahasra/ }));
    expect(screen.getByText("1,000 practices in your log.")).toBeVisible();
    expect(screen.queryByText(/before 06:00/)).toBeNull(); // one open at a time
    fireEvent.click(screen.getByRole("button", { name: /Kapotasana/ }));
    expect(screen.getByText(byPlain("Kapotasana became part of your practice."))).toBeVisible();
  });

  it("marks badges New until this device has shown them", async () => {
    localStorage.setItem(SEEN_KEY, JSON.stringify(["ekam"]));
    stubApi();
    const first = renderBadges();
    await screen.findByRole("heading", { name: "Practice" });
    expect(screen.getByRole("button", { name: /Ekam/ })).not.toHaveTextContent("New");
    expect(screen.getByRole("button", { name: /Shatam/ })).toHaveTextContent("New");
    first.unmount();

    renderBadges();
    await screen.findByRole("heading", { name: "Practice" });
    expect(screen.queryByText("New")).toBeNull();
    expect(JSON.parse(localStorage.getItem(SEEN_KEY) ?? "[]")).toContain("tic-tacs");
  });

  it("still works when storage is blocked", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    stubApi();
    renderBadges();
    expect(await screen.findByRole("button", { name: /Ekam/ })).toHaveTextContent("New");
  });

  it("says so when the catalog can't load, instead of spinning", async () => {
    stubApi(ALL, 503);
    renderBadges();
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load your badges.");
  });

  it("shows the empty state", async () => {
    stubApi([]);
    renderBadges();
    expect(
      await screen.findByText("Badges appear here by themselves as you log your practice."),
    ).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Practice" })).toBeNull();
  });

  it("reads in Russian, names paired and the variant letter dropped", async () => {
    stubApi();
    renderBadges("ru");
    await screen.findByRole("heading", { name: "Практика" });

    expect(rows("Асаны")).toEqual([
      "2️⃣Нади Шодхана · начало Второй серии НовоеС начала журнала",
      "🕊Капотасана Новое1 мар. 2026 г.",
      "🔄Випарита Чакрасана (тик-токи) Новое1 мар. 2026 г.",
    ]);
    fireEvent.click(screen.getByRole("button", { name: /Капотасана/ }));
    expect(screen.getByText(byPlain("Капотасана вошла в твою практику."))).toBeVisible();
  });
});

function byPlain(text: string) {
  return (_: string, el: Element | null) => el?.tagName === "P" && plain(el.textContent) === text;
}

// --- copy ------------------------------------------------------------------------------------

const SOURCES: Record<Locale, string> = { en: enBadges, ru: ruBadges };

function bundle(locale: Locale): FluentBundle {
  const b = new FluentBundle(locale);
  expect(b.addResource(new FluentResource(SOURCES[locale]))).toEqual([]);
  return b;
}

function shape(locale: Locale): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const m of new FluentResource(SOURCES[locale]).body) {
    out[m.id] = Object.keys((m as { attributes?: Record<string, unknown> }).attributes ?? {});
  }
  return out;
}

function say(locale: Locale, id: string, attr: "value" | "about", count = 10): string {
  const b = bundle(locale);
  const message = b.getMessage(id);
  const pattern = attr === "value" ? message?.value : message?.attributes.about;
  if (!pattern) throw new Error(`missing ${id}.${attr}`);
  const errors: Error[] = [];
  const text = b.formatPattern(
    pattern,
    { count, before: "06:00", asana: "Капотасана", item: "Drop-backs" },
    errors,
  );
  expect(errors).toEqual([]);
  return plain(text);
}

// The GM-01 and PR-08 lists (minus "badge" / «значок») plus the badge words (spec §7).
const AVOID: Record<Locale, string[]> = {
  en: [
    "unlock", "level", "achieve", "earn", "finally", "behind", "lost", "regress", "back to",
    "demote", "only", "again", "streak", "rank", "goal", "should", "faster", "record", "best",
    "total", "in a row", "left", "until", "year", "daily", "every day", "keep", "collect all",
    "next", "gate", "mastered", "got ", "reached",
  ],
  ru: [
    "уровень", "достижен", "разблок", "наконец", "откат", "потер", "отстал", "только", "опять",
    "цель", "надо", "должен", "рекорд", "лучш", "подряд", "осталось", "до цели", "год",
    "ежедневн", "каждый день", "продолжай", "так держать", "заработ", "следующ", "освоил",
  ],
}; // prettier-ignore

describe("badges.ftl", () => {
  it("has the same messages, attributes and variables in en and ru", () => {
    expect(shape("ru")).toEqual(shape("en"));
    expect(Object.keys(shape("en"))).toContain("badge-mandala");
    // Every `id =` line parsed (Fluent drops junk silently).
    for (const locale of ["en", "ru"] as const) {
      const ids = [...SOURCES[locale].matchAll(/^[a-z][a-z0-9-]*\s*=/gm)].length;
      expect(Object.keys(shape(locale))).toHaveLength(ids);
    }
  });

  it.each([
    [1, "1 практика в журнале."],
    [2, "2 практики в журнале."],
    [5, "5 практик в журнале."],
    [21, "21 практика в журнале."],
    [40, "40 практик в журнале."],
    [108, "108 практик в журнале."],
    [1000, "1 000 практик в журнале."],
  ])("RU plural %i", (count, expected) => {
    expect(say("ru", "badge-count-108", "about", count).replace(/\s/g, " ")).toBe(expected);
  });

  it("pairs the traditional series names with the plain ones", () => {
    expect(say("en", "badge-yoga-chikitsa", "value")).toBe(
      "Yoga Chikitsa · the full Primary series",
    );
    expect(say("ru", "badge-nadi-shodhana", "value")).toBe("Нади Шодхана · начало Второй серии");
  });

  it.each(["en", "ru"] as const)("%s: never a score, a loss or a 🌸", (locale) => {
    const b = bundle(locale);
    const lines: string[] = [];
    for (const m of new FluentResource(SOURCES[locale]).body) {
      if (m.id.startsWith("-")) continue;
      for (const count of [1, 2, 5, 40, 108, 1000]) {
        lines.push(say(locale, m.id, "value", count).toLowerCase());
        if (b.getMessage(m.id)?.attributes.about) {
          lines.push(say(locale, m.id, "about", count).toLowerCase());
        }
      }
    }
    expect(lines.length).toBeGreaterThan(100);
    for (const word of [...AVOID[locale], "🌸", "ladies", "женск"]) {
      expect(lines.filter((l) => l.includes(word))).toEqual([]);
    }
  });

  it("has no gendered past tense about the person in Russian", () => {
    expect(ruBadges).not.toMatch(/\bты\s+\S+л[аи]?\b/i);
    expect(ruBadges).not.toContain("(а)");
  });
});
