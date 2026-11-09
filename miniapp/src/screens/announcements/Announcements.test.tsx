import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import Announcements, { type AnnouncementsMode } from "./Announcements";

// NT-03 (spec §2, §8): compose (audience line, the 1000 counter, pin, the date hint, the shala
// hint only for a shala, confirm/cancel, 409 keeps the text, success clears it); the sent list
// (unpin, pin, delete confirm); the feed (pin first, source chips, the mute switch, empty).
// API and SDK mocked.

const tg = vi.hoisted(() => ({
  confirmAction: vi.fn(async () => Promise.resolve(true)),
  confirmDestructive: vi.fn(async () => Promise.resolve(true)),
}));

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
  backButtonAvailable: vi.fn(() => true),
  confirmAction: tg.confirmAction,
  confirmDestructive: tg.confirmDestructive,
}));

const ME = "00000000-0000-4000-8000-000000000001";
const ANNA = "00000000-0000-4000-8000-0000000000a1";
const SHALA = "00000000-0000-4000-8000-0000000000b1";

const json = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const links = {
  teachers: [],
  students: [
    { id: "s1", name: "Bea", linked_at: "2026-10-01T00:00:00Z" },
    { id: "s2", name: "Cy", linked_at: "2026-10-01T00:00:00Z" },
  ],
};
const shala = {
  id: SHALA,
  name: "Ashtanga Almaty",
  city: { slug: "almaty", name: "Almaty" },
  zone: "Asia/Almaty",
  online: false,
  moon_city: null,
  staff: [
    { id: ME, name: "Ash", owner: false, roles: ["office"] },
    { id: ANNA, name: "Anna", owner: true, roles: ["teacher"] },
  ],
  students_total: 5,
  me: { owner: false, roles: ["office"], student: false, schedule: true, announce: true },
  days_off: null,
  moon_policy: "closed",
};
const sentItem = (id: string, pinned: string | null) => ({
  id,
  source: { kind: "teacher", id: ME, name: "Ash" },
  text: `Led class ${id}`,
  created_at: "2026-11-09T05:00:00Z",
  pinned_until: pinned,
  audience: 2,
});
const feed = {
  items: [
    {
      id: "p1",
      source: { kind: "shala", id: SHALA, name: "Ashtanga Almaty" },
      author_name: "Anna",
      text: "Closed 1-20 August",
      created_at: "2026-11-01T05:00:00Z",
      pinned_until: "2026-12-01T05:00:00Z",
      can_manage: false,
    },
    {
      id: "n1",
      source: { kind: "teacher", id: ANNA, name: "Anna" },
      author_name: "Anna",
      text: "No Mysore Mon 10 Nov",
      created_at: "2026-11-09T05:00:00Z",
      pinned_until: null,
      can_manage: false,
    },
  ],
  sources: [
    { kind: "teacher", id: ANNA, name: "Anna", muted: false },
    { kind: "shala", id: SHALA, name: "Ashtanga Almaty", muted: true },
  ],
  more: false,
};

let calls: { method: string; path: string; body: unknown }[] = [];

function stubApi(
  opts: { post?: Response; sent?: unknown[]; feed?: unknown; pages?: unknown[] } = {},
) {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname + new URL(request.url).search;
      const text = request.method === "GET" ? "" : await request.text();
      calls.push({ method: request.method, path, body: text ? JSON.parse(text) : null });
      if (path === "/api/v1/me/links") return json(links);
      if (path === `/api/v1/shalas/${SHALA}`) return json(shala);
      if (path === "/api/v1/me/announcements/sent") return json(opts.sent ?? []);
      if (path.startsWith("/api/v1/me/announcements") && request.method === "GET") {
        if (path.includes(`kind=teacher&id=${ANNA}`))
          return json({ items: [feed.items[1]], sources: [feed.sources[0]], more: false });
        if (opts.pages && path.includes("offset=20")) return json(opts.pages[1]);
        if (opts.pages) return json(opts.pages[0]);
        return json(opts.feed ?? feed);
      }
      if (path === "/api/v1/me/announcements" && request.method === "POST")
        return opts.post ?? json(sentItem("new", null), 201);
      if (request.method === "PATCH") return json(sentItem("a1", null));
      return json(null, 204);
    }),
  );
}

