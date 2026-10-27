import { Localized } from "@fluent/react";
import { useState } from "react";

import {
  DAY_STATUSES,
  periodOn,
  useDaysRange,
  useMe,
  useSetDay,
  type DaySaved,
  type DayStatus,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { haptics } from "../../telegram";
import { AutoNote } from "../AutoNote";
import { CheckIn } from "../CheckIn";
import { PauseOffer, PeriodLine } from "../PauseOffer";
import { PracticeDetails } from "../PracticeDetails";

interface Props {
  date: string;
  label: string;
  zone: string | null;
  locale: Locale;
  /** The device switch: when off, a ladies' holiday shows (and stays) as rest here too. */
  showLadies: boolean;
  onClose: () => void;
}

/** Log or change one earlier day from the month calendar (the Mini App backfill, ST-01). */
export function DayEditor({ date, label, zone, locale, showLadies, onClose }: Props) {
  const days = useDaysRange(date, date);
  const setDay = useSetDay();
  const hideLadies = useMe().data?.hide_ladies === true;
  const [after, setAfter] = useState<DaySaved | null>(null);
  // Taps update this cache optimistically (every day query), so it is always current.
  const logged = days.data?.days.find((d) => d.date === date);
  const auto = logged ? undefined : days.data?.auto.find((a) => a.date === date);
  const stored = logged?.status ?? null;
  const hidden = !showLadies && stored === "ladies";
  const current = hidden ? "rest" : stored;
  const period = periodOn(days.data, date);
  // "Hide the 🌸 button" (WH-01) keeps it on a day that shows as 🌸.
  const shown = current ?? period?.kind ?? null;
  const ladiesChip = showLadies && !(hideLadies && shown !== "ladies");
  const statuses = ladiesChip ? DAY_STATUSES : DAY_STATUSES.filter((s) => s !== "ladies");

  const save = (status: DayStatus | null) => {
    haptics.impact("light");
    setAfter(null);
    setDay.mutate(
      { date, status },
      {
        onSuccess: (saved) => {
          setAfter(saved);
        },
        onError: () => {
          haptics.notify("error");
        },
      },
    );
  };

  return (
    <section className="card editor" aria-labelledby="editor-title">
      <h2 id="editor-title">{label}</h2>
      {auto && days.data && (
        <AutoNote auto={auto} location={days.data.moon_location} locale={locale} />
      )}
      {period && days.data && (
        <PeriodLine
          period={period}
          day={date}
          today={days.data.today}
          logged={stored !== null}
          practiceOn={days.data.practice_on}
          showLadies={showLadies}
        />
      )}
      <div className="chips" role="group" aria-labelledby="editor-title">
        {statuses.map((status) => (
          <Localized key={status} id={`status-${status}`}>
            <button
              type="button"
              className="chip"
              aria-pressed={status === current}
              onClick={() => {
                if (status !== current) save(status);
              }}
            />
          </Localized>
        ))}
      </div>
      {after && after.date === date && days.data && (
        <PauseOffer
          saved={after}
          today={days.data.today}
          showLadies={showLadies}
          onDone={() => {
            setAfter(null);
          }}
        />
      )}
      {current === "practiced" && logged && (
        <PracticeDetails
          date={date}
          practice={logged.practices[0] ?? null}
          zone={zone}
          locale={locale}
        />
      )}
      {current === "practiced" && logged && days.data && (
        <CheckIn date={date} checkIns={logged.check_ins} today={days.data.today} />
      )}
      {current === "ladies" && showLadies && (
        <Localized id="today-private-note">
          <p className="hint" />
        </Localized>
      )}
      <div className="row">
        {current !== null && (
          <Localized id="today-clear">
            <button
              type="button"
              className="link"
              onClick={() => {
                save(null);
              }}
            />
          </Localized>
        )}
        <Localized id="stats-editor-done">
          <button type="button" className="link" onClick={onClose} />
        </Localized>
      </div>
      {setDay.isError && (
        <Localized id="today-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </section>
  );
}
