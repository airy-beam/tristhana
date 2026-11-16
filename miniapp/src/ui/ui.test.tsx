import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";

import { Chips } from "./Chips";
import { Check, DateInput, Field, NumberInput, Select, TextInput, TimeInput } from "./controls";
import { More } from "./More";

// UI-06 stage 4 (spec §7): one set of form controls. Native elements, so the phone's own
// pickers and screen readers keep working; the label, the hint and the error are wired to the
// control; chips say which are pressed; "More options" says whether it is open.

describe("Field", () => {
  it("names its control by the label", () => {
    render(
      <Field label="Name">
        <TextInput defaultValue="Ashtanga Almaty" />
      </Field>,
    );

    const input = screen.getByRole("textbox", { name: "Name" });
    expect(input).toHaveValue("Ashtanga Almaty");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).not.toHaveAttribute("aria-describedby");
  });

  it("wires the hint and the error as the control's description", () => {
    render(
      <Field label="Start" hint="Almaty time" error="Pick a time">
        <TimeInput defaultValue="06:00" />
      </Field>,
    );

    const input = screen.getByLabelText("Start");
    expect(input).toHaveAttribute("type", "time");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Almaty time Pick a time");
    expect(screen.getByRole("alert")).toHaveTextContent("Pick a time");
  });

  it("labels a select and a date field the same way", () => {
    render(
      <>
        <Field label="City">
          <Select defaultValue="almaty">
            <option value="almaty">Almaty</option>
          </Select>
        </Field>
        <Field label="First date">
          <DateInput defaultValue="2026-11-16" />
        </Field>
      </>,
    );

    expect(screen.getByRole("combobox", { name: "City" })).toHaveValue("almaty");
    expect(screen.getByLabelText("First date")).toHaveAttribute("type", "date");
  });
});

describe("NumberInput", () => {
  it("is a number field with the phone's digit keys; its unit is shown, not read twice", () => {
    render(
      <Field label="How many minutes" error="Too long">
        <NumberInput defaultValue="105" min={15} max={480} suffix="min" />
      </Field>,
    );

    const input = screen.getByRole("spinbutton", { name: "How many minutes" });
    expect(input).toHaveValue(105);
    expect(input).toHaveAttribute("inputmode", "numeric");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("min")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("Check", () => {
  it("is a native checkbox named by its label", () => {
    const onChange = vi.fn();
    render(<Check label="🌐 Online" checked={false} onChange={onChange} />);

    fireEvent.click(screen.getByRole("checkbox", { name: "🌐 Online" }));

    expect(onChange).toHaveBeenCalledOnce();
  });
});

describe("Chips", () => {
  const TYPES = [
    { value: "mysore", label: "Mysore" },
    { value: "led", label: "Led" },
  ];

  it("is a named group whose chips say which one is pressed", () => {
    const onPick = vi.fn();
    render(<Chips label="Type" options={TYPES} value="mysore" onPick={onPick} />);

    const group = screen.getByRole("group", { name: "Type" });
    expect(within(group).getByRole("button", { name: "Mysore" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const led = within(group).getByRole("button", { name: "Led" });
    expect(led).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(led);

    expect(onPick).toHaveBeenCalledWith("led");
  });

  it("takes many values, and a chip's full name when its label is short", () => {
    const days = [
      { value: 1, label: "Mon", name: "Monday" },
      { value: 2, label: "Tue", name: "Tuesday" },
      { value: 3, label: "Wed", name: "Wednesday" },
    ];
    render(<Chips label="Repeats on" options={days} value={[1, 3]} onPick={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Monday" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Tuesday" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByRole("button", { name: "Wednesday" })).toHaveTextContent("Wed");
  });

  it("carries its error as the group's description", () => {
    render(
      <Chips label="Repeats on" options={[]} value={[]} onPick={vi.fn()} error="Choose a day" />,
    );

    expect(screen.getByRole("group", { name: "Repeats on" })).toHaveAccessibleDescription(
      "Choose a day",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a day");
  });
});

describe("More", () => {
  function Fold() {
    const [open, setOpen] = useState(false);
    return (
      <More
        label="More options"
        summary="until 09:30 · Anna"
        open={open}
        onToggle={() => {
          setOpen(!open);
        }}
      >
        <p>inside</p>
      </More>
    );
  }

  it("is a button that says whether it is open, and what it controls", () => {
    render(<Fold />);

    const row = screen.getByRole("button", { name: "More options" });
    expect(row).toHaveAttribute("aria-expanded", "false");
    expect(row).toHaveAccessibleDescription("until 09:30 · Anna");
    expect(screen.queryByText("inside")).toBeNull();
    fireEvent.click(row);

    expect(row).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(row.getAttribute("aria-controls") ?? "");
    expect(panel).toContainElement(screen.getByText("inside"));
    // Open, the values are on screen themselves: no summary.
    expect(row).not.toHaveAccessibleDescription();
  });
});
