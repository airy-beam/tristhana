import { Localized, useLocalization } from "@fluent/react";
import { useEffect, useState } from "react";

import {
  ApiError,
  STUDENTS_PAGE,
  useCatalog,
  useDropStudents,
  useMarkNewAsana,
  useRemoveStudent,
  useStudent,
  useStudents,
  type Catalog,
  type ProgressionPosition,
  type StudentCard,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import {
  backButtonAvailable,
  confirmAction,
  confirmDestructive,
  haptics,
  useBackButton,
} from "../../telegram";
import { lengthText } from "../practiceText";
import { get, isStanding, stopLabel } from "../progression/progressionText";

interface Props {
  locale: Locale;
  onBack: () => void;
}

/** "👥 My students" (ST-06): name and today's mark in the list, the 7 days on the card only, so
 * no side-by-side week can read as a "who hasn't practiced" list (Q78). Loaded lazily. */
export default function Students({ locale, onBack }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  return open ? (
    <Card
      id={open}
      locale={locale}
      onBack={() => {
        setOpen(null);
      }}
    />
  ) : (
    <List onBack={onBack} onOpen={setOpen} />
  );
}

function useName() {
  const { l10n } = useLocalization();
  return (name: string | null) => name ?? l10n.getString("link-no-name");
}

function List({ onBack, onOpen }: { onBack: () => void; onOpen: (id: string) => void }) {
  useBackButton(onBack);
  const [pages, setPages] = useState(1);
  const first = useStudents(0);
  const total = first.data?.total ?? 0;
  const empty = first.data && first.data.students.length === 0;
  return (
    <main className="screen students">
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      {first.data && (
        <Localized id="links-students" vars={{ count: total }}>
          <h1 />
        </Localized>
      )}
      <Localized id="students-days-note">
        <p className="hint" />
      </Localized>
      {first.isError && (
        <Localized id="students-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {empty && (
        <Localized id="links-no-students">
          <p className="hint" />
        </Localized>
      )}
      {Array.from({ length: pages }, (_, n) => (
        <Page key={n} offset={n * STUDENTS_PAGE} onOpen={onOpen} />
      ))}
      {pages * STUDENTS_PAGE < total && (
        <Localized id="students-more">
          <button
            type="button"
            className="row-button"
            onClick={() => {
              setPages(pages + 1);
            }}
          />
        </Localized>
      )}
    </main>
  );
}

function Page({ offset, onOpen }: { offset: number; onOpen: (id: string) => void }) {
  const { l10n } = useLocalization();
  const name = useName();
  const { data, isError } = useStudents(offset);
  return (
    <>
      {offset > 0 && isError && (
        <Localized id="students-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {data?.students.map((student) => (
        <button
          type="button"
          className="row-button"
          key={student.id}
          onClick={() => {
            onOpen(student.id);
          }}
        >
          {student.today && (
            <>
              <span role="img" aria-label={l10n.getString(`status-${student.today}`)}>
                {l10n.getString("students-mark", { state: student.today })}
              </span>{" "}
            </>
          )}
          <span className="student-name">{name(student.name)}</span>
        </button>
      ))}
    </>
  );
}

const DAY = 86_400_000;

