import { fireEvent, render, screen } from "@testing-library/react";

import { Row } from "./Row";

// UI-06: the one list row (the day card's entries, the rows under it, the empty Shala tab).
// Its name is the label as the message has it; what was entered is its description, so a
// reader hears "Details", then the summary.

describe("Row", () => {
  it("is a button named by its label, emoji included; a tap calls back", () => {
    const onClick = vi.fn();
    render(<Row label="📝 Add details" onClick={onClick} />);

    const row = screen.getByRole("button", { name: "📝 Add details" });
    expect(row).not.toHaveAttribute("aria-expanded");
    expect(row).not.toHaveAccessibleDescription();
    fireEvent.click(row);

    expect(onClick).toHaveBeenCalledOnce();
  });

  it("sets a leading emoji apart as the icon, and only an emoji", () => {
    const { container, rerender } = render(<Row label="✈️ Travel" onClick={() => undefined} />);
    expect(container.querySelector(".lrow-icon")).toHaveTextContent("✈️");
    expect(container.querySelector(".lrow-title")).toHaveTextContent("Travel");

    rerender(<Row label="Invite students" onClick={() => undefined} />);
    expect(container.querySelector(".lrow-icon")).toBeNull();
    expect(container.querySelector(".lrow-title")).toHaveTextContent("Invite students");
    expect(screen.getByRole("button", { name: "Invite students" })).toBeInTheDocument();
  });

  it("carries the second line as its description, not in its name", () => {
    render(
      <Row label="📝 Details" sub="Mysore · Full Primary · 90 min" onClick={() => undefined} />,
    );

    const row = screen.getByRole("button", { name: "📝 Details" });
    expect(row).toHaveAccessibleDescription("Mysore · Full Primary · 90 min");
  });

  it("says whether its panel is open", () => {
    const { rerender } = render(<Row label="📓 Note" expanded={false} onClick={() => undefined} />);
    expect(screen.getByRole("button", { name: "📓 Note" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    rerender(<Row label="📓 Note" expanded onClick={() => undefined} />);
    expect(screen.getByRole("button", { name: "📓 Note" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
