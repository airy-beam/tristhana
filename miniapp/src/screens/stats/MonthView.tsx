import { useLocalization } from "@fluent/react";

import type { AutoDay, Stats } from "../../api/client";
import { autoArgs, cellAt, dateOf, daysInMonth, kindOf, labelKey, mondayFirst } from "./cells";

interface Props {
  stats: Stats;
  month: number;
  moon: Set<string>;
  auto: Map<string, AutoDay>;
  city: string;
  showLadies: boolean;
  weekdays: string[];
  dateLabel: (day: string) => string;
  onPick: (day: string) => void;
}

/** A large calendar for one month: tap a day up to today to log or change it. */
export function MonthView({
  stats,
  month,
  moon,
  auto,
  city,
  showLadies,
  weekdays,
  dateLabel,
  onPick,
}: Props) {
  const { l10n } = useLocalization();
  const offset = mondayFirst(stats.year, month);
  const days = daysInMonth(stats.year, month);
  return (
    <div className="month-grid" role="group" aria-labelledby="month-title">
      {weekdays.map((w) => (
        <span key={w} className="weekday" aria-hidden="true">
          {w}
        </span>
      ))}
      {Array.from({ length: offset }, (_, i) => (
        <span key={`pad${String(i)}`} />
      ))}
      {Array.from({ length: days }, (_, i) => {
        const day = dateOf(stats.year, month, i + 1);
        const cell = cellAt(stats, day);
        const future = cell === undefined;
        const rest = cell === "none" ? auto.get(day) : undefined;
        const marker = moon.has(day) ? "yes" : "no";
        const label = future
          ? l10n.getString("stats-cell-future", { date: dateLabel(day), moon: marker })
          : rest
            ? l10n.getString("stats-cell-auto", autoArgs(rest, dateLabel(day), city))
            : l10n.getString("stats-cell-label", {
                date: dateLabel(day),
                status: l10n.getString(labelKey(cell, showLadies)),
                moon: marker,
              });
        return (
          <button
            key={day}
            type="button"
            className={`day ${future ? "future" : rest ? "auto" : kindOf(cell, showLadies)}${
              day === stats.today ? " today" : ""
            }${moon.has(day) ? " moon-marker" : ""}`}
            disabled={future}
            aria-label={label}
            aria-current={day === stats.today ? "date" : undefined}
            onClick={() => {
              onPick(day);
            }}
          >
            {i + 1}
          </button>
        );
      })}
    </div>
  );
}
