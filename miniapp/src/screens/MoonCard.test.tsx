import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import type { City, Me, MoonDays, NotificationSettings } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import type { Locale } from "../i18n/negotiate";
import { MoonCard } from "./MoonCard";
import { PracticeReminderCard } from "./PracticeReminderCard";
import Settings from "./settings/Settings";
import { TodayCard } from "./TodayCard";

vi.mock("../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
}));

const ME: Me = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Ash",
  locale: "en",
  timezone: "Asia/Almaty",
  name_from_telegram: true,
  locale_from_telegram: true,
};

const TODAY = "2026-10-19";
const MOON: MoonDays = {
  location: { slug: "mysuru", explicit: false },
  today: TODAY,
  days: [
    { date: "2026-10-22", kind: "purnima", phase: "purnima" },
    { date: "2026-11-06", kind: "kshaya_amavasya", phase: "amavasya" },
  ],
};
const CITIES: City[] = [
  { slug: "mysuru", name_en: "Mysuru", name_ru: "Майсур", timezone: "Asia/Kolkata" },
  { slug: "almaty", name_en: "Almaty", name_ru: "Алматы", timezone: "Asia/Almaty" },
];
const SETTINGS: NotificationSettings = {
  moon: { offsets: [1, 7], at: "19:00:00" },
  quiet: { start: "22:00:00", end: "07:00:00" },
  daily_cap: 3,
  practice: { on: null, at: "10:00:00", days: [1, 2, 3, 4, 5, 7] },
  timezone: "Asia/Almaty",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubApi(moon: MoonDays = MOON, settings: NotificationSettings = SETTINGS): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request);
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/me/day-off") {
        const { day_off } = (await request.clone().json()) as { day_off: number[] };
        const off = new Set(day_off);
        const practice_days = [1, 2, 3, 4, 5, 6, 7].filter((d) => !off.has(d));
        return json({ day_off, practice_days });
      }
      if (path === "/api/v1/me") return json({ ...ME, day_off: [6] });
      if (request.method === "PUT") return json(await request.clone().json());
      if (request.method === "PATCH") {
        // Echo the merged settings, as the server does.
        const body = (await request.clone().json()) as Partial<NotificationSettings>;
        return json({
          ...settings,
          ...body,
          moon: { ...settings.moon, ...body.moon },
          practice: { ...settings.practice, ...body.practice },
        });
      }
      if (path === "/api/v1/me/moon-days") return json(moon);
      if (path === "/api/v1/moon/cities") return json(CITIES);
      if (path === "/api/v1/me/notification-settings") return json(settings);
      if (path === "/api/v1/me/days")
        return json({
          today: TODAY,
          timezone_known: true,
          auto: [],
          moon_location: "mysuru",
          days: [],
        });
      return json({});
    }),
  );
  return seen;
}

function renderWith(node: React.ReactNode, locale: Locale = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>{node}</L10nProvider>
    </QueryClientProvider>,
  );
}

