import { Localized, useLocalization, type ReactLocalization } from "@fluent/react";
import { Suspense, useEffect, useState, type ReactNode } from "react";

import {
  periodOn,
  useCatalog,
  useMe,
  usePracticePresets,
  useSavePractice,
  useSetDay,
  type Catalog,
  type Celebration,
  type CheckIn as CheckInValue,
  type Days,
  type DaySaved,
  type DayStatus,
  type Practice,
} from "../api/client";
import type { Locale } from "../i18n/negotiate";
import { ChunkGuard } from "../shell/ChunkGuard";
import { lazyRetry } from "../shell/lazyRetry";
import { haptics } from "../telegram";
import { AutoNote } from "./AutoNote";
import { DayChoice } from "./DayChoice";
import { DiaryNote } from "./DiaryNote";
import { PauseOffer, PeriodLine } from "./PauseOffer";
import { lastWhen, practiceSummary } from "./practiceText";
import { CountCelebration } from "./progression/CountCelebration";
import { Row } from "./Row";

// Details and the check-in editor are one chunk outside the first one: they mount on a tap.
const loadExtras = () => import("./dayExtras");
const PracticeDetails = lazyRetry(async () => ({ default: (await loadExtras()).PracticeDetails }));
const CheckIn = lazyRetry(async () => ({ default: (await loadExtras()).CheckIn }));

interface Props {
  /** The heading's id: the card's and the choices' accessible name. */
  id: string;
  /** "Today, Sun, Oct 18", or the day's label in the day editor. */
  title: string;
  date: string;
  /** The loaded days that include `date` ("today" is the server's, never the device's). While
   * they load, the card is its heading. */
  days: Days | undefined;
  /** The read failed and there are no days: the card says so (and still closes with Done). */
  failed?: boolean;
  /** The account's IANA zone (null until the device reported it). */
  zone: string | null;
  locale: Locale;
  /** The device switch of the day editor: when off, a ladies' holiday shows (and stays) as
   * rest here too. */
  showLadies?: boolean;
  /** The day editor: Done closes it, and an unlogged day can get a note too. */
  onDone?: (() => void) | undefined;
  /** Lines under the heading (Today's moon line). */
  children?: ReactNode;
}

/** The one day card (UI-06), for today and for any earlier day, as the bot's Today and day
 * editor. An unanswered day shows three choices. A logged day folds them into one line that
 * states it, with "Change" (the choices again, and Clear); under it the entries are list rows.
 * Nothing opens by itself: details, the check-in and the note each wait for their own tap. */
export function DayLog({ id, title, days, failed, onDone, children, ...day }: Props) {
  const done = onDone && (
    <Localized id="stats-editor-done">
      <button type="button" className="link" onClick={onDone} />
    </Localized>
  );
  return (
    <section
      className={onDone ? "card daylog editor" : "card daylog"}
      aria-labelledby={id}
      aria-busy={days || failed ? undefined : true}
    >
      <h2 id={id}>{title}</h2>
      {days && children}
      {/* Another day starts clean: no answer, open reasons or note carried over. */}
      {days ? (
        <Day key={day.date} id={id} days={days} done={done} {...day} />
      ) : (
        failed && (
          <>
            <Localized id="today-load-failed">
              <p className="status" role="alert" />
            </Localized>
            <div className="row">{done}</div>
          </>
        )
      )}
    </section>
  );
}

