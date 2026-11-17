import { Localized } from "@fluent/react";
import { useState } from "react";

import type { DayStatus } from "../api/client";
import { haptics } from "../telegram";

/** Behind "Other…", in the order of the backend's `domain/journey.OTHER_REASONS`. */
export const OTHER_REASONS: readonly DayStatus[] = ["moon", "ladies", "sick", "travel", "skipped"];

interface Props {
  /** What the day shows as; null while nothing is logged (auto-rest presses nothing). */
  current: DayStatus | null;
  /** Whether 🌸 is among the reasons ("Hide the 🌸 button", WH-01). */
  ladies: boolean;
  /** The card's heading: the group's accessible name. */
  labelledBy: string;
  /** A tap on a choice, the current one too (the card folds either way). */
  onPick: (status: DayStatus) => void;
}

/** The day's three choices, one per row, as the bot's Today (UI-06): Practiced, Rest day and
 * "Other…", which opens the reasons right here. A reason saves and closes. Shown for a day
 * nothing has answered, and behind "Change" on a logged one. */
export function DayChoice({ current, ladies, labelledBy, onPick }: Props) {
  const [open, setOpen] = useState(false);
  const reason = current !== null && OTHER_REASONS.includes(current);
  const choice = (status: DayStatus) => (
    <Localized key={status} id={`status-${status}`}>
      <button
        type="button"
        className="choice"
        aria-pressed={status === current}
        onClick={() => {
          setOpen(false);
          onPick(status);
        }}
      />
    </Localized>
  );
  return (
    <div className="choices" role="group" aria-labelledby={labelledBy}>
      {choice("practiced")}
      {choice("rest")}
      <Localized id="today-other">
        <button
          type="button"
          className="choice"
          aria-pressed={reason}
          aria-expanded={open}
          onClick={() => {
            haptics.selection();
            setOpen(!open);
          }}
        />
      </Localized>
      {open && (
        <div className="choices reasons" role="group" aria-labelledby="day-reasons">
          <Localized id="today-reasons">
            <p id="day-reasons" className="hint small" />
          </Localized>
          {OTHER_REASONS.filter((status) => ladies || status !== "ladies").map(choice)}
        </div>
      )}
    </div>
  );
}
