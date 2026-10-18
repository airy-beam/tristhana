// Dev only (dynamically imported, so it's not in production bundles): pretend to be inside
// Telegram so the app runs in a normal browser. `?lang=ru` and `?theme=dark` switch the mock.
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

export function mockTelegram(): void {
  const query = new URLSearchParams(window.location.search);
  const user = { id: 1, first_name: "Dev", language_code: query.get("lang") ?? "en" };
  mockTelegramEnv({
    launchParams: {
      tgWebAppThemeParams: query.get("theme") === "dark" ? DARK : LIGHT,
      tgWebAppVersion: "8.0",
      tgWebAppPlatform: "tdesktop",
      tgWebAppData: new URLSearchParams([
        ["user", JSON.stringify(user)],
        ["auth_date", String(Math.floor(Date.now() / 1000))],
        ["hash", "dev"],
        ["signature", "dev"],
      ]),
    },
  });
}
