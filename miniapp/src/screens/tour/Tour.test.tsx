import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ComponentType } from "react";

import { L10nProvider } from "../../i18n/L10nProvider";
import enApp from "../../locales/en/app.ftl?raw";
import ruApp from "../../locales/ru/app.ftl?raw";
import { useBackButton } from "../../telegram";
import Tour, { type TourProps } from "./Tour";
import { useTour } from "./useTour";

// UI-02: five steps on Home; absent targets drop out; nothing behind can be tapped.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  useBackButton: vi.fn(),
}));

const scrollIntoView = vi.fn();
let reducedMotion = false;

function page(targets: string[]) {
  const root = document.createElement("div");
  root.id = "root";
  root.innerHTML =
    "<h1>Namaste</h1>" + targets.map((t) => `<section data-tour="${t}"></section>`).join("");
  document.body.append(root);
  return root;
}

function renderTour(onExit: () => void = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale="en">
        <Tour onExit={onExit} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const ALL = ["today", "stats", "asanas", "moon", "settings"];
const next = () => {
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
};
const progress = async (text: string) => {
  await waitFor(() => {
    const shown = document.getElementById("tour-progress")?.textContent;
    expect(shown?.replace(/[⁨⁩]/g, "")).toBe(text);
  });
};

beforeEach(() => {
  reducedMotion = false;
  scrollIntoView.mockClear();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
      ),
    ),
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe = vi.fn();
      disconnect = vi.fn();
    },
  );
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("matchMedia", () => ({ matches: reducedMotion }));
  Element.prototype.scrollIntoView = scrollIntoView;
});

afterEach(() => {
  document.getElementById("root")?.remove();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

test("walks all five steps forward and back", async () => {
  page(ALL);
  renderTour();
  await progress("1 of 5");
  expect(screen.queryByRole("button", { name: "Previous step" })).not.toBeInTheDocument();

  for (const n of [2, 3, 4, 5]) {
    next();
    await progress(`${String(n)} of 5`);
  }
  expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Previous step" }));
  await progress("4 of 5");
});

test("a step with no target drops out, and the count stays honest", async () => {
  page(["today", "stats", "asanas", "settings"]);
  renderTour();

  await progress("1 of 4");
});

test("a target lost mid-tour keeps its text, with no spotlight", async () => {
  const root = page(ALL);
  renderTour();
  await progress("1 of 5");
  await waitFor(() => {
    expect(document.querySelector(".tour-spot")).toBeInTheDocument();
  });
  root.querySelector('[data-tour="stats"]')?.remove();

  next();

  await progress("2 of 5");
  await waitFor(() => {
    expect(document.querySelector(".tour-spot")).not.toBeInTheDocument();
  });
});

test("no targets at all: leaves quietly", async () => {
  page([]);
  const onExit = vi.fn();
  renderTour(onExit);

  await waitFor(() => {
    expect(onExit).toHaveBeenCalledOnce();
  });
});

test("Back, Esc and Done all leave", async () => {
  page(ALL);
  const onExit = vi.fn();
  renderTour(onExit);
  await progress("1 of 5");

  expect(useBackButton).toHaveBeenCalledWith(onExit);
  fireEvent.keyDown(document, { key: "Escape" });
  fireEvent.click(screen.getByRole("button", { name: "Done" }));

  expect(onExit).toHaveBeenCalledTimes(2);
});

test("arrow keys change the step and stop at the ends", async () => {
  page(ALL);
  renderTour();
  await progress("1 of 5");

  fireEvent.keyDown(document, { key: "ArrowLeft" });
  await progress("1 of 5");
  fireEvent.keyDown(document, { key: "ArrowRight" });
  await progress("2 of 5");
});

test("the page behind is inert, then focus and scroll come back", async () => {
  const root = page(ALL);
  const { unmount } = renderTour();
  await progress("1 of 5");
  expect(root).toHaveAttribute("inert");
  expect(document.getElementById("tour-text")).toHaveFocus();

  unmount();

  expect(root).not.toHaveAttribute("inert");
  expect(vi.mocked(scrollTo)).toHaveBeenCalledWith({ top: 0 });
  expect(root.querySelector("h1")).toHaveFocus();
});

test("Tab stays inside the sheet", async () => {
  page(ALL);
  renderTour();
  await progress("1 of 5");
  // The step moves focus to its text in an effect: let it land first, or it can take focus
  // from "Done" mid-test on a slow runner (a CI flake).
  await waitFor(() => {
    expect(document.getElementById("tour-text")).toHaveFocus();
  });
  const done = screen.getByRole("button", { name: "Done" });
  done.focus();

  fireEvent.keyDown(document, { key: "Tab" });

  expect(screen.getByRole("button", { name: "Next" })).toHaveFocus();
  fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
  expect(done).toHaveFocus();
});

test("the sheet moves to the top only after scrolling stops, using the visible height", async () => {
  const root = page(ALL);
  document.documentElement.style.setProperty("--tg-viewport-stable-height", "400px");
  vi.spyOn(
    root.querySelector('[data-tour="today"]') as Element,
    "getBoundingClientRect",
  ).mockReturnValue({ top: 380, left: 0, width: 300, height: 100 } as DOMRect);
  renderTour();
  await progress("1 of 5");
  const sheet = document.querySelector(".tour-sheet");

  expect(sheet).not.toHaveClass("top");
  await waitFor(() => {
    expect(sheet).toHaveClass("top");
  });
  document.documentElement.style.removeProperty("--tg-viewport-stable-height");
});

test("reduced motion scrolls at once", async () => {
  reducedMotion = true;
  page(ALL);
  renderTour();
  await progress("1 of 5");

  expect(scrollIntoView).toHaveBeenCalledWith({ block: "start", behavior: "auto" });
});

test("the tour text never names the ladies' holiday and stays gentle", () => {
  for (const source of [enApp, ruApp]) {
    const section = source.slice(source.indexOf("(UI-02)")).split("\n").slice(1).join("\n");
    expect(section).toContain("tour-settings");
    expect(section).not.toMatch(
      /🌸|ladies|женск|streak|missed|skipped|серия|faster|только|\bonly\b/i,
    );
  }
});

describe("useTour", () => {
  const Chunk: ComponentType<TourProps> = () => null;

  test("a chunk that fails to load leaves nothing open", async () => {
    const { result } = renderHook(() => useTour(() => Promise.reject(new Error("offline"))));

    await act(async () => {
      result.current.start();
      await Promise.resolve();
    });

    expect(result.current.Tour).toBeNull();
  });

  test("closing while it loads doesn't open it afterwards", async () => {
    let finish: (chunk: { default: ComponentType<TourProps> }) => void = () => undefined;
    const load = () =>
      new Promise<{ default: ComponentType<TourProps> }>((resolve) => {
        finish = resolve;
      });
    const { result } = renderHook(() => useTour(load));

    act(() => {
      result.current.start();
      result.current.close();
    });
    await act(async () => {
      finish({ default: Chunk });
      await Promise.resolve();
    });

    expect(result.current.Tour).toBeNull();
  });

  test("opens once loaded", async () => {
    const { result } = renderHook(() => useTour(() => Promise.resolve({ default: Chunk })));

    await act(async () => {
      result.current.start();
      await Promise.resolve();
    });

    expect(result.current.Tour).toBe(Chunk);
  });
});