function renderWith(mode: AnnouncementsMode, locale: Locale = "en") {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <L10nProvider locale={locale}>
        <Announcements mode={mode} locale={locale} onBack={vi.fn()} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const box = () => screen.getByRole("textbox");
/** Matches a <p> by its text without Fluent's isolation marks. */
const para = (re: RegExp) => (_: string, el: Element | null) =>
  el?.tagName === "P" && re.test(el.textContent.replace(/[\u2068\u2069]/g, ""));

beforeEach(() => {
  tg.confirmAction.mockResolvedValue(true);
  tg.confirmDestructive.mockResolvedValue(true);
});

describe("compose", () => {
  it("counts the audience and code points, and hints at the date", async () => {
    stubApi();
    renderWith({ view: "compose", shala: null });
    expect(await screen.findByText(para(/To: all your students \(2\)/))).toBeInTheDocument();
    fireEvent.change(box(), { target: { value: "🙏".repeat(1000) } });
    expect(screen.getByText(para(/^1000 \/ 1000$/))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
    fireEvent.change(box(), { target: { value: "a".repeat(1001) } });
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByText(/Name the day and time/)).toBeInTheDocument();
    expect(screen.queryByText(/students and staff/)).not.toBeInTheDocument();
  });

  it("asks first, sends with the pin, then clears", async () => {
    stubApi();
    renderWith({ view: "compose", shala: null });
    await screen.findByText(/To: all your students/);
    fireEvent.change(box(), { target: { value: "Led class Sun 15 Nov, 7:00" } });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("status");
    expect(tg.confirmAction).toHaveBeenCalledWith(
      expect.stringContaining("Send to 2 people?"),
      "Send",
      "Cancel",
    );
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toEqual({ to: "students", text: "Led class Sun 15 Nov, 7:00", pin_days: 7 });
    expect(box()).toHaveValue("");
  });

  it("does nothing when the confirm is cancelled", async () => {
    stubApi();
    tg.confirmAction.mockResolvedValue(false);
    renderWith({ view: "compose", shala: null });
    await screen.findByText(/To: all your students/);
    fireEvent.change(box(), { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => {
      expect(tg.confirmAction).toHaveBeenCalled();
    });
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    expect(box()).toHaveValue("hello");
  });

  it("keeps the text on 409", async () => {
    stubApi({ post: json({ code: "announcement_limit" }, 409) });
    renderWith({ view: "compose", shala: null });
    await screen.findByText(/To: all your students/);
    fireEvent.change(box(), { target: { value: "fourth" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/3 announcements/);
    expect(box()).toHaveValue("fourth");
  });

  it("names the shala and its people for shala staff", async () => {
    stubApi();
    renderWith({ view: "compose", shala: SHALA });
    expect(
      await screen.findByText(para(/To: everyone in Ashtanga Almaty \(6\)/)),
    ).toBeInTheDocument();
    expect(screen.getByText(/students and staff/)).toBeInTheDocument();
    fireEvent.change(box(), { target: { value: "Closed Mon" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("status");
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      to: "shala",
      shala_id: SHALA,
      text: "Closed Mon",
      pin_days: 0,
    });
  });

  it("lists what I sent, with unpin, pin and delete", async () => {
    stubApi({ sent: [sentItem("a1", "2026-11-16T05:00:00Z"), sentItem("a2", null)] });
    renderWith({ view: "compose", shala: null });
    const list = await screen.findByRole("list");
    expect(within(list).getAllByText(para(/Sent to 2 people/))).toHaveLength(2);
    fireEvent.click(within(list).getByRole("button", { name: "Unpin" }));
    await waitFor(() => {
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ pin_days: 0 });
    });
    fireEvent.click(within(list).getByRole("button", { name: "📌 1 week" }));
    const [first] = within(list).getAllByRole("button", { name: "🗑 Delete" });
    if (first) fireEvent.click(first);
    await waitFor(() => {
      expect(calls.some((c) => c.method === "DELETE")).toBe(true);
    });
    expect(tg.confirmDestructive).toHaveBeenCalledWith(
      expect.stringContaining("already delivered stay"),
      "🗑 Delete",
      "Cancel",
    );
  });
});

describe("feed", () => {
  it("shows pins first, filters by source and switches mutes", async () => {
    stubApi();
    renderWith({ view: "feed", shala: null });
    const items = await screen.findAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Closed 1-20 August");
    expect(items[0]).toHaveTextContent(/📌 until/);
    expect(items[1]).toHaveTextContent("No Mysore Mon 10 Nov");
    fireEvent.click(screen.getByRole("button", { name: "Anna" }));
    await waitFor(() => {
      expect(screen.getAllByRole("listitem")).toHaveLength(1);
    });
    expect(calls.some((c) => c.path.includes(`kind=teacher&id=${ANNA}`))).toBe(true);
    const switches = screen.getAllByRole("switch");
    expect(switches).toHaveLength(1);
    expect(switches[0]).toBeChecked();
    const [mute] = switches;
    if (mute) fireEvent.click(mute);
    await waitFor(() => {
      expect(calls.find((c) => c.method === "PUT")).toEqual({
        method: "PUT",
        path: `/api/v1/me/announcement-mutes/teacher/${ANNA}`,
        body: { muted: true },
      });
    });
  });

  it("asks for one shala's feed and says when it is empty", async () => {
    stubApi({ feed: { items: [], sources: [feed.sources[1]], more: false } });
    renderWith({ view: "feed", shala: SHALA }, "ru");
    expect(await screen.findByText("За последние 30 дней объявлений нет.")).toBeInTheDocument();
    expect(calls.some((c) => c.path.includes(`kind=shala&id=${SHALA}`))).toBe(true);
    expect(screen.getByRole("switch")).not.toBeChecked();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("pages with More", async () => {
    const item = (id: string) => ({ ...feed.items[1], id, text: `note ${id}` });
    stubApi({
      pages: [
        { items: [item("a")], sources: feed.sources, more: true },
        { items: [item("b")], sources: feed.sources, more: false },
      ],
    });
    renderWith({ view: "feed", shala: null });
    fireEvent.click(await screen.findByRole("button", { name: "Show more" }));
    expect(await screen.findByText("note b")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
  });

  it("lets a manager unpin and delete from the feed", async () => {
    const managed = { ...feed.items[0], can_manage: true };
    stubApi({ feed: { items: [managed, feed.items[1]], sources: feed.sources, more: false } });
    renderWith({ view: "feed", shala: null });
    fireEvent.click(await screen.findByRole("button", { name: "Unpin" }));
    await waitFor(() => {
      expect(calls.find((c) => c.method === "PATCH")?.path).toBe("/api/v1/me/announcements/p1");
    });
    expect(screen.getAllByRole("button", { name: "🗑 Delete" })).toHaveLength(1);
  });
});

it("asks for no shala on a teacher's compose", async () => {
  stubApi();
  renderWith({ view: "compose", shala: null });
  await screen.findByText(para(/To: all your students/));
  expect(calls.some((c) => c.path.startsWith("/api/v1/shalas"))).toBe(false);
});
