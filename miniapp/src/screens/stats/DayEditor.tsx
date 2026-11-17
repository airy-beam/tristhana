import { useEffect, useRef, type ReactNode } from "react";

import { useDaysRange } from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { useBackButton } from "../../telegram";
import { DayLog } from "../DayLog";

interface Props {
  date: string;
  label: string;
  zone: string | null;
  locale: Locale;
  onClose: () => void;
  /** Lines under the heading (the month calendar's moon line). */
  children?: ReactNode;
}

/** Log or change one earlier day from the month calendar (the Mini App backfill, ST-01): the
 * same day card as Today's (UI-06, Q336), for that date, with Done. The day is named at once;
 * its choices follow the read of that day, or the card says the read failed. It tells its owner
 * the truth, as Today and the bot do: a ladies' holiday is offered and shown as one, whatever
 * the calendar's device switch says. Opened by a tap, it comes into view and its heading takes
 * the focus. */
export function DayEditor({ date, label, zone, locale, onClose, children }: Props) {
  useBackButton(onClose);
  const days = useDaysRange(date, date);
  const card = useRef<HTMLDivElement>(null);
  const settled = days.data !== undefined || days.isError;
  useEffect(() => {
    card.current?.querySelector("h2")?.focus({ preventScroll: true });
  }, []);
  // Twice: the heading at once, then the whole card when its choices have arrived.
  useEffect(() => {
    card.current?.scrollIntoView({ block: "nearest" });
  }, [settled]);
  return (
    <div ref={card}>
      <DayLog
        id="editor-title"
        title={label}
        date={date}
        days={days.data}
        failed={days.isError}
        zone={zone}
        locale={locale}
        onDone={onClose}
      >
        {children}
      </DayLog>
    </div>
  );
}
