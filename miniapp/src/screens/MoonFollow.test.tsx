import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { Me } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import type { Locale } from "../i18n/negotiate";
import { MoonCard } from "./MoonCard";
import Links from "./settings/Links";
import Settings from "./settings/Settings";

// MD-02 (spec §2, §4, §7): "👥 Follow my teacher" as the first option of the moon city select,
// only with a main teacher, sending `{slug: null}`; the source line on the card and in
// Settings; the teacher's shared line; Make main and Remove refetch the moon days, days and
// stats. The API and the Telegram SDK are mocked.

const telegram = vi.hoisted(() => ({
  confirmDestructive: vi.fn<(message: string, ok: string, cancel: string) => Promise<boolean>>(),
}));

vi.mock("../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  confirmDestructive: telegram.confirmDestructive,
  openTelegramLink: vi.fn(),
}));

const ME: Me = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Ash",
  locale: "en",
  timezone: "Asia/Almaty",
  name_from_telegram: true,
  locale_from_telegram: true,
  hide_ladies: false,
  offer_check_in: true,
  home_city_chosen: true,
};
const ANNA = "00000000-0000-0000-0000-0000000000a1";
const BORIS = "00000000-0000-0000-0000-0000000000a2";
const TODAY = "2026-11-07";
const CITIES = [
  { slug: "mysuru", name_en: "Mysuru", name_ru: "Майсур", timezone: "Asia/Kolkata" },
  { slug: "almaty", name_en: "Almaty", name_ru: "Алматы", timezone: "Asia/Almaty" },
  { slug: "moscow", name_en: "Moscow", name_ru: "Москва", timezone: "Europe/Moscow" },
];

interface Location {
  slug: string;
  explicit: boolean;
  source: "chosen" | "teacher" | "shala" | "default";
  follow_chosen: boolean;
  teacher: { id: string; name: string | null } | null;
  shared: { chosen: boolean } | null;
  shala?: { id: string; name: string; staff: boolean } | null;
}

const location = (over: Partial<Location> = {}): Location => ({
  slug: "mysuru",
  explicit: false,
  source: "default",
  follow_chosen: false,
  teacher: null,
  shared: null,
  ...over,
});
const FOLLOWING = location({
  slug: "almaty",
  source: "teacher",
  teacher: { id: ANNA, name: "Anna" },
});

const teacher = (id: string, name: string, primary: boolean) => ({
  id,
  name,
  primary,
  primary_chosen: false,
  linked_at: "2026-11-01T06:00:00Z",
});
const WITH_ANNA = { teachers: [teacher(ANNA, "Anna", true)], students: [] };
const NO_TEACHERS = { teachers: [], students: [] };

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubApi(loc: Location, links: unknown = WITH_ANNA): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      await Promise.resolve(); // a round trip
      seen.push(request);
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/me/moon-location") return json(FOLLOWING);
      if (path === "/api/v1/me/moon-days") return json({ location: loc, today: TODAY, days: [] });
      if (path === "/api/v1/moon/cities") return json(CITIES);
      if (path === "/api/v1/me/links") return json(links);
      if (path === "/api/v1/me/shalas") return json([]); // SC-01
      if (path.startsWith("/api/v1/me/teachers/") && request.method === "PUT") return json(links);
      if (path.startsWith("/api/v1/me/teachers/") && request.method === "DELETE")
        return new Response(null, { status: 204 });
      if (path === "/api/v1/me/notification-settings")
        return json({
          moon: { offsets: [1, 7], at: "19:00:00" },
          quiet: { start: "22:00:00", end: "07:00:00" },
          daily_cap: 3,
          practice: { on: null, at: "10:00:00", days: [1, 2, 3, 4, 5, 7] },
          timezone: "Asia/Almaty",
        });
      if (path === "/api/v1/me") return json({ ...ME, day_off: [6] });
      return json({});
    }),
  );
  return seen;
}

function renderWith(node: React.ReactNode, locale: Locale = "en", client?: QueryClient) {
  const queries = client ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <L10nProvider locale={locale}>{node}</L10nProvider>
    </QueryClientProvider>,
  );
}

