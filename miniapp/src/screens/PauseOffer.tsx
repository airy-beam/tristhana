import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import {
  isPausable,
  useEndRestPeriod,
  useKeepRestPeriod,
  useStartRestPeriod,
  type DaySaved,
  type RestPeriod,
} from "../api/client";
import { haptics } from "../telegram";

/** "Thu, Oct 29" / «чт, 29 окт.» in the current UI language (dates only: no zone label). */
export function useDateLabel(): (day: string) => string {
  const { l10n } = useLocalization();
  const locale = [...l10n.bundles][0]?.locales[0] ?? "en";
  const format = new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
  return (day) => format.format(new Date(`${day}T00:00:00Z`));
}

const onOff = (flag: boolean) => (flag ? "on" : "off");

/** After a save (WH-01, ADR-0023): "for how many days?" with the server's day counts, or,
 * when a 🧘 save cut a pause that still had days ahead, a gentle "Keep the pause". Ignoring
 * it (or "Just today") is fine: no pause. `onDone` hides it once answered. */
export function PauseOffer({
  saved,
  today,
  onDone,
  showLadies = true,
}: {
  saved: DaySaved;
  today: string;
  onDone: () => void;
  /** The device switch: when off, 🌸 is named as rest here too (as PeriodLine). */
  showLadies?: boolean;
}) {
  const [more, setMore] = useState(false);
  const start = useStartRestPeriod();
  const keep = useKeepRestPeriod();
  const end = useEndRestPeriod();
  const { l10n } = useLocalization();
  const dateLabel = useDateLabel();
  const offer = saved.pause_offer;
  const cut = saved.cut;
  const named = (kind: string) => (kind === "ladies" && !showLadies ? "rest" : kind);

  if (offer) {
    const label = l10n.getString(`status-${named(offer.kind)}`);
    const rel = offer.start === today ? "today" : "yesterday";
    return (
      <div className="pause">
        <Localized id="pause-ask" vars={{ label, rel, reminders: onOff(offer.reminders_on) }}>
          <p className="hint" />
        </Localized>
        <div className="chips" role="group">
          {(more ? offer.more : offer.choices).map((n) => (
            <Localized key={n} id="pause-days" vars={{ n }}>
              <button
                type="button"
                className="chip"
                onClick={() => {
                  haptics.impact("light");
                  onDone(); // optimistic: the period line takes its place
                  start.mutate(
                    { start: offer.start, days: n, kind: offer.kind },
                    {
                      onError: () => {
                        haptics.notify("error");
                      },
                    },
                  );
                }}
              />
            </Localized>
          ))}
          <Localized id={more ? "pause-back" : "pause-other"}>
            <button
              type="button"
              className="chip"
              onClick={() => {
                setMore(!more);
              }}
            />
          </Localized>
        </div>
        <Localized id="pause-only" vars={{ rel }}>
          <button
            type="button"
            className="link"
            onClick={() => {
              haptics.impact("light");
              onDone(); // the day is saved: just no pause
              // A re-asked first day of a pause: "just that day" means no pause.
              if (saved.period?.start === offer.start) {
                end.mutate({ start: offer.start, today });
              }
            }}
          />
        </Localized>
      </div>
    );
  }
  if (cut && isPausable(cut) && cut.end > saved.date && cut.end >= today) {
    const label = l10n.getString(`status-${named(cut.kind)}`);
    const rel =
      saved.date === today ? "today" : isYesterday(saved.date, today) ? "yesterday" : "other";
    return (
      <div className="pause">
        <Localized id="pause-cut" vars={{ label, until: dateLabel(cut.end), rel }}>
          <p className="hint" />
        </Localized>
        <Localized id="pause-keep">
          <button
            type="button"
            className="link"
            onClick={() => {
              haptics.impact("light");
              onDone();
              keep.mutate(cut, {
                onError: () => {
                  haptics.notify("error");
                },
              });
            }}
          />
        </Localized>
      </div>
    );
  }
  return null;
}

function isYesterday(day: string, today: string): boolean {
  return Date.parse(`${today}T00:00:00Z`) - Date.parse(`${day}T00:00:00Z`) === 86_400_000;
}

/** A day a rest period covers (or its first day): what it shows as, and End early. */
export function PeriodLine({
  period,
  day,
  today,
  logged,
  practiceOn,
  showLadies = true,
}: {
  period: RestPeriod;
  day: string;
  today: string;
  /** The day has its own status: then only the End link (the status says the rest). */
  logged: boolean;
  practiceOn: boolean;
  showLadies?: boolean;
}) {
  const end = useEndRestPeriod();
  const { l10n } = useLocalization();
  const dateLabel = useDateLabel();
  const kind = period.kind === "ladies" && !showLadies ? "rest" : period.kind;
  const showLine = !logged || day === period.start;
  return (
    <>
      {showLine && (
        <Localized
          id="today-period"
          vars={{ label: l10n.getString(`status-${kind}`), until: dateLabel(period.end) }}
        >
          <p className="hint" />
        </Localized>
      )}
      {period.end >= today && (
        <Localized id="pause-end" vars={{ reminders: onOff(practiceOn) }}>
          <button
            type="button"
            className="link"
            onClick={() => {
              haptics.impact("light");
              end.mutate(
                { start: period.start, today },
                {
                  onError: () => {
                    haptics.notify("error");
                  },
                },
              );
            }}
          />
        </Localized>
      )}
    </>
  );
}
