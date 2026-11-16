import { Localized, useLocalization } from "@fluent/react";
import { Suspense, useState, type ReactNode } from "react";

import {
  useClearOccurrence,
  useSetOccurrence,
  type Occurrence,
  type OccurrenceChange,
  type Shala,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { lazyRetry } from "../../shell/lazyRetry";
import { haptics } from "../../telegram";
import { Field, Select } from "../../ui/controls";
import { Row } from "../Row";
import { timeLabel } from "../timeLabel";
import { lengthOf, useTypeName } from "./classText";
import { dateIn, dayName, plain, timeIn } from "./scheduleText";
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
  /** "Tell students…": the announcement, with this text to start from (Q338). */
  onTell: (draft: string) => void;
}

/** Staff on one occurrence: attendance (any staff seat, SC-05); and for those who manage
 * classes two headed groups (UI-06 stage 4). "This date": substitute, cancel, hold anyway
 * (auto-cancelled only, Q126), restore. "The whole class": change it; deleting it is in that
 * form, so nothing here touches another date. */
export default function OccurrenceSheet({
  shala,
  occurrence: o,
  locale,
  onDone,
  onEdit,
  onTell,
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
  attendance,
}: Props & { attendance: ReactNode }) {
  const { l10n } = useLocalization();
  const typeName = useTypeName();
  const set = useSetOccurrence(shala.id);
  const clear = useClearOccurrence(shala.id);
  // Cancelled here, a moment ago: the one time "Tell students…" is offered (Q338).
  const [cancelled, setCancelled] = useState(false);
  // Never for a 1:1 (Q121: it names a person's class to the whole shala).
  const mayTell = shala.me.announce && o.type !== "private";
  const target = { classId: o.class_id, key: o.key };
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
      },
    );
  };
  const restore = () => {
    haptics.impact("light");
    clear.mutate(target, { onSuccess: onDone });
  };
  // "Usual teacher" names no one for the date: it follows the class's teacher.
  const substitute = (teacher: string) => {
    haptics.impact("light");
    const body = { ...kept(), teacher_id: teacher || null };
    set.mutate({ ...target, body }, { onSuccess: onDone });
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
  const pending = set.isPending || clear.isPending;
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
        {cancelled && mayTell && row("occurrence-tell", tell)}
      </div>
      <Localized id="occurrence-note">
        <p className="hint small" />
      </Localized>
      {(set.isError || clear.isError) && (
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
      </div>
    </div>
  );
}
