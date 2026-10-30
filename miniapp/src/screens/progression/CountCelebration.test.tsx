import { render, screen } from "@testing-library/react";

import { L10nProvider } from "../../i18n/L10nProvider";
import { CountCelebration } from "./CountCelebration";

const count = (n: number) => ({
  kind: "practice_count" as const,
  series: null,
  key: null,
  first: null,
  count: n,
});

const visible = (el: HTMLElement) => el.textContent.replace(/[⁨⁩]/g, "");

describe("CountCelebration (GM-01 part 2)", () => {
  it.each([
    [100, "🎉 100 практик в журнале. Спасибо, что приходишь на коврик."],
    [101, "🎉 101 практика в журнале. Спасибо, что приходишь на коврик."],
    [102, "🎉 102 практики в журнале. Спасибо, что приходишь на коврик."],
    [365, "🎉 365 практик в журнале. Спасибо, что приходишь на коврик."],
  ])("uses Russian plurals for %i", (n, text) => {
    render(
      <L10nProvider locale="ru">
        <CountCelebration found={[count(n)]} onDismiss={() => undefined} />
      </L10nProvider>,
    );

    expect(visible(screen.getByRole("status"))).toBe(text);
  });

  it("groups 1000 like the bot (Babel and Intl agree)", () => {
    render(
      <L10nProvider locale="ru">
        <CountCelebration found={[count(1000)]} onDismiss={() => undefined} />
      </L10nProvider>,
    );

    // The bot renders "1 000" with U+00A0 (Babel, CLDR ru); Intl may use U+00A0 or U+202F.
    expect(visible(screen.getByRole("status"))).toMatch(/^🎉 1[\u00a0\u202f]000 практик/);
  });

  it("renders nothing for other kinds", () => {
    const { container } = render(
      <L10nProvider locale="en">
        <CountCelebration
          found={[{ kind: "item", series: null, key: "drop-backs", first: null, count: null }]}
          onDismiss={() => undefined}
        />
      </L10nProvider>,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
