import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

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
  hide_ladies: false,
  offer_check_in: true, // WH-01 part 2
  home_city_chosen: true, // MD-04: no nudge in these tests
};
const ALMATY: City = {
  slug: "almaty",
  name_en: "Almaty",
  name_ru: "Алматы",
  timezone: "Asia/Almaty",
};
const SOCHI: City = { slug: "sochi", name_en: "Sochi", name_ru: "Сочи", timezone: "Europe/Moscow" };
const CITIES: City[] = [
  { slug: "mysuru", name_en: "Mysuru", name_ru: "Майсур", timezone: "Asia/Kolkata" },
  ALMATY,
  { slug: "bangkok", name_en: "Bangkok", name_ru: "Бангкок", timezone: "Asia/Bangkok" },
  SOCHI,
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

let dayOffFails = false;
let meFails = false;

function stubApi(): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request);
      const path = new URL(request.url).pathname;
      if (request.method === "PATCH" && path === "/api/v1/me") {
        if (meFails) return new Response(JSON.stringify({ code: "unavailable" }), { status: 503 });
        return json({ ...ME, ...(await request.clone().json()) });
      }
      if (request.method === "PATCH") return json(SETTINGS);
      if (path === "/api/v1/me/day-off") {
        if (dayOffFails)
          return new Response(JSON.stringify({ code: "unavailable" }), { status: 503 });
        const { day_off } = (await request.clone().json()) as { day_off: number[] };
        return json({
          day_off,
          practice_days: [1, 2, 3, 4, 5, 6, 7].filter((d) => !day_off.includes(d)),
        });
      }
      if (path === "/api/v1/me") return json({ ...ME, day_off: null });
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

  it("lists every city, plus 'not listed' that offers the phone's time or UTC", async () => {
    deviceZoneIs("Asia/Bangkok");
    const seen = stubApi();
    renderWith(<Settings me={{ ...ME, home_city: ALMATY }} onBack={vi.fn()} />);
    const select = await screen.findByRole("combobox", { name: "Which city do you live in?" });
    expect([...select.querySelectorAll("option")].map((o) => o.value)).toEqual([
      "",
      "almaty",
      "bangkok",
      "moscow",
      "mysuru",
      "sochi",
      "-",
    ]);
    expect(screen.queryByRole("button", { name: /Use my phone's time/ })).not.toBeInTheDocument();

    fireEvent.change(select, { target: { value: "-" } });
    expect(select).toHaveValue("-"); // stays on "not listed" while the chips are shown
    fireEvent.click(
      await screen.findByRole("button", {
        name: (n) => plain(n).startsWith("Use my phone's time: Bangkok (UTC+7)"),
      }),
    );

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([
      { home_city: null, timezone: "Asia/Bangkok" },
    ]);
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

  it("names the home city as 'here'", async () => {
    deviceZoneIs("Asia/Bangkok");
    stubApi();
    const astana: City = {
      slug: "astana",
      name_en: "Astana",
      name_ru: "Астана",
      timezone: "Asia/Almaty",
    };
    renderWith(<TravelPrompt zone="Asia/Almaty" locale="en" home={astana} />);

    expect(
      await screen.findByRole("button", { name: (n) => plain(n) === "Keep Astana" }),
    ).toBeInTheDocument();
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

describe("My city (MD-04)", () => {
  afterEach(() => {
    meFails = false;
  });

  it("marks the stored city, not another one in its zone, and saves the slug", async () => {
    const seen = stubApi();
    renderWith(
      <Settings me={{ ...ME, timezone: "Europe/Moscow", home_city: SOCHI }} onBack={vi.fn()} />,
    );
    const select = await screen.findByRole("combobox", { name: "Which city do you live in?" });

    expect(select).toHaveValue("sochi"); // the bug: Moscow used to be marked
    fireEvent.change(select, { target: { value: "moscow" } });

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ home_city: "moscow" }]);
  });

  it("labels the time with the city's name", async () => {
    stubApi();
    const astana: City = {
      slug: "astana",
      name_en: "Astana",
      name_ru: "Астана",
      timezone: "Asia/Almaty",
    };
    renderWith(<Settings me={{ ...ME, home_city: astana }} onBack={vi.fn()} />);

    expect(
      await screen.findByText(
        (_, el) => el?.tagName === "P" && /Astana \(UTC\+5\)$/.test(plain(el.textContent)),
      ),
    ).toBeInTheDocument();
  });

  it("nudges once: Not now answers it and keeps the zone", async () => {
    const seen = stubApi();
    renderWith(<Settings me={{ ...ME, home_city_chosen: false }} onBack={vi.fn()} />);

    expect(
      await screen.findByText("Pick your city if you like: times will then show its name."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ home_city: null }]);
  });

  it("has no nudge once answered", async () => {
    stubApi();
    renderWith(<Settings me={ME} onBack={vi.fn()} />);
    await screen.findByRole("combobox", { name: "Which city do you live in?" });

    expect(
      screen.queryByText("Pick your city if you like: times will then show its name."),
    ).not.toBeInTheDocument();
  });

  it("shows the old city again when the save fails", async () => {
    meFails = true;
    stubApi();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(["me"], { ...ME, home_city: SOCHI, timezone: "Europe/Moscow" });
    client.setQueryData(["moon-cities"], CITIES);
    function Live() {
      const me = client.getQueryData<Me>(["me"]) ?? ME;
      return <Settings me={me} onBack={vi.fn()} />;
    }
    render(
      <QueryClientProvider client={client}>
        <L10nProvider locale="en">
          <Live />
        </L10nProvider>
      </QueryClientProvider>,
    );
    const select = await screen.findByRole("combobox", { name: "Which city do you live in?" });

    fireEvent.change(select, { target: { value: "almaty" } });

    expect(await screen.findAllByRole("alert")).not.toHaveLength(0);
    expect(client.getQueryData<Me>(["me"])?.home_city?.slug).toBe("sochi");
  });

  it("offers 'Same as my city' first in the moon calendar picker", async () => {
    const seen = stubApi();
    renderWith(<Settings me={{ ...ME, home_city: ALMATY }} onBack={vi.fn()} />);
    const select = await screen.findByRole("combobox", { name: "City for the calendar" });

    const first = select.querySelector("option");
    expect(first?.textContent && plain(first.textContent)).toBe("Same as my city (Almaty)");
    fireEvent.change(select, { target: { value: "almaty" } });

    expect(await bodies(seen, "PUT", "/api/v1/me/moon-location")).toEqual([{ slug: "almaty" }]);
  });
});

describe("Day off (PR-09)", () => {
  afterEach(() => {
    dayOffFails = false;
  });

  it("starts with nothing pressed and takes up to two days off", async () => {
    const seen = stubApi();
    renderWith(<Settings me={{ ...ME, day_off: null }} onBack={vi.fn()} />);
    const group = await screen.findByRole("group", { name: "Day off" });
    const chip = (name: string) =>
      within(group).getByRole("button", { name: (n) => plain(n) === name });
    expect(within(group).queryAllByRole("button", { pressed: true })).toHaveLength(0);
    expect(screen.getByText(/Past weeks show them too/)).toBeInTheDocument();

    fireEvent.click(chip("Sun"));
    await vi.waitFor(() => {
      expect(chip("Sun")).toHaveAttribute("aria-pressed", "true");
    });
    fireEvent.click(chip("Sat"));
    await vi.waitFor(() => {
      expect(chip("Sat")).toHaveAttribute("aria-pressed", "true");
    });

    expect(chip("Mon")).toBeDisabled(); // a third day off waits until one is unpressed
    expect(await bodies(seen, "PUT", "/api/v1/me/day-off")).toEqual([
      { day_off: [7] },
      { day_off: [6, 7] },
    ]);
  });

  it("rolls back when the save fails", async () => {
    dayOffFails = true;
    stubApi();
    renderWith(<Settings me={{ ...ME, day_off: null }} onBack={vi.fn()} />);
    const group = await screen.findByRole("group", { name: "Day off" });
    fireEvent.click(within(group).getByRole("button", { name: "No fixed day off" }));

    expect(await screen.findAllByText("Couldn't save. Try again in a moment.")).not.toHaveLength(0);
    expect(within(group).queryAllByRole("button", { pressed: true })).toHaveLength(0);
  });
});

describe("Hide the 🌸 button (WH-01 part 2)", () => {
  afterEach(() => {
    meFails = false;
  });

  const shown = { ...ME, hide_ladies: false } as Me;
  const toggle = () =>
    screen.findByRole("checkbox", {
      name: (n) => plain(n) === "Show the 🌸 Ladies' holiday button",
    });

  it("is on by default, explains itself, and saves at once", async () => {
    const seen = stubApi();
    renderWith(<Settings me={shown} onBack={vi.fn()} />);

    const box = await toggle();
    expect(box).toBeChecked();
    expect(
      screen.getByText("In the bot and here. Days you already logged stay as they are."),
    ).toBeInTheDocument();
    fireEvent.click(box);

    expect(box).not.toBeChecked(); // optimistic
    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ hide_ladies: true }]);
  });

  it("reads the stored choice", async () => {
    stubApi();
    renderWith(<Settings me={{ ...ME, hide_ladies: true }} onBack={vi.fn()} />);

    expect(await toggle()).not.toBeChecked();
  });

  it("rolls back when the save fails", async () => {
    meFails = true;
    stubApi();
    renderWith(<Settings me={shown} onBack={vi.fn()} />);
    const box = await toggle();

    fireEvent.click(box);

    await vi.waitFor(() => {
      expect(box).toBeChecked();
    });
  });

  it("is separate from the device-only 🌸 days switch", async () => {
    stubApi();
    renderWith(<Settings me={shown} onBack={vi.fn()} />);
    fireEvent.click(await toggle());

    expect(screen.getByRole("checkbox", { name: "Show 🌸 days on this device" })).not.toBeChecked();
    expect(localStorage.getItem("stats.showLadies")).not.toBe("1");
  });
});

