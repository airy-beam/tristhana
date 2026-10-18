import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import { L10nProvider } from "../i18n/L10nProvider";
import type { Locale } from "../i18n/negotiate";
import { haptics, useMainButton } from "../telegram";
import { Home } from "./Home";

vi.mock("../telegram", () => ({
  haptics: { impact: vi.fn(), notify: vi.fn() },
  useMainButton: vi.fn(),
  rawInitData: vi.fn(),
}));

function renderHome(
  locale: Locale,
  name: string | null,
  showDetails = true,
  onGreetingLongPress?: () => void,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>{children}</L10nProvider>
    </QueryClientProvider>
  );
  return render(
    <Home
      firstName={name}
      showDetails={showDetails}
      {...(onGreetingLongPress ? { onGreetingLongPress } : {})}
    />,
    { wrapper },
  );
}

/** A fresh Response per call: a body can only be read once. */
function stubFetch(response: (() => Response) | Response | Error) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => {
      if (response instanceof Error) return Promise.reject(response);
      return Promise.resolve(typeof response === "function" ? response() : response.clone());
    }),
  );
}

const healthy = () =>
  new Response(JSON.stringify({ status: "ok", version: "0.1.0", commit: "13dfd1c3dce7" }), {
    headers: { "Content-Type": "application/json" },
  });

// Fluent isolates placeables with invisible bidi marks (safe for mixed-script names).
const visible = (el: HTMLElement) => el.textContent.replace(/[\u2068\u2069]/g, "");

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Home", () => {
  it("greets the user by first name (ru)", () => {
    stubFetch(healthy);
    renderHome("ru", "Аня");
    expect(visible(screen.getByRole("heading"))).toBe("Намасте, Аня 🙏");
  });

  it("greets without a name (en)", () => {
    stubFetch(healthy);
    renderHome("en", null);
    expect(visible(screen.getByRole("heading"))).toBe("Namaste 🙏");
  });

  it("shows the backend version and short commit", async () => {
    stubFetch(healthy);
    renderHome("en", "Ash");
    const status = await screen.findByRole("status");
    await vi.waitFor(() => {
      expect(visible(status)).toBe("Server 0.1.0 · 13dfd1c");
    });
  });

  it("hides server details unless asked", async () => {
    stubFetch(healthy);
    renderHome("en", "Ash", false);
    expect(await screen.findByRole("heading")).toBeInTheDocument();
    expect(screen.queryByText(/0\.1\.0/)).not.toBeInTheDocument();
  });

  it("shows a calm offline message when the server can't be reached", async () => {
    stubFetch(new TypeError("Failed to fetch"));
    renderHome("en", "Ash");
    expect(await screen.findByText(/can't reach the server/i)).toBeInTheDocument();
  });

  it("shows the offline message on a server error", async () => {
    stubFetch(new Response("unavailable", { status: 503 }));
    renderHome("en", "Ash");
    expect(await screen.findByText(/can't reach the server/i)).toBeInTheDocument();
  });

  it("the main button refetches health with haptic feedback", async () => {
    stubFetch(healthy);
    renderHome("en", "Ash");
    await screen.findByText(/Server/);
    const [text, onClick] = vi.mocked(useMainButton).mock.lastCall ?? [];
    expect(text).toBe("Check connection");

    await act(async () => {
      onClick?.();
      await Promise.resolve();
    });

    expect(haptics.impact).toHaveBeenCalledWith("light");
    await vi.waitFor(() => {
      expect(haptics.notify).toHaveBeenCalledWith("success");
    });
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2);
  });

  it("shows the check result even when server details are hidden", async () => {
    stubFetch(healthy);
    renderHome("ru", "Аня", false);
    await vi.waitFor(() => {
      expect(vi.mocked(fetch)).toHaveBeenCalledOnce();
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    const onClick = vi.mocked(useMainButton).mock.lastCall?.[1];

    act(() => {
      onClick?.();
    });

    expect(await screen.findByText(/Связь в порядке/)).toBeInTheDocument();
    // The main button showed its loader while checking, and is enabled again afterwards.
    const loadingFlags = vi.mocked(useMainButton).mock.calls.map((call) => call[2]);
    expect(loadingFlags).toContain(true);
    expect(vi.mocked(useMainButton).mock.lastCall?.[2]).toBe(false);
  });

  it("a long press on the greeting reveals details; a scroll cancels it", () => {
    vi.useFakeTimers();
    stubFetch(healthy);
    const onLongPress = vi.fn();
    renderHome("en", "Ash", false, onLongPress);
    const heading = screen.getByRole("heading");

    fireEvent.pointerDown(heading);
    fireEvent.pointerCancel(heading);
    vi.advanceTimersByTime(1000);
    expect(onLongPress).not.toHaveBeenCalled();

    fireEvent.pointerDown(heading);
    vi.advanceTimersByTime(1000);
    expect(onLongPress).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });
});
