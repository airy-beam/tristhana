import { fireEvent, render, screen } from "@testing-library/react";
import { Suspense } from "react";

import { L10nProvider } from "../i18n/L10nProvider";
import { ChunkBoundary } from "./ChunkBoundary";
import { lazyRetry } from "./lazyRetry";

// UI-06 stage 2 (ADR-0047): a lazy screen whose chunk fails to load says so and can be tried
// again. `React.lazy` alone keeps the failure for good, so the retry needs `lazyRetry`.

const backButton = vi.hoisted(() => ({ available: true }));

vi.mock("../telegram", () => ({
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
  backButtonAvailable: () => backButton.available,
}));

const FAILED = "Couldn't load this. Check your connection and try again.";

function Screen({ title }: { title: string }) {
  return <h1>{title}</h1>;
}

/** A chunk whose first `failures` loads fail, as on a weak connection. */
function flaky(failures: number) {
  const load = vi.fn(() =>
    load.mock.calls.length <= failures
      ? Promise.reject(new Error("Failed to fetch dynamically imported module"))
      : Promise.resolve({ default: Screen }),
  );
  return load;
}

function renderWith(node: React.ReactNode) {
  return render(
    <L10nProvider locale="en">
      <Suspense fallback={<main aria-busy="true" />}>{node}</Suspense>
    </L10nProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined); // React reports what it caught
});

afterEach(() => {
  vi.restoreAllMocks();
  backButton.available = true;
});

test("a chunk that loads renders as with React.lazy, and is loaded once", async () => {
  const load = flaky(0);
  const Lazy = lazyRetry(load);
  const { rerender } = renderWith(
    <ChunkBoundary>
      <Lazy title="My practice" />
    </ChunkBoundary>,
  );

  expect(await screen.findByRole("heading", { name: "My practice" })).toBeInTheDocument();
  rerender(
    <L10nProvider locale="en">
      <Suspense fallback={null}>
        <ChunkBoundary>
          <Lazy title="Again" />
        </ChunkBoundary>
      </Suspense>
    </L10nProvider>,
  );

  expect(await screen.findByRole("heading", { name: "Again" })).toBeInTheDocument();
  expect(load).toHaveBeenCalledOnce();
});

test("a failed chunk says so, and Try again loads it", async () => {
  const load = flaky(1);
  const Lazy = lazyRetry(load);
  renderWith(
    <ChunkBoundary>
      <Lazy title="My practice" />
    </ChunkBoundary>,
  );

  expect(await screen.findByRole("alert")).toHaveTextContent(FAILED);
  expect(screen.queryByRole("heading")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));

  expect(await screen.findByRole("heading", { name: "My practice" })).toBeInTheDocument();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(load).toHaveBeenCalledTimes(2);
});

test("still failing: the line stays, and each tap is one more try", async () => {
  const load = flaky(2);
  const Lazy = lazyRetry(load);
  renderWith(
    <ChunkBoundary>
      <Lazy title="My practice" />
    </ChunkBoundary>,
  );
  await screen.findByRole("alert");

  fireEvent.click(screen.getByRole("button", { name: "Try again" }));

  await vi.waitFor(() => {
    expect(load).toHaveBeenCalledTimes(2);
  });
  expect(await screen.findByRole("alert")).toHaveTextContent(FAILED);
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("heading", { name: "My practice" })).toBeInTheDocument();
});

test("a pushed screen keeps a way back where Telegram has no Back button", async () => {
  backButton.available = false;
  const onBack = vi.fn();
  const Lazy = lazyRetry(flaky(1));
  renderWith(
    <ChunkBoundary onBack={onBack}>
      <Lazy title="Settings" />
    </ChunkBoundary>,
  );
  await screen.findByRole("alert");

  fireEvent.click(screen.getByRole("button", { name: "‹ Back" }));

  expect(onBack).toHaveBeenCalledOnce();
});

test("a root has no back link, and neither has a screen with Telegram's Back", async () => {
  backButton.available = false;
  const Root = lazyRetry(flaky(1));
  const { unmount } = renderWith(
    <ChunkBoundary>
      <Root title="My practice" />
    </ChunkBoundary>,
  );
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "‹ Back" })).toBeNull();
  unmount();

  backButton.available = true;
  const Pushed = lazyRetry(flaky(1));
  renderWith(
    <ChunkBoundary onBack={vi.fn()}>
      <Pushed title="Settings" />
    </ChunkBoundary>,
  );
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "‹ Back" })).toBeNull();
});

// `React.lazy` keeps a failed load for good, so under it "Try again" could never work: every
// lazy piece of the app, also one inside a screen, goes through `lazyRetry`.
test("no source file but lazyRetry.ts uses React.lazy", () => {
  const sources = import.meta.glob<string>("../**/*.{ts,tsx}", {
    query: "?raw",
    import: "default",
    eager: true,
  });
  const plain = Object.entries(sources)
    .filter(([path]) => !/\.test\.tsx?$/.test(path) && !path.endsWith("/lazyRetry.ts"))
    .filter(([, source]) => /\blazy\(/.test(source))
    .map(([path]) => path);

  expect(Object.keys(sources).length).toBeGreaterThan(50);
  expect(plain).toEqual([]);
});