function Day({
  id,
  date,
  days,
  zone,
  locale,
  showLadies = true,
  done,
}: Omit<Props, "title" | "children" | "days" | "failed" | "onDone"> & {
  days: Days;
  /** The day editor's Done button: with it an unlogged day can get a note too. */
  done: ReactNode;
}) {
  const { l10n } = useLocalization();
  const setDay = useSetDay();
  const hideLadies = useMe().data?.hide_ladies === true;
  // The last save's answer: the pause offer or "keep the pause" (WH-01).
  const [after, setAfter] = useState<DaySaved | null>(null);
  // GM-01 part 2: a practice count this save reached (dismissed on its own).
  const [counted, setCounted] = useState<Celebration[]>([]);

  const { today } = days;
  // Taps update the cache optimistically (every day query), so this is always current.
  const logged = days.days.find((d) => d.date === date);
  // Auto-rest is a line, never a pressed choice: logging anything replaces it (PR-09).
  const auto = logged ? undefined : days.auto.find((a) => a.date === date);
  const stored = logged?.status ?? null;
  const current = !showLadies && stored === "ladies" ? "rest" : stored;
  const period = periodOn(days, date);
  // "Hide the 🌸 button" (WH-01) keeps it on a day that shows as 🌸.
  const ladies = showLadies && !(hideLadies && (current ?? period?.kind) !== "ladies");
  const note = days.notes.find((n) => n.date === date);
  // The note entry: on a logged day, where a note exists, and always in the day editor. Once
  // shown it stays while the card is open, so clearing the day never drops a note being typed.
  const [noted, setNoted] = useState(false);
  if (!noted && (stored !== null || note !== undefined || done)) setNoted(true);
  // "Change" on a logged day: the three choices again, with Clear.
  const [changing, setChanging] = useState(false);

  const save = (status: DayStatus | null) => {
    haptics.impact("light"); // feedback before the network call
    setAfter(null);
    setCounted([]);
    setDay.mutate(
      { date, status },
      {
        onSuccess: (saved) => {
          setAfter(saved);
          // Only kinds the card shows (an older server's answer has no `celebrations`).
          const found = (saved?.celebrations ?? []).filter((c) => c.kind === "practice_count");
          if (found.length) {
            haptics.notify("success");
            setCounted(found);
          }
        },
        onError: () => {
          haptics.notify("error");
        },
      },
    );
  };

  return (
    <>
      {auto && <AutoNote auto={auto} location={days.moon_location} locale={locale} />}
      {period && (
        <PeriodLine
          period={period}
          day={date}
          today={today}
          logged={stored !== null}
          practiceOn={days.practice_on}
          showLadies={showLadies}
        />
      )}
      {current === null ? (
        // Only a day nothing has answered yet gets the question, as in the bot.
        !auto &&
        !period && (
          <Localized id="today-prompt">
            <p className="hint" />
          </Localized>
        )
      ) : (
        // The day's one line: what it is, a reason behind "Other…" by its own name.
        <div className="state">
          <p id={`${id}-state`}>{l10n.getString(`status-${current}`)}</p>
          <Localized id="today-change">
            <button
              type="button"
              className="link"
              aria-expanded={changing}
              aria-describedby={`${id}-state`}
              onClick={() => {
                haptics.selection();
                setChanging(!changing);
              }}
            />
          </Localized>
        </div>
      )}
      {current === "ladies" && (
        <Localized id="today-private-note">
          <p className="hint small" />
        </Localized>
      )}
      {counted.length > 0 && (
        <CountCelebration
          found={counted}
          onDismiss={() => {
            setCounted([]);
          }}
        />
      )}
      {(current === null || changing) && (
        <DayChoice
          current={current}
          ladies={ladies}
          labelledBy={id}
          onPick={(status) => {
            setChanging(false);
            if (status !== current) save(status);
          }}
        />
      )}
      {current !== null && changing && (
        <Localized id="today-clear">
          <button
            type="button"
            className="link clear"
            onClick={() => {
              setChanging(false);
              save(null);
            }}
          />
        </Localized>
      )}
      {after && after.date === date && (
        <PauseOffer
          saved={after}
          today={today}
          showLadies={showLadies}
          onDone={() => {
            setAfter(null);
          }}
        />
      )}
      {((current === "practiced" && logged) || noted) && (
        <div className="list">
          {current === "practiced" && logged && (
            <PracticeEntries
              date={date}
              practice={logged.practices[0]}
              checkIns={logged.check_ins}
              zone={zone}
              locale={locale}
            />
          )}
          {/* Another day starts clean: no draft or confirm carried over. */}
          {noted && <DiaryNote key={date} date={date} note={note} />}
        </div>
      )}
      {done && <div className="row">{done}</div>}
      {setDay.isError && (
        <Localized id="today-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </>
  );
}

const detailed = (p: Practice | undefined) =>
  !!p && (!!p.context || !!p.length || !!p.duration_min || !!p.start_time);

// Fluent's bidi isolation marks around variables: noise in a composed line.
const plain = (text: string) => text.replace(/[⁨⁩]/g, "");

/** "🙂 · ⚡ energy 4/5 · 🔥 effort 3/5 · Light, Calm", as the bot's; "" for none. */
function checkInSummary(l10n: ReactLocalization, c: CheckInValue, catalog: Catalog | undefined) {
  const parts: string[] = [];
  if (c.mood != null) parts.push(l10n.getString("checkin-mood-chip", { n: c.mood }));
  if (c.energy != null) parts.push(l10n.getString("checkin-summary-energy", { n: c.energy }));
  if (c.effort != null) parts.push(l10n.getString("checkin-summary-effort", { n: c.effort }));
  const tags = (catalog?.check_in_tags ?? [])
    .filter((t) => c.tags.includes(t.key)) // the catalog's order
    .map((t) => l10n.getString("checkin-tag", { tag: t.key }));
  if (tags.length) parts.push(tags.join(", "));
  return plain(parts.join(" · "));
}

type Panel = "details" | "checkin";

/** The rows of a practiced day: "Same as last time" (with what it would copy, as the bot shows
 * it: Q23, Q296), "Add details" or the details' summary, "How do you feel?" with the
 * check-in's. Each panel mounts on its own tap, one at a time. */
function PracticeEntries({
  date,
  practice,
  checkIns,
  zone,
  locale,
}: {
  date: string;
  practice: Practice | undefined;
  /** Absent from an older API. */
  checkIns: CheckInValue[] | undefined;
  zone: string | null;
  locale: Locale;
}) {
  const { l10n } = useLocalization();
  const offered = useMe().data?.offer_check_in === true;
  const catalog = useCatalog().data;
  const presets = usePracticePresets(date, true).data;
  const last = presets?.last;
  const save = useSavePractice();
  const [open, setOpen] = useState<Panel | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    void loadExtras().catch(() => undefined); // ready before the tap; a tap tries again
  }, []);

  const hasDetails = detailed(practice);
  const felt = checkIns?.[0] ? checkInSummary(l10n, checkIns[0], catalog) : "";
  const toggle = (panel: Panel) => () => {
    haptics.selection();
    setFailed(false);
    setOpen(open === panel ? null : panel);
  };
  const panel = (node: ReactNode) => (
    <ChunkGuard
      onFail={() => {
        haptics.notify("error");
        setOpen(null); // the next tap loads it again
        setFailed(true);
      }}
    >
      <Suspense fallback={<div className="details" aria-busy="true" />}>{node}</Suspense>
    </ChunkGuard>
  );

  return (
    <>
      {last && !hasDetails && (
        <Row
          action
          label={l10n.getString("practice-same-as-last")}
          sub={
            catalog &&
            [
              lastWhen(presets.last_date ?? null, date, locale),
              practiceSummary(l10n, catalog, last, locale),
            ]
              .filter(Boolean)
              .join(" · ")
          }
          onClick={() => {
            haptics.impact("light");
            save.mutate(
              {
                date,
                // Never the start time: that was the other day's.
                body: {
                  context: last.context ?? null,
                  online: last.context === "self" ? false : last.online,
                  length: last.length ?? null,
                  duration_min: last.duration_min ?? null,
                  start_time: null,
                },
              },
              {
                onError: () => {
                  haptics.notify("error");
                },
              },
            );
          }}
        />
      )}
      <Row
        label={l10n.getString(hasDetails ? "practice-details" : "practice-add-details")}
        sub={practice && catalog && practiceSummary(l10n, catalog, practice, locale)}
        expanded={open === "details"}
        onClick={toggle("details")}
      />
      {open === "details" &&
        panel(
          <PracticeDetails date={date} practice={practice ?? null} zone={zone} locale={locale} />,
        )}
      {/* The setting shows or hides the entry; a check-in that exists stays editable (Q313). */}
      {(offered || felt !== "") && (
        <Row
          label={l10n.getString("checkin-edit")}
          sub={felt}
          expanded={open === "checkin"}
          onClick={toggle("checkin")}
        />
      )}
      {open === "checkin" && panel(<CheckIn date={date} checkIns={checkIns} />)}
      {/* "Same as last time" did not save: the entry is still there to tap again. */}
      {save.isError && (
        <Localized id="today-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
      {failed && (
        <Localized id="chunk-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </>
  );
}
