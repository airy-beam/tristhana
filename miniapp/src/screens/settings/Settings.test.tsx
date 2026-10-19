import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import type { City, Me, NotificationSettings } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import Settings from "./Settings";
import { TravelPrompt } from "./TravelPrompt";

vi.mock("../../telegram", () => ({
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
const CITIES: City[] = [
  { slug: "mysuru", name_en: "Mysuru", name_ru: "Майсур", timezone: "Asia/Kolkata" },
  { slug: "almaty", name_en: "Almaty", name_ru: "Алматы", timezone: "Asia/Almaty" },
  { slug: "bangkok", name_en: "Bangkok", name_ru: "Бангкок", timezone: "Asia/Bangkok" },
  { slug: "sochi", name_en: "Sochi", name_ru: "Сочи", timezone: "Europe/Moscow" },
  { slug: "moscow", name_en: "Moscow", name_ru: "Москва", timezone: "Europe/Moscow" },
];
const SETTINGS: NotificationSettings = {
  moon: { offsets: [1, 7], at: "19:00:00" },
  quiet: { start: "22:00:00", end: "07:00:00" },
  daily_cap: 3,
  practice: { on: true, at: "20:00:00", days: [1, 2, 3, 4, 5, 7] },
  timezone: "Asia/Almaty",
};

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

function stubApi(): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request);
      const path = new URL(request.url).pathname;
      if (request.method === "PATCH" && path === "/api/v1/me") {
        return json({ ...ME, ...(await request.clone().json()) });
      }
      if (request.method === "PATCH") return json(SETTINGS);
      if (path === "/api/v1/moon/cities") return json(CITIES);
      if (path === "/api/v1/me/notification-settings") return json(SETTINGS);
      if (path === "/api/v1/me/moon-days") {
        return json({
          location: { slug: "mysuru", explicit: false },
          today: "2026-10-19",
          days: [],
        });
      }
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

const plain = (text: string) => text.replace(/[⁨⁩]/g, "");

async function bodies(seen: Request[], method: string, path: string): Promise<unknown[]> {
  await vi.waitFor(() => {
    expect(seen.some((r) => r.method === method && new URL(r.url).pathname === path)).toBe(true);
  });
  return Promise.all(
    seen
      .filter((r) => r.method === method && new URL(r.url).pathname === path)
      .map((r) => r.clone().json() as Promise<unknown>),
  );
}

function deviceZoneIs(zone: string) {
  const Real = Intl.DateTimeFormat;
  // A regular function, so it works with and without `new` like the real constructor.
  function Fake(locale?: string | string[], options?: Intl.DateTimeFormatOptions) {
    const format = new Real(locale, options);
    if (options === undefined) {
      const resolved = format.resolvedOptions();
      format.resolvedOptions = () => ({ ...resolved, timeZone: zone });
    }
    return format;
  }
  vi.spyOn(Intl, "DateTimeFormat").mockImplementation(
    Fake as unknown as typeof Intl.DateTimeFormat,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("Settings", () => {
  it("saves a name on blur, and blank goes back to the Telegram name", async () => {
    const seen = stubApi();
    renderWith(<Settings me={ME} onBack={vi.fn()} />);
    const name = await screen.findByRole("textbox", { name: "Name" });
    expect(name).toHaveAttribute("placeholder", "Ash");

    fireEvent.change(name, { target: { value: "  Anna 🧘 " } });
    fireEvent.blur(name);

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ display_name: "Anna 🧘" }]);
  });

  it("switches the language and back to Telegram's", async () => {
    const seen = stubApi();
    renderWith(<Settings me={{ ...ME, locale_from_telegram: false }} onBack={vi.fn()} />);

    expect(
      await screen.findByRole("button", { name: "English", pressed: true }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "As in Telegram" }));

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ locale: null }]);
  });

  it("offers the phone's zone and a city list (one per zone, plus UTC)", async () => {
    deviceZoneIs("Asia/Bangkok");
    const seen = stubApi();
    renderWith(<Settings me={ME} onBack={vi.fn()} />);

    fireEvent.click(
      await screen.findByRole("button", {
        name: (n) => plain(n).startsWith("Use this phone's zone: Bangkok"),
      }),
    );
    const select = await screen.findByRole("combobox", { name: "Pick a city" });
    expect([...select.querySelectorAll("option")].map((o) => o.value)).toEqual([
      "",
      "almaty",
      "bangkok",
      "moscow",
      "mysuru",
      "sochi",
      "UTC",
    ]);

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ timezone: "Asia/Bangkok" }]);
  });

  it("won't let quiet hours swallow an active reminder, and sets the cap", async () => {
    const seen = stubApi();
    renderWith(<Settings me={ME} onBack={vi.fn()} />);

    const from = await screen.findByRole("combobox", { name: "Quiet from" });
    const option = (h: string) => from.querySelector(`option[value="${h}"]`) as HTMLOptionElement;
    expect(option("19:00").disabled).toBe(true); // 19:00 moon and 20:00 practice
    expect(option("21:00").disabled).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "2" }));

    expect(await bodies(seen, "PATCH", "/api/v1/me/notification-settings")).toEqual([
      { daily_cap: 2 },
    ]);
  });

  it("explains privacy and shares the 🌸 switch with Stats", async () => {
    stubApi();
    renderWith(<Settings me={ME} onBack={vi.fn()} />);

    expect(await screen.findByText(/stored encrypted/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Show 🌸 days on this device" }));
    expect(localStorage.getItem("stats.showLadies")).toBe("1");
  });
});