const plain = (text: string) => text.replace(/[\u2068\u2069]/g, "");
/** The one element that holds exactly `text` (not its ancestors, not an <option>). */
const exact = (text: string) => (_: string, el: Element | null) =>
  !!el && el.childElementCount === 0 && el.tagName !== "OPTION" && plain(el.textContent) === text;
const settings = (locale: Locale = "en") => (
  <Settings me={{ ...ME, locale }} onBack={vi.fn()} onTour={vi.fn()} onLinks={vi.fn()} />
);

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

async function citySelect(): Promise<HTMLSelectElement> {
  return screen.findByRole<HTMLSelectElement>("combobox", { name: "City for the calendar" });
}

const optionTexts = (select: HTMLSelectElement) =>
  Array.from(select.options).map((o) => plain(o.textContent));

describe("Follow my teacher in Settings", () => {
  it("is the first option with a main teacher", async () => {
    stubApi(location({ slug: "moscow", source: "chosen", explicit: true }));
    renderWith(settings());
    const select = await citySelect();

    await waitFor(() => {
      expect(optionTexts(select)[0]).toBe("👥 Follow my teacher (Anna)");
    });
    expect(select.value).toBe("moscow"); // a chosen city stays selected
  });

  it("is absent without a teacher", async () => {
    stubApi(location(), NO_TEACHERS);
    renderWith(settings());
    const select = await citySelect();

    await waitFor(() => {
      expect(optionTexts(select)).toContain("Almaty");
    });
    expect(optionTexts(select).some((t) => t.includes("Follow my teacher"))).toBe(false);
  });

  it("sends null when chosen", async () => {
    const seen = stubApi(location({ slug: "moscow", source: "chosen", explicit: true }));
    renderWith(settings());
    const select = await citySelect();
    await waitFor(() => {
      expect(optionTexts(select)[0]).toMatch(/Follow my teacher/);
    });

    fireEvent.change(select, { target: { value: select.options[0]?.value } });

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PUT")).toBe(true);
    });
    const put = seen.find((r) => r.method === "PUT");
    expect(new URL(put?.url ?? "").pathname).toBe("/api/v1/me/moon-location");
    expect(await put?.json()).toEqual({ slug: null });
  });

  it("is the selected option while following", async () => {
    stubApi(FOLLOWING);
    renderWith(settings());
    const select = await citySelect();

    await waitFor(() => {
      expect(optionTexts(select)[0]).toMatch(/Follow my teacher/);
    });
    expect(select.value).toBe(select.options[0]?.value);
  });

  it("is in Russian too", async () => {
    stubApi(FOLLOWING);
    renderWith(settings("ru"), "ru");
    const select = await screen.findByRole<HTMLSelectElement>("combobox", {
      name: "Город для календаря",
    });

    await waitFor(() => {
      expect(optionTexts(select)[0]).toBe("👥 Как у учителя (Anna)");
    });
  });

  it("shows the source line in Settings", async () => {
    stubApi(FOLLOWING);
    renderWith(settings());

    expect(
      await screen.findByText(
        exact("👥 Same as your main teacher, Anna. You can choose another city."),
      ),
    ).toBeInTheDocument();
  });
});

