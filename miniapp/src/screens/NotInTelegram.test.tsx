import { render, screen } from "@testing-library/react";

import { L10nProvider } from "../i18n/L10nProvider";
import { NotInTelegram } from "./NotInTelegram";

it("points to the bot when opened outside Telegram", () => {
  render(
    <L10nProvider locale="ru">
      <NotInTelegram />
    </L10nProvider>,
  );
  expect(screen.getByText(/@tristhana_bot/)).toBeInTheDocument();
});
