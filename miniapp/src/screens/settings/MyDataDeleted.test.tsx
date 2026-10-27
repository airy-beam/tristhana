import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";

import { api, isAccountDeleted } from "../../api/client";
import { App } from "../../App";
import { L10nProvider } from "../../i18n/L10nProvider";
import { closeApp, confirmDestructive } from "../../telegram";
import { MyData } from "./MyData";

// ST-09 (spec §6): confirming sends DELETE /me with the confirmation; after the 204 no
// request goes out (any call would create a new empty account), the query cache and local
// storage are cleared, and the app shows only the Done screen, whose Close closes it.
// While the DELETE is in flight no other request goes out either.
// Its own file: the "deleted" flag is module state and stays set.

vi.mock("../../telegram", () => ({
  rawInitData: vi.fn(() => "user=%7B%7D&hash=abc"),
  haptics: { impact: vi.fn(), notify: vi.fn() },
  confirmDestructive: vi.fn(() => Promise.resolve(true)),
  closeApp: vi.fn(),
  markReady: vi.fn(),
  useSettingsButton: vi.fn(),
}));

test("confirm deletes, then nothing else is sent and only Done shows", async () => {
  const seen: Request[] = [];
  let release: () => void = () => undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      seen.push(request);
      return new Promise<Response>((r) => {
        release = () => {
          r(new Response(null, { status: 204 }));
        };
      });
    }),
  );
  localStorage.setItem("tristhana.showLadies", "1");
  const client = new QueryClient();
  client.setQueryData(["me"], { id: "x" });
  render(
    <QueryClientProvider client={client}>
      <L10nProvider locale="en">
        <MyData />
      </L10nProvider>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Delete my account…" }));

  fireEvent.click(screen.getByRole("button", { name: "Delete everything" }));

  await vi.waitFor(() => {
    expect(seen).toHaveLength(1);
  });
  await expect(api.PATCH("/api/v1/me", { body: {} })).rejects.toThrow("being deleted");
  release();
  await vi.waitFor(() => {
    expect(isAccountDeleted()).toBe(true);
  });
  expect(confirmDestructive).toHaveBeenCalledOnce();
  expect(seen).toHaveLength(1);
  expect(seen[0]?.method).toBe("DELETE");
  expect(await seen[0]?.clone().json()).toEqual({ confirm: "delete-everything" });
  expect(client.getQueryData(["me"])).toBeUndefined();
  expect(localStorage.length).toBe(0);

  await expect(api.GET("/api/v1/me")).rejects.toThrow("account deleted");
  expect(seen).toHaveLength(1);

  render(<App locale="en" firstName="Ash" inTelegram />);
  expect(screen.getByRole("status")).toHaveTextContent("Your account and data are deleted.");
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(closeApp).toHaveBeenCalledOnce();
  expect(seen).toHaveLength(1);
});
