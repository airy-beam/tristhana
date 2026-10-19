import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import type { City, MoonDays, NotificationSettings } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import type { Locale } from "../i18n/negotiate";
import { MoonCard } from "./MoonCard";
import { TodayCard } from "./TodayCard";

vi.mock("../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
}));

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
  timezone: "Asia/Almaty",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubApi(moon: MoonDays = MOON): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request);
      const path = new URL(request.url).pathname;
      if (request.method === "PUT") return json(await request.clone().json());
      if (path === "/api/v1/me/moon-days") return json(moon);
      if (path === "/api/v1/moon/cities") return json(CITIES);
      if (path === "/api/v1/me/notification-settings") return json(SETTINGS);
      if (path === "/api/v1/me/days") return json({ today: TODAY, timezone_known: true, days: [] });
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
    renderWith(<MoonCard locale="en" zone="Asia/Almaty" />);

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
    renderWith(<MoonCard locale="en" zone="Asia/Almaty" />);
    const select = await screen.findByRole("combobox");

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
    renderWith(<MoonCard locale="en" zone="Asia/Almaty" />);

    fireEvent.click(
      await screen.findByRole("button", {
        name: (name) => plain(name) === "3 days",
        pressed: false,
      }),
    );

    await vi.waitFor(() => {
      expect(seen.some((r) => r.method === "PUT")).toBe(true);
    });
    const put = seen.find((r) => r.method === "PUT");
    expect(await put?.json()).toMatchObject({ moon: { offsets: [1, 7, 3], at: "19:00:00" } });
  });

  it("explains that reminders need a time zone", async () => {
    stubApi();
    renderWith(<MoonCard locale="en" zone={null} />);

    expect(await screen.findByText(/once your time zone is known/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: (name) => /^\d+ days?$/.test(plain(name)) }),
    ).not.toBeInTheDocument();
  });

  it("uses Russian city names and plurals", async () => {
    stubApi();
    renderWith(<MoonCard locale="ru" zone="Asia/Almaty" />, "ru");

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
