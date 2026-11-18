import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import { haptics } from "../../telegram";
import AskTeacher from "./AskTeacher";
import type { Said } from "./requests";

// UI-06 stage 4B (spec §4, §11; ADR-0049): the picker. A student of a shala asks one of its
// teachers from the app with the bot's question screen, line for line: the short consent, the
// full text behind Details, a name (or Yes) that is the consent and the request at once. The
// result is one of the bot's lines, given back to the screen that opened the picker. Nothing on
// it tells a teacher's "no" from silence. The API and the Telegram SDK are mocked.

const telegram = vi.hoisted(() => ({ back: vi.fn() as () => void }));

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: (onBack: () => void) => {
    telegram.back = onBack;
  },
  backButtonAvailable: vi.fn(() => true),
}));

const ME = {
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
const SHALA = { id: "00000000-0000-0000-0000-0000000000c1", name: "Mysore Room" };
const ANNA = { id: "00000000-0000-0000-0000-0000000000a1", name: "Anna" };
const BORIS = { id: "00000000-0000-0000-0000-0000000000a2", name: "Boris" };
const NONAME = { id: "00000000-0000-0000-0000-0000000000a3", name: null };
const CHOICES = `/api/v1/shalas/${SHALA.id}/teacher-choices`;
const ASK = "/api/v1/me/teacher-requests";

type Teacher = { id: string; name: string | null };
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Stub {
  /** Who can be asked, read again after each ask. */
  offer: () => Teacher[];
  /** The answer to the ask. */
  ask?: (body: unknown) => Response | Promise<Response>;
  me?: Partial<typeof ME>;
}

function stubApi(stub: Stub): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request.clone());
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/me") return json({ ...ME, ...stub.me });
      if (path === CHOICES) return json({ offer: stub.offer(), waiting: [] });
      if (path === ASK && request.method === "POST") {
        const body: unknown = await request.json();
        return (await stub.ask?.(body)) ?? json({ result: "created" });
      }
      return json({});
    }),
  );
  return seen;
}

function renderPicker(locale: Locale = "en", client?: QueryClient) {
  const queries = client ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onDone = vi.fn<(said: Said | null) => void>();
  render(
    <QueryClientProvider client={queries}>
      <L10nProvider locale={locale}>
        <AskTeacher shala={SHALA} onDone={onDone} />
      </L10nProvider>
    </QueryClientProvider>,
  );
  return onDone;
}

const plain = (text: string | null | undefined) => (text ?? "").replace(/[⁨⁩]/g, "");
const pageText = () => plain(document.querySelector("main")?.textContent);
const byText = (text: string) => (found: string) => plain(found) === text;
const button = (name: string) => screen.findByRole("button", { name: (n) => plain(n) === name });
const posts = (seen: Request[]) =>
  seen.filter((r) => r.method === "POST" && new URL(r.url).pathname === ASK);

