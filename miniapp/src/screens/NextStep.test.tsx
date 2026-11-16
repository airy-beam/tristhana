import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import type { NextStep as Step } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import type { Locale } from "../i18n/negotiate";
import { NextStep } from "./NextStep";

// UI-06 stage 2 (spec §6): one suggestion at a time from GET /me/next-steps, the first the
// person has not put off on this device. "Not now" never reaches the server (Q333).

vi.mock("../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn(), selection: vi.fn() },
}));

const SHALA = "11111111-1111-4111-8111-111111111111";
const step = (kind: Step["kind"], shala_id: string | null = null): Step => ({ kind, shala_id });

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

/** `steps`: the server's list; a number: that status; "never": no answer. */
function stubApi(steps: Step[] | number | "never"): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      seen.push(request);
      if (steps === "never") return new Promise<Response>(() => undefined);
      if (typeof steps === "number") return Promise.resolve(json({ detail: "Not Found" }, steps));
      return Promise.resolve(json({ steps }));
    }),
  );
  return seen;
}

function renderStep(onOpen: (step: Step) => void = () => undefined, locale: Locale = "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <NextStep onOpen={onOpen} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const answered = (seen: Request[]) =>
  vi.waitFor(() => {
    expect(seen.length).toBeGreaterThan(0);
  });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("NextStep", () => {
  it("shows the first step only: one sentence, one button, a quiet Not now", async () => {
    const seen = stubApi([step("reminder"), step("position")]);
    renderStep();

    expect(
      await screen.findByText("🔔 Want me to ask once a day, so logging takes one tap?"),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Set the reminder",
      "Not now",
    ]);
    expect(screen.queryByText(/Where does your practice end/)).not.toBeInTheDocument();
    expect(new URL(seen[0]?.url ?? "").pathname).toBe("/api/v1/me/next-steps");
  });

  it("shows nothing when the server offers nothing", async () => {
    const seen = stubApi([]);
    const { container } = renderStep();

    await answered(seen);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows nothing while loading", () => {
    stubApi("never");
    const { container } = renderStep();

    expect(container).toBeEmptyDOMElement();
  });

  it("shows nothing against an API older than this bundle (404), and asks once", async () => {
    const seen = stubApi(404);
    const { container } = renderStep();

    await answered(seen);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(container).toBeEmptyDOMElement();
    expect(seen).toHaveLength(1); // no retry
  });

  it("skips a step this bundle does not know and shows the next", async () => {
    stubApi([step("something_new" as Step["kind"]), step("position")]);
    renderStep();

    expect(await screen.findByRole("button", { name: "Open My asanas" })).toBeInTheDocument();
  });

  it.each([
    ["reminder", null, "Set the reminder"],
    ["position", null, "Open My asanas"],
    ["invite_student", null, "Open the invite"],
    ["add_class", SHALA, "Add a class"],
    ["invite_shala_students", SHALA, "Invite students"],
  ] as const)("%s: its button hands the step to the shell", async (kind, shala, label) => {
    stubApi([step(kind, shala)]);
    const onOpen = vi.fn();
    renderStep(onOpen);

    fireEvent.click(await screen.findByRole("button", { name: label }));

    expect(onOpen).toHaveBeenCalledExactlyOnceWith({ kind, shala_id: shala });
  });

  it("Not now hides that step on this device and shows the next", async () => {
    const steps = [step("reminder"), step("position")];
    const seen = stubApi(steps);
    const { unmount } = renderStep();

    fireEvent.click(await screen.findByRole("button", { name: "Not now" }));

    expect(screen.queryByRole("button", { name: "Set the reminder" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open My asanas" })).toBeInTheDocument();
    // Nothing is sent: the server still offers it, the device remembers.
    expect(seen.every((r) => r.method === "GET")).toBe(true);
    unmount();

    stubApi(steps);
    renderStep();
    expect(await screen.findByRole("button", { name: "Open My asanas" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Set the reminder" })).not.toBeInTheDocument();
  });

  it("remembers a shala step per shala", async () => {
    const other = "22222222-2222-4222-8222-222222222222";
    stubApi([step("add_class", SHALA), step("add_class", other)]);
    const onOpen = vi.fn();
    renderStep(onOpen);

    fireEvent.click(await screen.findByRole("button", { name: "Not now" }));
    fireEvent.click(screen.getByRole("button", { name: "Add a class" }));

    expect(onOpen).toHaveBeenCalledExactlyOnceWith({ kind: "add_class", shala_id: other });
  });

  it("disappears once the last step is put off", async () => {
    stubApi([step("position")]);
    const { container } = renderStep();

    fireEvent.click(await screen.findByRole("button", { name: "Not now" }));

    expect(container).toBeEmptyDOMElement();
  });

  it("blocked storage counts as Not now: nothing shows, never a nag", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    const seen = stubApi([step("reminder"), step("position")]);
    const { container } = renderStep();

    await answered(seen);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(container).toBeEmptyDOMElement();
  });

  it("is in Russian too", async () => {
    stubApi([step("invite_student")]);
    renderStep(undefined, "ru");

    expect(
      await screen.findByText("Ссылка-приглашение готова. Отправь её первому ученику."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Не сейчас" })).toBeInTheDocument();
  });
});