describe("The moon card names the source", () => {
  it("says it follows the main teacher", async () => {
    stubApi(FOLLOWING);
    renderWith(<MoonCard locale="en" />);

    expect(plain((await screen.findByRole("heading")).textContent)).toBe(
      "🌙 Moon days · 📍 Almaty",
    );
    expect(
      screen.getByText(exact("👥 Same as your main teacher, Anna. You can choose another city.")),
    ).toBeInTheDocument();
  });

  it("says when the followed teacher has no city yet", async () => {
    stubApi(
      location({
        explicit: true,
        follow_chosen: true,
        teacher: { id: ANNA, name: "Anna" },
      }),
    );
    renderWith(<MoonCard locale="en" />);

    await screen.findByRole("heading");
    expect(
      screen.getByText(
        exact("👥 Anna hasn't chosen a city yet, so the dates are for 📍 Mysuru for now."),
      ),
    ).toBeInTheDocument();
  });

  it("has no source line for a chosen city or the default", async () => {
    stubApi(location({ slug: "moscow", source: "chosen", explicit: true }));
    renderWith(<MoonCard locale="en" />);

    await screen.findByRole("heading");
    expect(screen.queryByText(/👥/)).not.toBeInTheDocument();
  });

  it.each([
    [true, "👥 Students who haven't chosen a city follow yours: 📍 Almaty."],
    [
      false,
      "👥 Your students' moon days are for 📍 Mysuru, like yours. You can keep it or choose your own city.",
    ],
  ])("tells a teacher their students follow (chosen: %s)", async (chosen, text) => {
    stubApi(
      chosen
        ? location({ slug: "almaty", source: "chosen", explicit: true, shared: { chosen } })
        : location({ shared: { chosen } }),
    );
    renderWith(<MoonCard locale="en" />);

    await screen.findByRole("heading");
    expect(screen.getByText(exact(text))).toBeInTheDocument();
  });
});

it.each([
  [
    true,
    "👥 Students in your shala follow its moon calendar. Your other students get 📍 Mysuru by default, or your city if you choose one.",
  ],
  // Only a student of the shala: their students in it would move to a city they choose.
  [
    false,
    "👥 Your students' moon days are for 📍 Mysuru. You can keep it or choose your own city.",
  ],
])(
  'doesn\'t say "like yours" to a teacher whose own moon days follow their shala (Q274, staff: %s)',
  async (staff, text) => {
    stubApi(
      location({
        slug: "almaty",
        source: "shala",
        shala: { id: "5b1e7d0c-0000-4000-8000-000000000001", name: "Ashtanga Almaty", staff },
        shared: { chosen: false },
      }),
    );
    renderWith(<MoonCard locale="en" />);

    await screen.findByRole("heading");
    expect(screen.getByText((_, el) => plain(el?.textContent ?? "") === text)).toBeInTheDocument();
    expect(screen.queryByText(/like yours/)).not.toBeInTheDocument();
  },
);

it("names the default for students of a teacher who follows their own teacher", async () => {
  // One hop: this teacher sees Almaty from their teacher, their students get Mysuru.
  stubApi({ ...FOLLOWING, explicit: true, follow_chosen: true, shared: { chosen: false } });
  renderWith(<MoonCard locale="en" />);

  await screen.findByRole("heading");
  expect(
    screen.getByText(
      (_, el) =>
        plain(el?.textContent ?? "") ===
        "👥 Your students' moon days are for 📍 Mysuru. You can keep it or choose your own city.",
    ),
  ).toBeInTheDocument();
});

describe("Make main and Remove refetch the moon days, days and stats", () => {
  const roots = (spy: { mock: { calls: unknown[][] } }) =>
    new Set(
      spy.mock.calls.map((call) => {
        const filters = call[0] as { queryKey?: readonly unknown[] } | undefined;
        return filters?.queryKey?.[0];
      }),
    );

  it("after Make main", async () => {
    const links = {
      teachers: [teacher(ANNA, "Anna", true), teacher(BORIS, "Boris", false)],
      students: [],
    };
    stubApi(FOLLOWING, links);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(client, "invalidateQueries");
    renderWith(<Links onBack={vi.fn()} onStudents={vi.fn()} />, "en", client);

    fireEvent.click(await screen.findByRole("button", { name: (n) => /Make main/.test(plain(n)) }));

    await waitFor(() => {
      for (const key of ["moon-days", "days", "stats"]) expect(roots(spy).has(key)).toBe(true);
    });
  });

  it("after Remove", async () => {
    telegram.confirmDestructive.mockResolvedValue(true);
    stubApi(FOLLOWING);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(client, "invalidateQueries");
    renderWith(<Links onBack={vi.fn()} onStudents={vi.fn()} />, "en", client);

    fireEvent.click(await screen.findByRole("button", { name: (n) => /Remove/.test(plain(n)) }));

    await waitFor(() => {
      for (const key of ["moon-days", "days", "stats"]) expect(roots(spy).has(key)).toBe(true);
    });
  });
});