const SHORT_EN =
  "• The teacher you pick sees your name (Ash) and what you log from today on: practice or " +
  "rest, your practice length and your last asana. If nothing shows for a while, they see a " +
  "short note saying just that.";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("the question", () => {
  it("one teacher: is she your teacher, the short consent and one Yes", async () => {
    stubApi({ offer: () => [ANNA] });
    renderPicker();

    const heading = await screen.findByRole("heading", { level: 1 });
    expect(plain(heading.textContent)).toBe("🏛 Mysore Room");
    await screen.findByText(byText("Is Anna your teacher?"));
    await waitFor(() => {
      expect(pageText()).toContain(SHORT_EN);
    });
    expect(pageText()).toContain("Nothing is shown until they confirm.");
    expect(pageText()).toContain("Pick only a teacher you know.");
    expect(await button("✅ Yes")).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Anna" })).toBeNull();
    expect(screen.getByRole("button", { name: "📄 Read in full" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByRole("button", { name: "Not now" })).toBeInTheDocument();
  });

  it("several teachers: who is your teacher, one button per name, a fallback for no name", async () => {
    stubApi({ offer: () => [ANNA, BORIS, NONAME] });
    renderPicker();

    await screen.findByText("Who is your teacher here?");
    const names = ["Anna", "Boris", "(no name)"];
    for (const name of names) expect(await button(name)).toBeEnabled();
    expect(screen.queryByRole("button", { name: "✅ Yes" })).toBeNull();
  });

  it("the heading has the focus, so a screen reader starts at the top", async () => {
    stubApi({ offer: () => [ANNA] });
    renderPicker();

    const heading = await screen.findByRole("heading", { level: 1 });
    expect(heading).toHaveFocus();
  });

  it("without a name of my own, the consent names none", async () => {
    stubApi({ offer: () => [ANNA], me: { display_name: null as unknown as string } });
    renderPicker();

    await button("✅ Yes");
    await waitFor(() => {
      expect(pageText()).toContain("sees your name and what you log");
    });
    expect(pageText()).not.toContain("()");
  });

  it("Russian: the bot's words", async () => {
    stubApi({ offer: () => [ANNA] });
    renderPicker("ru");

    await screen.findByText(byText("Anna — твой учитель?"));
    expect(await button("✅ Да")).toBeInTheDocument();
    expect(pageText()).toContain("Выбирай только учителя, которого знаешь.");
    expect(screen.getByRole("button", { name: "📄 Подробнее" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Не сейчас" })).toBeInTheDocument();
  });

  it("a long name is shown whole, in the question and on its button", async () => {
    const long = { id: BORIS.id, name: "Я".repeat(64) };
    stubApi({ offer: () => [ANNA, long] });
    renderPicker("ru");

    expect(await button(long.name)).toBeInTheDocument();
  });

  it("one teacher with a long name: the question names her whole", async () => {
    const long = { id: BORIS.id, name: "Я".repeat(64) };
    stubApi({ offer: () => [long] });
    renderPicker("ru");

    expect(await screen.findByText(byText(`${long.name} — твой учитель?`))).toBeVisible();
  });
});

describe("Details", () => {
  it("swaps the short consent for the full text, the names stay; and back", async () => {
    stubApi({ offer: () => [ANNA, BORIS] });
    renderPicker();
    await button("Anna");

    fireEvent.click(screen.getByRole("button", { name: "📄 Read in full" }));

    const back = screen.getByRole("button", { name: "‹ In short" });
    expect(back).toHaveAttribute("aria-expanded", "true");
    expect(pageText()).toContain("If you pick a teacher and they confirm:");
    expect(pageText()).toContain("Days count from today, even if they confirm a few days later.");
    expect(pageText()).not.toContain("stay private.\n• You can remove a teacher");
    expect(screen.getByRole("button", { name: "Anna" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Boris" })).toBeInTheDocument();

    fireEvent.click(back);

    expect(screen.getByRole("button", { name: "📄 Read in full" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(pageText()).not.toContain("If you pick a teacher and they confirm:");
    expect(pageText()).toContain(SHORT_EN);
  });

  it("a name tapped under the full text is the same consent", async () => {
    const seen = stubApi({ offer: () => [ANNA] });
    renderPicker();
    await button("✅ Yes");
    fireEvent.click(screen.getByRole("button", { name: "📄 Read in full" }));

    fireEvent.click(screen.getByRole("button", { name: "✅ Yes" }));

    await waitFor(() => {
      expect(posts(seen)).toHaveLength(1);
    });
    expect(await posts(seen)[0]?.json()).toEqual({
      shala_id: SHALA.id,
      teacher_id: ANNA.id,
      consent: "request-1",
    });
  });
});

describe("the tap", () => {
  it("sends the shala, the teacher and the consent it showed, never a flag", async () => {
    const seen = stubApi({ offer: () => [ANNA, BORIS] });
    const onDone = renderPicker();

    fireEvent.click(await button("Boris"));

    await waitFor(() => {
      expect(onDone).toHaveBeenCalledOnce();
    });
    expect(posts(seen)).toHaveLength(1);
    expect(await posts(seen)[0]?.json()).toEqual({
      shala_id: SHALA.id,
      teacher_id: BORIS.id,
      consent: "request-1",
    });
    expect(haptics.impact).toHaveBeenCalled();
  });

  it("names are disabled while it is sent, and the list holds still", async () => {
    let answer: (response: Response) => void = () => undefined;
    stubApi({
      offer: () => [ANNA, BORIS],
      ask: () =>
        new Promise<Response>((resolve) => {
          answer = resolve;
        }),
    });
    const onDone = renderPicker();

    fireEvent.click(await button("Anna"));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Anna" })).toBeDisabled();
    });
    expect(screen.getByRole("button", { name: "Boris" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Boris" }));
    await act(async () => {
      answer(json({ result: "created" }));
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(onDone).toHaveBeenCalledOnce();
    });
  });

  const LINES = {
    en: {
      created: "✉️ Request sent to Anna. Nothing from your log is shown until they confirm.",
      linked: "Anna is already on your list of teachers.",
      waiting: "You've already asked Anna. No answer yet.",
      recent: "You asked Anna not long ago. Try again later, or ask them for their invite link.",
      too_many: "You've asked several teachers lately. You can ask another in a few days.",
      full: "This request can't be sent right now. Try again later.",
    },
    ru: {
      created:
        "✉️ Запрос отправлен: Anna. Пока учитель не подтвердит, из твоего журнала ничего не видно.",
      linked: "Anna уже в списке твоих учителей.",
      waiting: "Запрос уже отправлен: Anna. Ответа пока нет.",
      recent:
        "Запрос уже был недавно: Anna. Попробуй позже или попроси у учителя ссылку-приглашение.",
      too_many:
        "Недавно уже были запросы другим учителям. Новый можно отправить через несколько дней.",
      full: "Сейчас отправить запрос не получится. Попробуй позже.",
    },
  } as const;

  it.each(
    (["en", "ru"] as const).flatMap((locale) =>
      Object.entries(LINES[locale]).map(([result, line]) => [locale, result, line] as const),
    ),
  )(
    "%s: %s gives the bot's line to the screen it was opened from",
    async (locale, result, line) => {
      stubApi({ offer: () => [ANNA], ask: () => json({ result }) });
      const onDone = renderPicker(locale);

      fireEvent.click(await button(locale === "en" ? "✅ Yes" : "✅ Да"));

      await waitFor(() => {
        expect(onDone).toHaveBeenCalledOnce();
      });
      const said = onDone.mock.calls[0]?.[0];
      expect(plain(said?.text)).toBe(line);
      expect(said?.alert).toBeFalsy();
    },
  );

  it("the choices are read again after the tap", async () => {
    let asked = false;
    const seen = stubApi({
      offer: () => (asked ? [] : [ANNA]),
      ask: () => {
        asked = true;
        return json({ result: "created" });
      },
    });
    const onDone = renderPicker();

    fireEvent.click(await button("✅ Yes"));

    await waitFor(() => {
      expect(onDone).toHaveBeenCalledOnce();
    });
    expect(seen.filter((r) => new URL(r.url).pathname === CHOICES)).toHaveLength(2);
  });
});

describe("when the tap can't be done", () => {
  it("403: the list is read again and redrawn without the name", async () => {
    let gone = false;
    stubApi({
      offer: () => (gone ? [BORIS, NONAME] : [ANNA, BORIS, NONAME]),
      ask: () => {
        gone = true;
        return json({ code: "not_allowed" }, 403);
      },
    });
    const onDone = renderPicker();

    fireEvent.click(await button("Anna"));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Anna" })).toBeNull();
    });
    expect(screen.getByRole("button", { name: "Boris" })).toBeEnabled();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("403 with nobody left: says so", async () => {
    let gone = false;
    stubApi({
      offer: () => (gone ? [] : [ANNA]),
      ask: () => {
        gone = true;
        return json({ code: "not_allowed" }, 403);
      },
    });
    const onDone = renderPicker();

    fireEvent.click(await button("✅ Yes"));

    expect(await screen.findByText("There's no one else to pick here right now.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "✅ Yes" })).toBeNull();
    expect(pageText()).not.toContain("Pick only a teacher you know.");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("404 (left the shala meanwhile): closes with a short line, and my shalas are read again", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(["shalas", "mine"], []);
    client.setQueryData(["links"], { teachers: [], students: [] });
    stubApi({ offer: () => [ANNA], ask: () => json({ code: "not_found" }, 404) });
    const onDone = renderPicker("en", client);

    fireEvent.click(await button("✅ Yes"));

    await waitFor(() => {
      expect(onDone).toHaveBeenCalledOnce();
    });
    expect(onDone.mock.calls[0]?.[0]).toEqual({
      text: "Couldn't load the shala. Try again in a moment.",
      alert: true,
    });
    expect(client.getQueryState(["shalas", "mine"])?.isInvalidated).toBe(true);
    expect(client.getQueryState(["links"])?.isInvalidated).toBe(true);
  });

  it("anything else: a line, an error buzz, and the picker stays", async () => {
    stubApi({ offer: () => [ANNA], ask: () => json({ code: "unavailable" }, 503) });
    const onDone = renderPicker();

    fireEvent.click(await button("✅ Yes"));

    const line = await screen.findByRole("alert");
    expect(plain(line.textContent)).toBe("Couldn't save. Try again in a moment.");
    expect(haptics.notify).toHaveBeenCalledWith("error");
    expect(screen.getByRole("button", { name: "✅ Yes" })).toBeEnabled();
    expect(onDone).not.toHaveBeenCalled();
  });
});

describe("leaving", () => {
  it("Not now and Back close it and send nothing", async () => {
    const seen = stubApi({ offer: () => [ANNA] });
    const onDone = renderPicker();

    fireEvent.click(await button("Not now"));
    expect(onDone).toHaveBeenLastCalledWith(null);

    act(() => {
      telegram.back();
    });
    expect(onDone).toHaveBeenCalledTimes(2);
    expect(onDone).toHaveBeenLastCalledWith(null);
    expect(posts(seen)).toHaveLength(0);
  });
});

describe("no 'no' can be read", () => {
  it("the picker shows no state, date or count, in either layer", async () => {
    stubApi({ offer: () => [ANNA, BORIS] });
    renderPicker();
    await button("Anna");

    const short = pageText();
    fireEvent.click(screen.getByRole("button", { name: "📄 Read in full" }));
    const full = pageText();

    expect(full).not.toBe(short);
    for (const text of [short, full]) {
      expect(text).not.toMatch(/\d/);
      expect(text).not.toMatch(/declin|reject|refus|not your|expire|ago\b/i);
    }
  });
});