describe("TravelPrompt", () => {
  it("offers to switch when the phone's offset differs, and remembers Keep", async () => {
    deviceZoneIs("Asia/Bangkok");
    stubApi();
    const { unmount } = renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" />);

    expect(
      await screen.findByText(
        (_, el) =>
          el?.tagName === "P" &&
          plain(el.textContent) ===
            "Your phone is on Bangkok (UTC+7) time. Reminders use Almaty (UTC+5).",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: (n) => plain(n) === "Keep Almaty" }));
    unmount();

    renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("switches the zone on request", async () => {
    deviceZoneIs("Asia/Bangkok");
    const seen = stubApi();
    renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" />);

    fireEvent.click(
      await screen.findByRole("button", { name: (n) => plain(n) === "Switch to Bangkok" }),
    );

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ timezone: "Asia/Bangkok" }]);
  });

  it("stays quiet for the same clock under another name", () => {
    deviceZoneIs("Europe/Kiev");
    stubApi();
    renderWith(<TravelPrompt zone="Europe/Kyiv" locale="en" />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("says nothing when the phone reports UTC", () => {
    deviceZoneIs("UTC");
    stubApi();
    renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps the prompt and explains when the switch fails", async () => {
    deviceZoneIs("Asia/Bangkok");
    stubApi();
    vi.stubGlobal(
      "fetch",
      vi.fn((request: Request) =>
        request.method === "PATCH"
          ? new Response(JSON.stringify({ code: "unavailable" }), { status: 503 })
          : json(new URL(request.url).pathname === "/api/v1/moon/cities" ? CITIES : {}),
      ),
    );
    renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" />);

    fireEvent.click(
      await screen.findByRole("button", { name: (n) => plain(n) === "Switch to Bangkok" }),
    );

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});

describe("time zone cities", () => {
  it("lists every city, even several in one zone, and sets its zone", async () => {
    const seen = stubApi();
    renderWith(<Settings me={{ ...ME, timezone: "Europe/Moscow" }} onBack={vi.fn()} />);
    const select = await screen.findByRole("combobox", { name: "Pick a city" });

    expect(select).toHaveValue("moscow"); // named after the zone, though Sochi is listed first
    fireEvent.change(select, { target: { value: "sochi" } });

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ timezone: "Europe/Moscow" }]);
  });
});
