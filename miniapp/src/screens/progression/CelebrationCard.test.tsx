import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import { L10nProvider } from "../../i18n/L10nProvider";
import { CelebrationCard, shareOf } from "./CelebrationCard";

// ST-07: a celebration offers Share only when it can become a card (a given asana, a
// series, a practice count; never an item), and tapping the text still dismisses it.

vi.mock("../share/ShareSheet", () => ({ default: () => null }));

vi.mock("../../telegram", () => ({
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
}));

function wrap(children: ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <L10nProvider locale="en">{children}</L10nProvider>
    </QueryClientProvider>
  );
}

test("share subjects", () => {
  expect(shareOf([{ kind: "new_asana", series: "primary", key: "x", first: null }], 7)).toEqual({
    kind: "asana",
    event_id: 7,
  });
  expect(
    shareOf([{ kind: "series_begins", series: "intermediate", key: null, first: null }], 8),
  ).toEqual({ kind: "asana", event_id: 8 });
  expect(
    shareOf([{ kind: "practice_count", series: null, key: null, first: null, count: 100 }], null),
  ).toEqual({ kind: "count", count: 100 });
  expect(shareOf([{ kind: "item", series: null, key: "drop-backs", first: null }], 9)).toBeNull();
  expect(shareOf([], 9)).toBeNull();
});

test("dismiss by tapping the text; Share doesn't dismiss", () => {
  const onDismiss = vi.fn();
  render(
    <L10nProvider locale="en">
      <CelebrationCard
        lines={["🎉 New asana"]}
        onDismiss={onDismiss}
        share={{ kind: "count", count: 100 }}
      />
    </L10nProvider>,
  );
  expect(screen.getByRole("status")).toHaveTextContent(/^🎉 New asana$/);
  fireEvent.click(screen.getByRole("button", { name: "Share" }));
  expect(onDismiss).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "🎉 New asana" }));
  expect(onDismiss).toHaveBeenCalledOnce();
});

test("no Share without a subject", () => {
  render(wrap(<CelebrationCard lines={["🎉 Drop-backs"]} onDismiss={vi.fn()} />));
  expect(screen.queryByRole("button", { name: "Share" })).toBeNull();
});
