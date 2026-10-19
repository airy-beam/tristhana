import { useLocalization } from "@fluent/react";

import type { Stats } from "../../api/client";
import { cellAt, dateOf, daysInMonth, kindOf, labelKey, mondayFirst } from "./cells";

const SIZE = 10;
const GAP = 2;
const STEP = SIZE + GAP;

interface Props {
  stats: Stats;
  moon: Set<string>;
  showLadies: boolean;
  month: number;
  onMonth: (month: number) => void;
  monthName: (month: number) => string;
  dateLabel: (day: string) => string;
}

/** 12 mini-months in a 3 × 4 grid (fits a 360 px phone); tapping one opens it below. */
export function Heatmap({ stats, moon, showLadies, month, onMonth, monthName, dateLabel }: Props) {
  const { l10n } = useLocalization();
  return (
    <div className="heatmap">
      {Array.from({ length: 12 }, (_, m) => {
        const offset = mondayFirst(stats.year, m);
        const days = daysInMonth(stats.year, m);
        const rows = Math.ceil((offset + days) / 7);
        return (
          <button
            key={m}
            type="button"
            className="mini-month"
            aria-pressed={m === month}
            aria-label={monthName(m)}
            onClick={() => {
              onMonth(m);
            }}
          >
            <span className="mini-month-name" aria-hidden="true">
              {monthName(m).slice(0, 3)}
            </span>
            <svg
              width={7 * STEP - GAP}
              height={rows * STEP - GAP}
              aria-hidden="true"
              focusable="false"
            >
              {Array.from({ length: days }, (_, i) => {
                const day = dateOf(stats.year, m, i + 1);
                const cell = cellAt(stats, day);
                const slot = offset + i;
                const x = (slot % 7) * STEP;
                const y = Math.floor(slot / 7) * STEP;
                const kind = cell === undefined ? "future" : kindOf(cell, showLadies);
                const title =
                  cell === undefined
                    ? null
                    : l10n.getString("stats-cell-label", {
                        date: dateLabel(day),
                        status: l10n.getString(labelKey(cell, showLadies)),
                        moon: moon.has(day) ? "yes" : "no",
                      });
                return (
                  <g key={day}>
                    <rect x={x} y={y} width={SIZE} height={SIZE} rx={2} className={`cell ${kind}`}>
                      {title && <title>{title}</title>}
                    </rect>
                    {moon.has(day) && (
                      <circle
                        cx={x + SIZE / 2}
                        cy={y + SIZE / 2}
                        r={SIZE / 2 - 0.5}
                        className="moon-ring"
                      />
                    )}
                  </g>
                );
              })}
            </svg>
          </button>
        );
      })}
    </div>
  );
}
