import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import type { NextStep as Step } from "../api/client";
import { L10nProvider } from "../i18n/L10nProvider";
import type { Locale } from "../i18n/negotiate";
import { haptics } from "../telegram";
import { NextStep } from "./NextStep";

// UI-06 stage 2 (spec §6): one suggestion at a time from GET /me/next-steps, the first the
// person has not put off on this device. "Not now" never reaches the server (Q334).

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

const SETTINGS = {
  moon: { offsets: [1, 7], at: "19:00:00" },
  quiet: { start: "22:00:00", end: "07:00:00" },
  daily_cap: 3,
  practice: { on: true, at: "10:00:00", days: [1, 2, 3, 4, 5, 7] },
  timezone: "Asia/Almaty",
};

/** `steps`: the server's list; a number: that status; "never": no answer. The reminder patch
 * answers `patch` (a status: it fails); once it is on, the server no longer offers the step. */
function stubApi(steps: Step[] | number | "never", patch: number = 200): Request[] {
  const seen: Request[] = [];
  let on = false;
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      seen.push(request);
      if (request.method === "PATCH") {
        if (patch !== 200) return Promise.resolve(json({ code: "unavailable" }, patch));
        on = true;
        return Promise.resolve(json(SETTINGS));
      }
      if (Array.isArray(steps) && on)
        return Promise.resolve(json({ steps: steps.filter((s) => s.kind !== "reminder") }));
      if (steps === "never") return new Promise<Response>(() => undefined);
      if (typeof steps === "number") return Promise.resolve(json({ detail: "Not Found" }, steps));
      return Promise.resolve(json({ steps }));
    }),
  );
  return seen;
}

/** `zone`: the account's; unknown by default, as before the device reported one. */
function renderStep(
  onOpen: (step: Step) => void = () => undefined,
  locale: Locale = "en",
  zone: string | null = null,
  place?: string,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <L10nProvider locale={locale}>
        <NextStep zone={zone} place={place} onOpen={onOpen} />
      </L10nProvider>
    </QueryClientProvider>,
  );
}

const visible = (el: HTMLElement) => el.textContent.replace(/[⁨⁩]/g, "");

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
      "Yes, remind me",
      "Not now",
    ]);
    expect(screen.queryByText(/Set where your practice ends/)).not.toBeInTheDocument();
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
    // The sentence promises nothing the app may not do: the choices follow the practice.
    expect(
      screen.getByText(
        "Set where your practice ends, and the length choices will match your practice.",
      ),
    ).toBeInTheDocument();
  });

  it.each([
    ["reminder", null, "Yes, remind me"],
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

  describe("the reminder in one tap", () => {
    const patches = (seen: Request[]) => seen.filter((r) => r.method === "PATCH");

    it("turns the reminder on at the default time and says when, with a quiet way to change it", async () => {
      const seen = stubApi([step("reminder"), step("position")]);
      const onOpen = vi.fn();
      renderStep(onOpen, "en", "Asia/Almaty");

      fireEvent.click(await screen.findByRole("button", { name: "Yes, remind me" }));

      // My own zone: the place, no offset (ADR-0044). The time is the server's answer.
      expect(visible(await screen.findByRole("status"))).toBe(
        "🔔 I'll ask once a day at 10:00 Almaty.",
      );
      expect(haptics.impact).toHaveBeenCalledWith("light");
      expect(patches(seen)).toHaveLength(1);
      expect(new URL(patches(seen)[0]?.url ?? "").pathname).toBe(
        "/api/v1/me/notification-settings",
      );
      // On, and nothing else: the time is the default the server keeps (or one chosen before).
      expect(await patches(seen)[0]?.json()).toEqual({ practice: { on: true } });
      expect(onOpen).not.toHaveBeenCalled();
      expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
        "⏰ Change the time",
      ]);

      fireEvent.click(screen.getByRole("button", { name: "⏰ Change the time" }));

      expect(onOpen).toHaveBeenCalledExactlyOnceWith({ kind: "reminder", shala_id: null });
    });

    it("keeps the confirmation after the server stops offering the step", async () => {
      const seen = stubApi([step("reminder"), step("position")]);
      renderStep(undefined, "en", "Asia/Almaty");
      fireEvent.click(await screen.findByRole("button", { name: "Yes, remind me" }));
      await screen.findByRole("status");

      await vi.waitFor(() => {
        expect(seen.filter((r) => r.method === "GET")).toHaveLength(2); // next-steps, again
      });
      await new Promise((resolve) => setTimeout(resolve, 20));

      expect(screen.getByRole("status")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Open My asanas" })).not.toBeInTheDocument();
    });

    it("names the home city when it is the zone's, in Russian too", async () => {
      stubApi([step("reminder")]);
      renderStep(undefined, "ru", "Asia/Almaty", "Алматы");

      fireEvent.click(await screen.findByRole("button", { name: "Да, напоминай" }));

      expect(visible(await screen.findByRole("status"))).toBe(
        "🔔 Буду спрашивать раз в день в 10:00 Алматы.",
      );
      expect(screen.getByRole("button", { name: "⏰ Изменить время" })).toBeInTheDocument();
    });

    it("with no zone yet, opens the reminder setting and saves nothing", async () => {
      const seen = stubApi([step("reminder")]);
      const onOpen = vi.fn();
      renderStep(onOpen);

      fireEvent.click(await screen.findByRole("button", { name: "Yes, remind me" }));

      expect(onOpen).toHaveBeenCalledExactlyOnceWith({ kind: "reminder", shala_id: null });
      expect(patches(seen)).toHaveLength(0);
    });

    it("a failed save says so and keeps the step", async () => {
      stubApi([step("reminder")], 503);
      renderStep(undefined, "en", "Asia/Almaty");

      fireEvent.click(await screen.findByRole("button", { name: "Yes, remind me" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Couldn't save. Try again in a moment.",
      );
      expect(haptics.notify).toHaveBeenCalledWith("error");
      expect(screen.getByRole("button", { name: "Yes, remind me" })).toBeEnabled();
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  it("Not now hides that step on this device and shows the next", async () => {
    const steps = [step("reminder"), step("position")];
    const seen = stubApi(steps);
    const { unmount } = renderStep();

    fireEvent.click(await screen.findByRole("button", { name: "Not now" }));

    expect(screen.queryByRole("button", { name: "Yes, remind me" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open My asanas" })).toBeInTheDocument();
    // Nothing is sent: the server still offers it, the device remembers.
    expect(seen.every((r) => r.method === "GET")).toBe(true);
    unmount();

    stubApi(steps);
    renderStep();
    expect(await screen.findByRole("button", { name: "Open My asanas" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yes, remind me" })).not.toBeInTheDocument();
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
      await screen.findByText(
        "Ссылка-приглашение готова. Отправь её ученикам, и ты увидишь то, чем они с тобой делятся.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Не сейчас" })).toBeInTheDocument();
  });

  it("the position step in Russian", async () => {
    stubApi([step("position")]);
    renderStep(undefined, "ru");

    expect(
      await screen.findByText(
        "Укажи, где заканчивается твоя практика, и варианты объёма подстроятся под тебя.",
      ),
    ).toBeInTheDocument();
  });
});
