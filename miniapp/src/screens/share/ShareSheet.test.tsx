import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { ShareSubject } from "../../api/client";
import { L10nProvider } from "../../i18n/L10nProvider";
import type { Locale } from "../../i18n/negotiate";
import { allowBotMessages } from "../../telegram";
import {
  canDownload,
  canShareStory,
  isPremium,
  saveImage,
  shareToStory,
} from "../../telegram/share";
import ShareSheet from "./ShareSheet";

// ST-07 (spec §3): the sheet asks the server for the card (Story by default where the story
// editor exists, else Square), previews the image URL, and shows only the actions the client
// supports: Share to story (story format only), Save image, Send to my chat (always; asks for
// write access on 409 like the export). Errors: rate limit, failure. The privacy note.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  allowBotMessages: vi.fn(() => Promise.resolve(false)),
  useBackButton: vi.fn(),
}));

vi.mock("../../telegram/share", () => ({
  canShareStory: vi.fn(() => true),
  canDownload: vi.fn(() => true),
  isPremium: vi.fn(() => false),
  shareToStory: vi.fn(),
  saveImage: vi.fn(() => Promise.resolve(true)),
}));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const card = (format: "story" | "square") => ({
  id: `tok-${format}`,
  image_url: `https://api.test/share/v1/tok-${format}.png`,
  width: 1080,
  height: format === "story" ? 1920 : 1080,
  file_name: `tristhana-2026-10-${format}.png`,
  expires_at: "2026-11-10T03:00:00Z",
});

function stubApi(answer: (request: Request) => Response | Promise<Response>): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      seen.push(request.clone());
      return answer(request);
    }),
  );
  return seen;
}

const cards = async (request: Request) => {
  if (request.url.endsWith("/send")) return json({ sent: true });
  const body = (await request.json()) as { format: "story" | "square" };
  return json(card(body.format), 201);
};

const MONTH: ShareSubject = { kind: "month", year: 2026, month: 10 };

function renderSheet(locale: Locale = "en", onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <ShareSheet subject={MONTH} onClose={onClose} />
      </L10nProvider>
    </QueryClientProvider>,
  );
  return onClose;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(canShareStory).mockReturnValue(true);
  vi.mocked(canDownload).mockReturnValue(true);
  vi.mocked(isPremium).mockReturnValue(false);
  vi.mocked(shareToStory).mockClear();
  vi.mocked(saveImage).mockClear();
  vi.mocked(allowBotMessages).mockClear();
});

test("story by default: preview, share to story with the caption, privacy note", async () => {
  const seen = stubApi(cards);
  renderSheet();
  const img = await screen.findByRole("img", { name: "Card preview" });
  expect(img).toHaveAttribute("src", card("story").image_url);
  expect(await seen[0]?.json()).toEqual({ format: "story", card: MONTH });
  expect(screen.getByText(/no name, notes or reasons for rest/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Share to story" }));
  expect(shareToStory).toHaveBeenCalledWith(
    card("story").image_url,
    "My practice · @tristhana_bot",
  );
});

test("square format hides Share to story; switching back reuses the cached card", async () => {
  const seen = stubApi(cards);
  renderSheet();
  await screen.findByRole("img");
  fireEvent.click(screen.getByRole("button", { name: "Square" }));
  await waitFor(() => {
    expect(screen.getByRole("img")).toHaveAttribute("src", card("square").image_url);
  });
  expect(screen.queryByRole("button", { name: "Share to story" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Story" }));
  await waitFor(() => {
    expect(screen.getByRole("img")).toHaveAttribute("src", card("story").image_url);
  });
  expect(seen).toHaveLength(2);
});

test("no story editor (desktop): square by default, no story button", async () => {
  vi.mocked(canShareStory).mockReturnValue(false);
  vi.mocked(canDownload).mockReturnValue(false);
  const seen = stubApi(cards);
  renderSheet();
  await screen.findByRole("img");
  expect(await seen[0]?.json()).toEqual({ format: "square", card: MONTH });
  expect(screen.queryByRole("button", { name: "Share to story" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Save image" })).toBeNull();
  expect(screen.getByRole("button", { name: "Send to my chat" })).toBeEnabled();
});

test("save image uses the file name", async () => {
  stubApi(cards);
  renderSheet();
  fireEvent.click(await screen.findByRole("button", { name: "Save image" }));
  expect(saveImage).toHaveBeenCalledWith(card("story").image_url, "tristhana-2026-10-story.png");
  expect(await screen.findByRole("button", { name: "✓ Saved" })).toBeInTheDocument();
});

test("send to my chat once", async () => {
  const seen = stubApi(cards);
  renderSheet("ru");
  fireEvent.click(await screen.findByRole("button", { name: "Прислать в чат" }));
  const done = await screen.findByRole("button", { name: "✓ Отправлено в чат" });
  expect(done).toBeDisabled();
  expect(seen.at(-1)?.url).toMatch(/\/api\/v1\/me\/share-cards\/tok-story\/send$/);
});

test("send asks for write access when the bot can't write yet", async () => {
  stubApi(async (request) =>
    request.url.endsWith("/send") ? json({ code: "bot_unreachable" }, 409) : cards(request),
  );
  renderSheet();
  fireEvent.click(await screen.findByRole("button", { name: "Send to my chat" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Open @tristhana_bot");
  expect(allowBotMessages).toHaveBeenCalled();
});

test("rate limit and failure messages", async () => {
  stubApi(() => json({ code: "rate_limited" }, 429));
  renderSheet();
  expect(await screen.findByRole("alert")).toHaveTextContent("Try again tomorrow");
  expect(screen.queryByRole("button", { name: "Send to my chat" })).toBeNull();
});

test("closing: ✕ and the backdrop", async () => {
  stubApi(cards);
  const onClose = renderSheet();
  await screen.findByRole("img");
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  fireEvent.click(screen.getByRole("dialog"));
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("switching format after a send offers Send again: it's another card", async () => {
  stubApi(cards);
  renderSheet();
  fireEvent.click(await screen.findByRole("button", { name: "Send to my chat" }));
  await screen.findByRole("button", { name: "✓ Sent to your chat" });
  fireEvent.click(screen.getByRole("button", { name: "Square" }));
  expect(await screen.findByRole("button", { name: "Send to my chat" })).toBeEnabled();
});

test("already sent (reopened) reads as sent, not as a failure", async () => {
  stubApi((request) =>
    request.url.endsWith("/send") ? json({ code: "already_sent" }, 409) : cards(request),
  );
  renderSheet();
  fireEvent.click(await screen.findByRole("button", { name: "Send to my chat" }));
  expect(await screen.findByRole("button", { name: "✓ Sent to your chat" })).toBeDisabled();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("a modal: focus moves to the title, Escape closes", () => {
  stubApi(cards);
  const onClose = renderSheet();
  expect(screen.getByRole("heading", { name: "Share a card" })).toHaveFocus();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalledOnce();
});