describe("Offer a check-in after practice (PR-06)", () => {
  afterEach(() => {
    meFails = false;
  });

  const offered = { ...ME, offer_check_in: true } as Me;
  const toggle = () => screen.findByRole("checkbox", { name: "Offer a check-in after practice" });

  it("is on by default, explains itself, and saves at once", async () => {
    const seen = stubApi();
    renderWith(<Settings me={offered} onBack={vi.fn()} />);

    const box = await toggle();
    expect(box).toBeChecked();
    expect(
      screen.getByText(
        "Mood, energy and effort right after logging today's practice. You can always add one from the day.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(box);

    expect(box).not.toBeChecked(); // optimistic
    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ offer_check_in: false }]);
  });

  it("reads the stored choice and turns it back on", async () => {
    const seen = stubApi();
    renderWith(<Settings me={{ ...offered, offer_check_in: false }} onBack={vi.fn()} />);

    const box = await toggle();
    expect(box).not.toBeChecked();
    fireEvent.click(box);

    expect(await bodies(seen, "PATCH", "/api/v1/me")).toEqual([{ offer_check_in: true }]);
  });

  it("rolls back when the save fails", async () => {
    meFails = true;
    stubApi();
    renderWith(<Settings me={offered} onBack={vi.fn()} />);
    const box = await toggle();

    fireEvent.click(box);

    await vi.waitFor(() => {
      expect(box).toBeChecked();
    });
  });

  it("is in Russian too", async () => {
    stubApi();
    renderWith(<Settings me={offered} onBack={vi.fn()} />, "ru");

    expect(
      await screen.findByRole("checkbox", {
        name: "Предлагать отметить самочувствие после практики",
      }),
    ).toBeChecked();
  });
});
