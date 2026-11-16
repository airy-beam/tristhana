import { useDaysRange } from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { useBackButton } from "../../telegram";
import { DayLog } from "../DayLog";

interface Props {
  date: string;
  label: string;
  zone: string | null;
  locale: Locale;
  /** The device switch: when off, a ladies' holiday shows (and stays) as rest here too. */
  showLadies: boolean;
  onClose: () => void;
}

/** Log or change one earlier day from the month calendar (the Mini App backfill, ST-01): the
 * same day card as Today's (UI-06, Q335), for that date, with Done. The day is named at once;
 * its choices follow the read of that day. */
export function DayEditor({ date, label, zone, locale, showLadies, onClose }: Props) {
  useBackButton(onClose);
  const days = useDaysRange(date, date);
  return (
    <DayLog
      id="editor-title"
      title={label}
      date={date}
      days={days.data}
      zone={zone}
      locale={locale}
      showLadies={showLadies}
      onDone={onClose}
    />
  );
}
