// Dev only (dynamically imported, so it's not in production bundles): pretend to be inside
// Telegram so the app runs in a normal browser. `?lang=ru` and `?theme=dark` switch the mock;
// `?user=<id>&name=<first name>` picks the dev account (default: user 1, "Dev").
// The initData is signed by the local backend (APP_ENV=dev), so the real auth path runs.
import { mockTelegramEnv } from "@telegram-apps/sdk-react";

const LIGHT = {
  bg_color: "#ffffff",
  text_color: "#000000",
  hint_color: "#707579",
  link_color: "#3390ec",
  button_color: "#3390ec",
  button_text_color: "#ffffff",
  secondary_bg_color: "#f4f4f5",
} as const;
const DARK = {
  bg_color: "#212121",
  text_color: "#ffffff",
  hint_color: "#aaaaaa",
  link_color: "#8774e1",
  button_color: "#8774e1",
  button_text_color: "#ffffff",
  secondary_bg_color: "#181818",
} as const;

export async function mockTelegram(): Promise<void> {
  const query = new URLSearchParams(window.location.search);
  const lang = query.get("lang") ?? "en";
  mockTelegramEnv({
    launchParams: {
      tgWebAppThemeParams: query.get("theme") === "dark" ? DARK : LIGHT,
      tgWebAppVersion: "8.0",
      tgWebAppPlatform: "tdesktop",
      tgWebAppData: await signedInitData(lang, query.get("user"), query.get("name")),
    },
  });
}

/** From the backend's dev-only endpoint; unsigned (API answers 401) if it isn't running. */
async function signedInitData(
  lang: string,
  userId: string | null,
  firstName: string | null,
): Promise<URLSearchParams> {
  // UI-05: `?user=9001&name=Maya` signs in as a seeded demo account (guide screenshots).
  const params = new URLSearchParams({ lang });
  if (userId) params.set("user_id", userId);
  if (firstName) params.set("first_name", firstName);
  try {
    const response = await fetch(`/dev/telegram-init-data?${params.toString()}`);
    if (response.ok) {
      const { init_data } = (await response.json()) as { init_data: string };
      return new URLSearchParams(init_data);
    }
  } catch {
    // backend not running: fall through
  }
  console.warn("dev: backend not reachable, using unsigned initData");
  const user = { id: 1, first_name: "Dev", language_code: lang };
  return new URLSearchParams([
    ["user", JSON.stringify(user)],
    ["auth_date", String(Math.floor(Date.now() / 1000))],
    ["hash", "dev"],
  ]);
}
