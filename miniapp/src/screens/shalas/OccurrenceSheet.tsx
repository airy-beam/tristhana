import { Localized, useLocalization } from "@fluent/react";
import { Suspense, useState, type ReactNode } from "react";

import {
  ApiError,
  useClearOccurrence,
  useReadClasses,
  useRefreshSchedule,
  useSetOccurrence,
  useUpdateClass,
  type Occurrence,
  type OccurrenceChange,
  type Shala,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { lazyRetry } from "../../shell/lazyRetry";
import { confirmDestructive, haptics } from "../../telegram";
import { Field, Select } from "../../ui/controls";
import { Row } from "../Row";
import { timeLabel } from "../timeLabel";
import { runsBefore, runsOn } from "./classForm";
import { lengthOf, useTypeName } from "./classText";
import { addDays, dateIn, dayName, fullDate, plain, timeIn } from "./scheduleText";
import "./shalaCopy";
import "./shala.css";

// SC-05: the staff roster is its own lazy chunk.
const Attendance = lazyRetry(() => import("./Attendance"));

interface Props {
  shala: Shala;
  occurrence: Occurrence;
  locale: Locale;
  onDone: () => void;
  /** "Change the class…": the series, opened from this date. */
  onEdit: (occurrence: Occurrence) => void;
  /** "Tell students…": the announcement, with this text to start from (Q339). */
  onTell: (draft: string) => void;
  /** The class no longer has this date (it was changed or removed meanwhile): the sheet
   * closes, and the week says so over the schedule as it is now. */
  onGone: () => void;
}

const gone = (error: unknown) => error instanceof ApiError && error.status === 404;

/** Staff on one occurrence: attendance (any staff seat, SC-05); and for those who manage
 * classes two headed groups (UI-06 stage 4). "This date": substitute, cancel, hold anyway
 * (auto-cancelled only, Q126), restore, and for a cancelled date "Tell students…". "The whole
 * class": change it, or end it from this date (a date that has not begun); deleting every
 * date is in the edit form, so nothing here touches an earlier date. */
export default function OccurrenceSheet({
  shala,
  occurrence: o,
  locale,
  onDone,
  onEdit,
  onTell,
  onGone,
}: Props) {
  const { l10n } = useLocalization();
  const [roster, setRoster] = useState(false);
  const counts = o.attendance_counts;
  const attendance = counts && (
    <>
      {roster ? (
        <Suspense fallback={null}>
          <Attendance
            shalaId={shala.id}
            classId={o.class_id}
            occurrenceKey={o.key}
            locale={locale}
            onClose={() => {
              setRoster(false);
            }}
          />
        </Suspense>
      ) : (
        <Row
          label={plain(
            l10n.getString("attend-staff-open", {
              confirmed: counts.confirmed,
              claimed: counts.claimed,
            }),
          )}
          onClick={() => {
            haptics.selection();
            setRoster(true);
          }}
        />
      )}
    </>
  );
  if (!shala.me.schedule) return <div className="sheet list">{attendance}</div>;
  return (
    <Manage
      shala={shala}
      occurrence={o}
      locale={locale}
      onDone={onDone}
      onEdit={onEdit}
      onTell={onTell}
      onGone={onGone}
      attendance={attendance}
    />
  );
}

function Manage({
  shala,
  occurrence: o,
  locale,
  onDone,
  onEdit,
  onTell,
  onGone,
  attendance,
}: Props & { attendance: ReactNode }) {
  const { l10n } = useLocalization();
  const typeName = useTypeName();
  const set = useSetOccurrence(shala.id);
  const clear = useClearOccurrence(shala.id);
  const end = useUpdateClass(shala.id);
  const readClasses = useReadClasses(shala.id);
  const refresh = useRefreshSchedule(shala.id);
  // "End this class from this date": reading the class, or what stopped it.
  const [ending, setEnding] = useState<"reading" | "first" | "failed" | null>(null);
  // Cancelled here a moment ago: the sheet stays for "Tell students…" (Q339), which a
  // cancelled date keeps for as long as it is cancelled.
  const [cancelled, setCancelled] = useState(false);
  // Everyone in the shala but me, as the announcement counts its readers: with no one to
  // tell there is nothing to offer.
  const readers = shala.staff.length + (shala.students_total ?? 0) - 1;
  // Never for a 1:1 (Q121: it names a person's class to the whole shala).
  const mayTell = shala.me.announce && o.type !== "private" && readers > 0;
  const target = { classId: o.class_id, key: o.key };
  // A 404: this id has no such date any more (the class was changed from an earlier date,
  // ADR-0048, or removed). Nothing to try again: the schedule as it is now, with a line.
  const failed = (error: unknown) => {
    haptics.notify("error");
    if (!gone(error)) return;
    refresh();
    onGone();
  };
  // A write replaces the date's changes: send its move, substitute and hold again (Q126). A
  // swapped date's own move ends on `swapped_from`, not on the swap's day.
  const kept = (): OccurrenceChange => ({
    status: o.held ? "held" : null,
    teacher_id: o.substitute && o.teacher ? o.teacher.id : null,
    ...(o.moved ? { on: o.swapped_from ?? o.on, start: o.start, minutes: lengthOf(o) } : {}),
  });
  const change = (status: "cancelled" | "held") => {
    haptics.impact("light");
    const body = status === "held" ? { ...kept(), status } : { status };
    const tell = status === "cancelled" && mayTell;
    set.mutate(
      { ...target, body },
      {
        onSuccess: tell
          ? () => {
              setCancelled(true); // the sheet stays, for the offer
            }
          : onDone,
        onError: failed,
      },
    );
  };
  const restore = () => {
    haptics.impact("light");
    clear.mutate(target, { onSuccess: onDone, onError: failed });
  };
  // The class's last date becomes the day before this one: this date and the later ones go,
  // the earlier ones stay as they were. The class is read first, as it is now: a last date
  // set from an old picture could reach past the date someone else has just ended it on, and
  // run it beside its own successor (ADR-0048). The read also tells the question what to
  // say: a class that already has a last date ends only up to it.
  const endHere = async () => {
    haptics.selection();
    setEnding("reading");
    let series;
    try {
      series = (await readClasses()).find((c) => c.id === o.class_id);
    } catch {
      setEnding("failed");
      return;
    }
    if (!series || !runsOn(series, o.key)) {
      setEnding(null);
      refresh();
      onGone();
      return;
    }
    // Its first date (or its only one): there is no earlier date to end on.
    if (!runsBefore(series, o.key)) {
      setEnding("first");
      return;
    }
    setEnding(null);
    const day = dayName(o.key, locale);
    const ask = series.ends_on
      ? l10n.getString("class-end-ask-range", { day, end: fullDate(series.ends_on, locale) })
      : l10n.getString("class-end-ask", { day });
    const ok = await confirmDestructive(
      plain(ask),
      l10n.getString("class-end-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("heavy");
    end.mutate(
      { classId: o.class_id, body: { ends_on: addDays(o.key, -1) } },
      { onSuccess: onDone, onError: failed },
    );
  };
  // "Usual teacher" names no one for the date: it follows the class's teacher.
  const substitute = (teacher: string) => {
    haptics.impact("light");
    const body = { ...kept(), teacher_id: teacher || null };
    set.mutate({ ...target, body }, { onSuccess: onDone, onError: failed });
  };
  // The text a reader in any zone can use later: the day and the time in the shala's zone,
  // with its offset (ADR-0044); never a person's name.
  const tell = () => {
    haptics.selection();
    const day = dateIn(o.starts_at, shala.zone);
    const draft = l10n.getString("ann-cancel-draft", {
      class: `${typeName(o.type)}${o.title ? ` ${o.title}` : ""}`,
      day: dayName(day, locale),
      time: timeLabel(timeIn(o.starts_at, shala.zone), shala.zone, day, {
        place: shala.city.name,
      }),
    });
    onTell(plain(draft));
  };
  const named = o.substitute && o.teacher ? o.teacher : null;
  const pending = set.isPending || clear.isPending || end.isPending || ending === "reading";
  // Offered while the date's class has not begun: a class that ran stays on the schedule.
  const [ahead] = useState(() => Date.parse(o.starts_at) > Date.now());
  // The server's own word for a first date, should the read above have been too early.
  const first = ending === "first" || (end.error instanceof ApiError && end.error.status === 422);
  const endFailed = ending === "failed" || (end.isError && !gone(end.error));
  const row = (id: string, onClick: () => void) => (
    <Row
      label={l10n.getString(id)}
      action
      onClick={() => {
        if (!pending) onClick();
      }}
    />
  );
  return (
    <div className="sheet">
      <h4 className="group-title">
        {plain(l10n.getString("occurrence-this-date", { day: dayName(o.on, locale) }))}
      </h4>
      <div className="list">
        {attendance}
        {o.cancelled === null && (
          <Field label={l10n.getString("occurrence-teacher")}>
            <Select
              value={named?.id ?? ""}
              disabled={pending}
              onChange={(e) => {
                substitute(e.target.value);
              }}
            >
              <option value="">
                {plain(
                  l10n.getString("occurrence-usual-teacher", {
                    name: o.usual_teacher?.name ?? l10n.getString("class-form-no-teacher"),
                  }),
                )}
              </option>
              {named && !shala.staff.some((s) => s.id === named.id) && (
                <option value={named.id}>{named.name ?? l10n.getString("link-no-name")}</option>
              )}
              {shala.staff
                .filter((s) => s.id !== o.usual_teacher?.id)
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name ?? l10n.getString("link-no-name")}
                  </option>
                ))}
            </Select>
          </Field>
        )}
        {o.cancelled === null &&
          !cancelled &&
          row("occurrence-cancel", () => {
            change("cancelled");
          })}
        {(o.cancelled === "moon" || o.cancelled === "closure") &&
          row("occurrence-hold", () => {
            change("held");
          })}
        {(o.cancelled === "cancelled" || o.moved || o.substitute) &&
          row("occurrence-restore", restore)}
        {(cancelled || o.cancelled === "cancelled") && mayTell && row("occurrence-tell", tell)}
      </div>
      <Localized id="occurrence-note">
        <p className="hint small" />
      </Localized>
      {((set.isError && !gone(set.error)) || (clear.isError && !gone(clear.error))) && (
        <Localized id="occurrence-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      <Localized id="occurrence-whole-class">
        <h4 className="group-title" />
      </Localized>
      <div className="list">
        <Row
          label={l10n.getString("class-edit")}
          onClick={() => {
            haptics.selection();
            onEdit(o);
          }}
        />
        {ahead && (
          <Row
            label={l10n.getString("class-end")}
            action
            onClick={() => {
              if (!pending) void endHere();
            }}
          />
        )}
      </div>
      {(first || endFailed) && (
        <Localized id={first ? "class-end-first" : "occurrence-failed"}>
          <p className="hint" role="alert" />
        </Localized>
      )}
    </div>
  );
}