function Card({ id, locale, onBack }: { id: string; locale: Locale; onBack: () => void }) {
  useBackButton(onBack);
  const { l10n } = useLocalization();
  const name = useName();
  const query = useStudent(id);
  const catalog = useCatalog().data;
  const remove = useRemoveStudent();
  const drop = useDropStudents();
  const gone = query.error instanceof ApiError && query.error.status === 404;
  useEffect(() => {
    if (gone) {
      drop();
      onBack();
    }
  }, [gone, drop, onBack]);
  const card = query.data;
  if (!card) {
    const back = !backButtonAvailable() && (
      <Localized id="stats-back">
        <button type="button" className="link" onClick={onBack} />
      </Localized>
    );
    if (!query.isError || gone) {
      return (
        <main className="screen" aria-busy="true">
          {back}
        </main>
      );
    }
    return (
      <main className="screen">
        {back}
        <Localized id="students-card-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      </main>
    );
  }

  const confirmRemove = async () => {
    const ok = await confirmDestructive(
      l10n.getString("link-remove-ask", { name: name(card.name) }),
      l10n.getString("links-remove-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("light");
    remove.mutate(card.id, { onSettled: onBack });
  };
  return (
    <main className="screen students">
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      <h1 className="student-name">{name(card.name)}</h1>
      <LastAsana card={card} catalog={catalog} locale={locale} />
      {catalog && (
        <MarkNewAsana
          card={card}
          catalog={catalog}
          locale={locale}
          onGone={() => {
            drop();
            onBack();
          }}
        />
      )}
      <Localized id="students-week">
        <h2 />
      </Localized>
      <Days card={card} catalog={catalog} locale={locale} />
      <Localized id="students-blank-note">
        <p className="hint" />
      </Localized>
      {card.quiet && (
        <Localized id="students-quiet">
          <p className="hint" />
        </Localized>
      )}
      <Localized id="links-remove">
        <button
          type="button"
          className="link"
          onClick={() => {
            void confirmRemove();
          }}
        />
      </Localized>
    </main>
  );
}

function LastAsana({
  card,
  catalog,
  locale,
}: {
  card: StudentCard;
  catalog: Catalog | undefined;
  locale: Locale;
}) {
  const { l10n } = useLocalization();
  const position = card.last_asana;
  if (!position) {
    // PR-08 Phase 3: an unset student has nothing to mark from (ST-06 already hides the line).
    return <p>{get(l10n, "students-give-unset")}</p>;
  }
  if (!catalog) return null;
  if (isStanding(position)) {
    return (
      <Localized id="students-last-standing">
        <p />
      </Localized>
    );
  }
  const found = catalog.series.find((s) => s.slug === position.series);
  const series = found ? l10n.getString("series-lower", { n: found.number }) : position.series;
  const asana = stopLabel(catalog, position, locale);
  return <p>{get(l10n, "students-last-asana", { asana, series: series ?? "" })}</p>;
}

/** PR-08 Phase 3: "🎉 Mark new asana" opens the card's `next_asanas` inline (one stop, or a
 * range from the first new stop, as the bot's picker); a pick asks once, then posts
 * `{from: last_asana, to}`. Not optimistic: the response replaces the card. 409 refetches the
 * card with the stale line; 404 goes back to the list. Shows no celebration, history or
 * delivery: the teacher learns only what they marked. */
function MarkNewAsana({
  card,
  catalog,
  locale,
  onGone,
}: {
  card: StudentCard;
  catalog: Catalog;
  locale: Locale;
  onGone: () => void;
}) {
  const { l10n } = useLocalization();
  const name = useName();
  const mark = useMarkNewAsana(card.id);
  const [open, setOpen] = useState(false);
  const [line, setLine] = useState<{ text: string; alert: boolean } | null>(null);
  const seen = card.last_asana;
  const next = (card as Partial<StudentCard>).next_asanas ?? []; // an older payload has none
  const first = next[0];

  const label = (target: ProgressionPosition) => stopLabel(catalog, target, locale);
  const seriesOf = (target: ProgressionPosition) => {
    const found = catalog.series.find((s) => s.slug === target.series);
    return found ? get(l10n, "series-lower", { n: found.number }) : (target.series ?? "");
  };

  const pick = async (target: ProgressionPosition, steps: number) => {
    if (!seen || !first) return;
    const vars = {
      name: name(card.name),
      from: label(first),
      from_series: seriesOf(first),
      asana: label(target),
      series: seriesOf(target),
    };
    // Across a series boundary the confirm names both series (Setu Bandhasana → Krounchasana).
    const ask =
      steps === 1
        ? "students-give-ask"
        : first.series !== target.series
          ? "students-give-ask-across"
          : "students-give-ask-range";
    const ok = await confirmAction(
      get(l10n, ask, vars),
      get(l10n, "students-give-yes"),
      get(l10n, "delete-cancel"),
    );
    if (!ok) return;
    setLine(null);
    mark.mutate(
      { from: seen, to: target },
      {
        onSuccess: () => {
          haptics.impact("light");
          setOpen(false);
          const id = steps === 1 ? "students-given" : "students-given-range";
          setLine({ text: get(l10n, id, vars), alert: false });
        },
        onError: (error) => {
          if (error instanceof ApiError && error.status === 404) {
            onGone();
            return;
          }
          haptics.notify("error");
          if (error instanceof ApiError && error.status === 409) {
            setOpen(false); // the card refetches: pick again from what it shows now
            setLine({ text: get(l10n, "students-give-stale"), alert: true });
          } else {
            // Nothing is known to have changed (network, 5xx): keep the picks for a retry.
            setLine({ text: get(l10n, "progression-save-failed"), alert: true });
          }
        },
      },
    );
  };

  return (
    <>
      {line &&
        (line.alert ? (
          <p className="status" role="alert">
            {line.text}
          </p>
        ) : (
          <p className="status" role="status">
            {line.text}
          </p>
        ))}
      {seen && first && (
        <Localized id="students-give">
          <button
            type="button"
            className="row-button"
            aria-expanded={open}
            disabled={mark.isPending}
            onClick={() => {
              setOpen(!open);
            }}
          />
        </Localized>
      )}
      {open && seen && first && (
        <div className="chips" role="group">
          {next.map((target, i) => (
            <button
              type="button"
              className="chip"
              key={`${target.series ?? ""}:${target.last ?? ""}`}
              disabled={mark.isPending}
              onClick={() => {
                void pick(target, i + 1);
              }}
            >
              {/* [Supta Vajrasana] [→ Bakasana B] [→ Bharadvajasana]: the confirm names the range */}
              {get(l10n, i === 0 ? "students-give-option" : "students-give-range", {
                asana: label(target),
              })}
            </button>
          ))}
        </div>
      )}
    </>
  );
}

function Days({
  card,
  catalog,
  locale,
}: {
  card: StudentCard;
  catalog: Catalog | undefined;
  locale: Locale;
}) {
  const { l10n } = useLocalization();
  const format = new Intl.DateTimeFormat(locale, {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
  const last = Date.parse(`${card.days[card.days.length - 1]?.date ?? ""}T00:00:00Z`);
  return (
    <ul>
      {[...card.days].reverse().map((day) => {
        const at = Date.parse(`${day.date}T00:00:00Z`);
        const rel = at === last ? "today" : at === last - DAY ? "yesterday" : "other";
        const label = l10n.getString("day-label", { rel, date: format.format(at) });
        if (!day.state) {
          return (
            <li
              key={day.date}
              className="student-day-blank"
              aria-label={l10n.getString("students-day-blank", { date: label })}
            >
              {l10n.getString("students-day-blank-mark", { date: label })}
            </li>
          );
        }
        const state = l10n.getString(`status-${day.state}`);
        const length = day.length && catalog ? lengthText(l10n, catalog, day.length, locale) : null;
        const text = length
          ? l10n.getString("students-day-length", { date: label, state, length })
          : l10n.getString("students-day", { date: label, state });
        return (
          <li key={day.date} className="student-day" aria-label={text}>
            {text}
          </li>
        );
      })}
    </ul>
  );
}
