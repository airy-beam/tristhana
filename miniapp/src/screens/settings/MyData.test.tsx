import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import { allowBotMessages, confirmDestructive } from "../../telegram";
import { MyData } from "./MyData";

// ST-09 (spec §6): Download asks the API to have the bot send the file (busy → sent), 429
// says when again (from `retry_after_s`), 409 says to open the bot; "Delete my account…"
// explains first, and the native confirm's Cancel sends nothing. The delete itself and what
// follows (no more requests, cache and storage cleared, Close) are in MyDataDeleted.test.tsx.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
  confirmDestructive: vi.fn(() => Promise.resolve(false)),
  allowBotMessages: vi.fn(() => Promise.resolve(false)),
  closeApp: vi.fn(),
}));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stubApi(answer: () => Response | Promise<Response>): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request);
      return answer();
    }),
  );
  return seen;
}

function renderCard(locale: Locale = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <MyData />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const SENT = {
  file_name: "tristhana-export-2026-10-27.zip",
  bytes: 2048,
  sent_at: "2026-10-27T09:00:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(confirmDestructive).mockClear();
  vi.mocked(allowBotMessages).mockClear();
});

test("download is busy, then says it went to the chat", async () => {
  let release: (r: Response) => void = () => undefined;
  const seen = stubApi(() => new Promise<Response>((r) => (release = r)));
  renderCard();

  fireEvent.click(screen.getByRole("button", { name: "⬇️ Download my data" }));

  const busy = await screen.findByRole("button", { name: "Sending…" });
  expect(busy).toBeDisabled();
  release(json(SENT));
  expect(await screen.findByRole("status")).toHaveTextContent("Sent to your chat with the bot.");
  expect(seen).toHaveLength(1);
  expect(seen[0]?.method).toBe("POST");
  expect(new URL(seen[0]?.url ?? "").pathname).toBe("/api/v1/me/exports");
});

test("too soon says when, from the server's wait", async () => {
  stubApi(() => json({ code: "export_too_soon", retry_after_s: 400 }, 429));
  renderCard();

  fireEvent.click(screen.getByRole("button", { name: "⬇️ Download my data" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/Again in \u20687\u2069 min\./);
});

test("an unreachable bot asks Telegram for write access, then says to open the bot", async () => {
  const seen = stubApi(() => json({ code: "bot_unreachable" }, 409));
  renderCard();

  fireEvent.click(screen.getByRole("button", { name: "⬇️ Download my data" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Open the bot, tap Start");
  expect(allowBotMessages).toHaveBeenCalledOnce();
  expect(seen).toHaveLength(1); // not allowed: no second try
});

test("write access allowed: the export is sent once more", async () => {
  vi.mocked(allowBotMessages).mockResolvedValueOnce(true);
  let calls = 0;
  const seen = stubApi(() => (++calls === 1 ? json({ code: "bot_unreachable" }, 409) : json(SENT)));
  renderCard();

  fireEvent.click(screen.getByRole("button", { name: "⬇️ Download my data" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Sent to your chat with the bot.");
  expect(seen).toHaveLength(2);
});

test("delete explains first, in Russian too", () => {
  stubApi(() => json({}));
  renderCard("ru");

  fireEvent.click(screen.getByRole("button", { name: "Удалить аккаунт…" }));

  expect(screen.getByText(/Отменить это нельзя/)).toBeInTheDocument();
  expect(screen.getByText(/в течение 30 дней/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "⬇️ Сначала скачать данные" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Удалить всё" })).toBeInTheDocument();
});

test("cancel in the native confirm sends nothing", async () => {
  const seen = stubApi(() => json({}));
  renderCard();
  fireEvent.click(screen.getByRole("button", { name: "Delete my account…" }));

  fireEvent.click(screen.getByRole("button", { name: "Delete everything" }));

  await vi.waitFor(() => {
    expect(confirmDestructive).toHaveBeenCalledWith(
      "Delete your account and all data? This can't be undone.",
      "Delete everything",
      "Cancel",
    );
  });
  expect(seen).toHaveLength(0);
});
