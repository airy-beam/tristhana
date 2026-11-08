import { Localized, useLocalization } from "@fluent/react";

import { useMe, useMyClasses, type MyClass, type MyShalaClasses } from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { backButtonAvailable, useBackButton } from "../../telegram";
import { zoneLabel } from "../practiceText";
import { deviceZone } from "../settings/zones";
import { useOccurrenceText } from "./ShalaSchedule";
import { dateIn, dayName, plain } from "./scheduleText";

interface Props {
  locale: Locale;
  onBack: () => void;
}

/** "🧑‍🏫 My classes": the next 7 days of the classes I teach, cover or have covered, in every
 * shala where I'm on the staff, each in its own zone. Read only: changes live on the shala's
 * schedule. Loaded lazily. */
export default function MyClasses({ locale, onBack }: Props) {
  useBackButton(onBack);
  const query = useMyClasses();
  const viewer = useMe().data?.timezone ?? deviceZone();
  return (
    <main className="screen my-classes" aria-busy={query.isPending}>
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      <Localized id="my-classes-title">
        <h1 />
      </Localized>
      <Localized id="my-classes-subtitle">
        <p className="hint small" />
      </Localized>
      {query.isError && (
        <Localized id="my-classes-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {query.data?.length === 0 && (
        <Localized id="my-classes-empty">
          <p className="hint" />
        </Localized>
      )}
      {query.data?.map((s) => (
        <ShalaWeek key={s.shala_id} shala={s} locale={locale} viewer={viewer} />
      ))}
    </main>
  );
}

function ShalaWeek({
  shala,
  locale,
  viewer,
}: {
  shala: MyShalaClasses;
  locale: Locale;
  viewer: string | null;
}) {
  const { l10n } = useLocalization();
  const text = useOccurrenceText(shala.zone, viewer);
  const name = (t: { name: string | null } | null) => t?.name ?? l10n.getString("link-no-name");
  const other = (c: MyClass) => {
    if (c.role === "covered")
      return plain(l10n.getString("my-classes-covered", { name: name(c.teacher) }));
    if (c.role === "covering" && c.usual_teacher)
      return plain(l10n.getString("my-classes-covering", { name: name(c.usual_teacher) }));
    return "";
  };
  const days = [...new Set(shala.classes.map((c) => dateIn(c.starts_at, shala.zone)))];
  return (
    <section className="card schedule">
      <h2>{shala.name}</h2>
      <p className="hint small">{zoneLabel(shala.zone, shala.today)}</p>
      {days.map((day) => (
        <div key={day} className="schedule-day">
          <h3 className="label">{dayName(day, locale)}</h3>
          {shala.classes
            .filter((c) => dateIn(c.starts_at, shala.zone) === day)
            .map((c) => (
              <p key={`${c.class_id}:${c.key}`} className="link-person">
                {text(c, other(c))}
              </p>
            ))}
        </div>
      ))}
    </section>
  );
}