const plain = (text: string) => text.replace(/[\u2068\u2069]/g, "");
const visible = (el: HTMLElement) => plain(el.textContent);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("MoonCard", () => {
  it("lists upcoming moon days for the followed city", async () => {
    stubApi();
    renderWith(<MoonCard locale="en" />);

    expect(visible(await screen.findByRole("heading"))).toBe("🌙 Moon days · 📍 Mysuru");
    const items = screen.getAllByRole("listitem").map(visible);
    expect(items).toEqual([
      "🌕 Full moon (Purnima) · Thu, Oct 22 · in 3 days",
      "🌑 New moon (Amavasya) · Fri, Nov 6 · in 18 days",
    ]);
    expect(screen.getByText(/follow your teacher/)).toBeInTheDocument();
  });

  it("changes the city", async () => {
    const seen = stubApi();
    renderWith(<Settings me={ME} onBack={vi.fn()} />);
    const select = await screen.findByRole("combobox", { name: "City for the calendar" });

    fireEvent.change(select, { target: { value: "almaty" } });

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PUT")).toBe(true);
    });
    const put = seen.find((r) => r.method === "PUT");
    expect(new URL(put?.url ?? "").pathname).toBe("/api/v1/me/moon-location");
    expect(await put?.json()).toEqual({ slug: "almaty" });
  });

  it("toggles reminder offsets", async () => {
    const seen = stubApi();
    renderWith(<Settings me={ME} onBack={vi.fn()} />);

    fireEvent.click(
      await screen.findByRole("button", {
        name: (name) => plain(name) === "3 days",
        pressed: false,
      }),
    );

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PATCH")).toBe(true);
    });
    const patch = seen.find((r) => r.method === "PATCH");
    // Only what was tapped: a change made in the bot meanwhile stays (ADR-0021).
    expect(await patch?.json()).toEqual({ moon: { offsets: [1, 7, 3] } });
  });

  it("explains that reminders need a time zone", async () => {
    stubApi();
    renderWith(<Settings me={{ ...ME, timezone: null }} onBack={vi.fn()} />);

    expect(await screen.findByText(/once your time zone is known/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: (name) => /^\d+ days?$/.test(plain(name)) }),
    ).not.toBeInTheDocument();
  });

  it("uses Russian city names and plurals", async () => {
    stubApi();
    renderWith(<MoonCard locale="ru" />, "ru");

    expect(visible(await screen.findByRole("heading"))).toBe("🌙 Лунные дни · 📍 Майсур");
    expect(visible(screen.getAllByRole("listitem")[0] as HTMLElement)).toContain("через 3 дня");
  });
});

it("the Today card notes a moon day without picking a status", async () => {
  stubApi({ ...MOON, days: [{ date: TODAY, kind: "purnima", phase: "purnima" }] });
  renderWith(<TodayCard locale="en" zone="Asia/Almaty" />);

  expect(
    await screen.findByText(
      (_, el) => el?.tagName === "P" && plain(el.textContent) === "🌕 Full moon today · 📍 Mysuru",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { pressed: true })).not.toBeInTheDocument();
});

describe("PracticeReminderCard", () => {
  it("is off until chosen and turns on with the practice block", async () => {
    const seen = stubApi();
    renderWith(<PracticeReminderCard zone="Asia/Almaty" />);

    const toggle = await screen.findByRole("button", {
      name: (name) => plain(name) === "🔔 Ask me once a day",
      pressed: false,
    });
    expect(screen.queryByRole("button", { name: "10:00" })).not.toBeInTheDocument();
    fireEvent.click(toggle);

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PATCH")).toBe(true);
    });
    const put = seen.find((r) => r.method === "PATCH");
    expect(await put?.json()).toEqual({ practice: { on: true } });
    expect(await screen.findByRole("button", { name: "10:00", pressed: true })).toBeInTheDocument();
    expect(
      screen.getByText(
        (_, el) => el?.tagName === "P" && plain(el.textContent) === "Time · Almaty (UTC+5)",
      ),
    ).toBeInTheDocument();
  });

  it("comes on the practice days, with no day choices of its own (PR-09)", async () => {
    stubApi(MOON, { ...SETTINGS, practice: { on: true, at: "10:00:00", days: [1, 2, 3, 4, 5] } });
    renderWith(<PracticeReminderCard zone="Asia/Almaty" />);

    expect(
      await screen.findByText(
        (t) =>
          plain(t) === "On your practice days: Mon, Tue, Wed, Thu, Fri. Change them under Day off.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: (n) => plain(n) === "Sat" }),
    ).not.toBeInTheDocument();
  });

  it("asks for a time zone before showing times", async () => {
    stubApi(MOON, { ...SETTINGS, practice: { on: true, at: "10:00:00", days: [1] } });
    renderWith(<PracticeReminderCard zone={null} />);

    expect(await screen.findByText(/once your time zone is known/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "10:00" })).not.toBeInTheDocument();
  });
});
