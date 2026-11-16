import { Localized, useLocalization } from "@fluent/react";
import { useCallback, useEffect, useRef, useState, type SyntheticEvent } from "react";

import {
  ApiError,
  useClasses,
  useCreateClass,
  useDeleteClass,
  useMe,
  useMoonCities,
  useRefreshSchedule,
  useUpdateClass,
  type ClassPatch,
  type ClassSeries,
  type ClassType,
  type Shala,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import {
  backButtonAvailable,
  confirmDestructive,
  haptics,
  mainButtonAvailable,
  useBackButton,
  useMainButton,
} from "../../telegram";
import { Chips } from "../../ui/Chips";
import { Check, DateInput, Field, Select, TextInput, TimeInput } from "../../ui/controls";
import { More } from "../../ui/More";
import { cityName } from "../cityName";
import { labelOf } from "../settings/zones";
import {
  LENGTHS,
  TITLE_MAX,
  appliesFrom,
  bodyOf,
  changed,
  defaultTeacher,
  draftOf,
  endOf,
  hasStarted,
  minutesUntil,
  newDraft,
  problemOf,
  retyped,
  teacherChoices,
  type Draft,
} from "./classForm";
import { CLASS_TYPES, useTypeName } from "./classText";
import { WEEKDAYS, dayName, plain, todayIn, weekdayShort } from "./scheduleText";
import "./shalaCopy";
import "./shala.css";

/** How the form closed: saved (or deleted), or the class was no longer there. */
export type FormResult = "saved" | "gone";

interface Props {
  shala: Shala;
  /** A saved class opened for a change: its id, and the date that was tapped. */
  edit?: { classId: string; date: string } | undefined;
  /** Back, a save, or a class that is gone. */
  onDone: (result?: FormResult) => void;
}

const OTHER = 0; // the "Other" length chip

/** A class, new or saved (SC-02, UI-06 stage 4): a full-screen layer with its own Back. Three
 * things to choose (type, start, days), the rest under "More options". Times are wall clock in
 * the shala's zone; an online class may run in another listed city's (Q124). A change to a
 * weekly class that has run applies from a date, and earlier dates stay (ADR-0048). */
export default function ClassForm({ shala, edit, onDone }: Props) {
  const back = useCallback(() => {
    onDone();
  }, [onDone]);
  useBackButton(back);
  const classes = useClasses(shala.id, edit !== undefined);
  const refresh = useRefreshSchedule(shala.id);
  const saved = edit ? classes.data?.find((c) => c.id === edit.classId) : undefined;
  // Opened for a class that is no longer in the list: say so on the schedule, at once.
  const gone = edit !== undefined && classes.data !== undefined && !saved;
  useEffect(() => {
    if (!gone) return;
    refresh();
    onDone("gone");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, when the class is gone
  }, [gone]);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, []);
  return (
    <main className="screen class-form" aria-busy={edit && !saved && !classes.isError}>
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={back} />
        </Localized>
      )}
      <Localized id={edit ? "class-form-edit-title" : "class-form-new-title"}>
        <h1 ref={heading} tabIndex={-1} />
      </Localized>
      {edit && classes.isError && (
        <Localized id="schedule-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {(!edit || saved) && (
        <Fields shala={shala} saved={saved} tapped={edit?.date} onDone={onDone} />
      )}
    </main>
  );
}

function Fields({
  shala,
  saved,
  tapped,
  onDone,
}: {
  shala: Shala;
  saved: ClassSeries | undefined;
  tapped: string | undefined;
  onDone: (result?: FormResult) => void;
}) {
  const { l10n } = useLocalization();
  const typeName = useTypeName();
  const me = useMe().data;
  const locale: Locale = me?.locale ?? "en";
  const cities = useMoonCities().data;
  const create = useCreateClass(shala.id);
  const update = useUpdateClass(shala.id);
  const remove = useDeleteClass(shala.id);
  const today = todayIn(shala.zone);
  // What the form was filled from: only what differs from it is sent, so a field someone else
  // changed meanwhile stays (ADR-0048). Kept as first read, also after a refetch.
  const [base] = useState(() => (saved ? draftOf(saved, shala) : null));
  const [started] = useState(() => saved !== undefined && hasStarted(saved, today));
  const [draft, setDraft] = useState<Draft>(() => base ?? newDraft(shala, today, ""));
  // Untouched in a new class, the teacher is me when I teach here (my account may load later).
  const [teacher, setTeacher] = useState<string | null>(base ? base.teacher : null);
  const [applies, setApplies] = useState(() => appliesFrom(tapped ?? today, today));
  const [more, setMore] = useState(false);
  const [custom, setCustom] = useState(() => !!base && !LENGTHS.includes(base.minutes));
  const [problem, setProblem] = useState<ReturnType<typeof problemOf>>(null);
  const [focus, setFocus] = useState(0);
  const set = (patch: Partial<Draft>) => {
    setDraft((now) => ({ ...now, ...patch }));
  };
  const now: Draft = { ...draft, teacher: teacher ?? defaultTeacher(shala, me?.id) };
  const isWindow = now.type === "mysore";
  const pending = create.isPending || update.isPending || remove.isPending;

  const start = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLInputElement>(null);
  // A length that does not fit: its field is under "More options", which opens for it.
  useEffect(() => {
    if (focus) (end.current ?? start.current)?.focus();
  }, [focus]);

  const submit = () => {
    if (pending) return;
    const found = problemOf(now);
    setProblem(found);
    if (found) {
      haptics.notify("error");
      if (found === "window") {
        setMore(true);
        setFocus((n) => n + 1);
      }
      return;
    }
    haptics.impact("light");
    const body = bodyOf(now, shala);
    const failed = (error: unknown) => {
      haptics.notify("error");
      // Removed, or changed by someone else from an earlier date: the schedule says which.
      if (saved && error instanceof ApiError && error.status === 404) onDone("gone");
    };
    const done = () => {
      onDone("saved");
    };
    if (!saved || !base) {
      create.mutate(body, { onSuccess: done, onError: failed });
      return;
    }
    const patch: ClassPatch = changed(bodyOf(base, shala), body);
    if (Object.keys(patch).length === 0) {
      onDone();
      return;
    }
    // A class that has run changes from a date, never before the shala's today.
    if (started) patch.from = appliesFrom(applies, today);
    update.mutate({ classId: saved.id, body: patch }, { onSuccess: done, onError: failed });
  };
  // Telegram's main button keeps one listener; it always reaches the newest values.
  const latest = useRef(submit);
  useEffect(() => {
    latest.current = submit;
  });
  const press = useCallback(() => {
    latest.current();
  }, []);
  const save = l10n.getString("class-form-save");
  useMainButton(save, press, pending);

  const removeAll = async () => {
    if (!saved) return;
    const ok = await confirmDestructive(
      l10n.getString("occurrence-delete-ask"),
      l10n.getString("occurrence-delete-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("heavy");
    remove.mutate(saved.id, {
      onSuccess: () => {
        onDone("saved");
      },
    });
  };

  const pickType = (type: ClassType) => {
    haptics.selection();
    // A new class takes the type's usual days and length; a saved one keeps its own.
    setDraft((d) => (saved ? { ...d, type } : retyped(d, type, shala)));
    if (!saved) setCustom(false);
    setProblem(null);
  };
  const toggleDay = (d: number) => {
    haptics.selection();
    setDraft((n) => ({
      ...n,
      days: n.days.includes(d) ? n.days.filter((x) => x !== d) : [...n.days, d],
    }));
    setProblem(null);
  };

  // The start is wall clock where the class runs: another city's zone when online (Q124).
  const runsIn = now.online ? cities?.find((c) => c.slug === now.city) : undefined;
  const elsewhere = runsIn && runsIn.slug !== shala.city.slug ? runsIn : undefined;
  // It labels the start time, so the offset shows only outside my own zone (ADR-0044).
  const zone = runsIn
    ? labelOf(runsIn.timezone, cityName(runsIn, runsIn.slug, locale), me?.timezone)
    : labelOf(shala.zone, shala.city.name, me?.timezone);
  const offDay = !now.once && now.days.some((d) => (shala.days_off ?? []).includes(d));
  const staff = teacherChoices(shala.staff);
  const person = (s: Shala["staff"][number]) => s.name ?? l10n.getString("link-no-name");
  const named = staff.find((s) => s.id === now.teacher);
  const everyN = (n: number) => plain(l10n.getString("class-form-every-n", { n }));
  const minutesChip = (minutes: number) =>
    plain(l10n.getString("class-form-length-chip", { minutes }));
  const windowError = problem === "window" && l10n.getString("class-form-window-invalid");
  const endField = isWindow || custom;
  // One line for what is set under "More options".
  const summary = [
    isWindow
      ? plain(l10n.getString("class-form-sum-until", { time: endOf(now) }))
      : plain(l10n.getString("class-form-sum-length", { minutes: now.minutes })),
    now.title.trim(),
    named && person(named),
    !now.once && now.every > 1 && everyN(now.every),
    !now.once &&
      !started &&
      now.from !== today &&
      plain(l10n.getString("class-form-sum-from", { date: dayName(now.from, locale) })),
    !now.once &&
      now.end &&
      plain(l10n.getString("class-form-sum-end", { date: dayName(now.end, locale) })),
    now.online &&
      [
        l10n.getString("class-form-online"),
        elsewhere && cityName(elsewhere, elsewhere.slug, locale),
      ]
        .filter(Boolean)
        .join(" "),
  ]
    .filter(Boolean)
    .join(" · ");
  const failed = create.isError || update.isError;
  const capped = create.error instanceof ApiError && create.error.code === "class_caps";

  return (
    <form
      className="form"
      noValidate
      onSubmit={(e: SyntheticEvent) => {
        e.preventDefault();
        submit();
      }}
    >
      <Chips
        label={l10n.getString("class-form-type")}
        options={CLASS_TYPES.map((t) => ({ value: t, label: typeName(t) }))}
        value={now.type}
        onPick={pickType}
      />
      <Field
        label={plain(l10n.getString("class-form-start", { zone }))}
        error={!endField && windowError}
      >
        <TimeInput
          ref={start}
          value={now.start}
          onChange={(e) => {
            set({ start: e.target.value }); // the length stays, so the end moves with it
            setProblem(null);
          }}
        />
      </Field>
      {now.once ? (
        <Field label={l10n.getString("class-form-date")}>
          <DateInput
            value={now.date}
            onChange={(e) => {
              set({ date: e.target.value });
            }}
          />
        </Field>
      ) : (
        <Chips
          label={l10n.getString("class-form-days")}
          options={WEEKDAYS.map((d) => ({
            value: d,
            label: weekdayShort(d, locale),
            name: l10n.getString("day-off-weekday", { d }),
          }))}
          value={now.days}
          onPick={toggleDay}
          hint={
            offDay
              ? l10n.getString("class-form-day-off-warning")
              : now.type === "led"
                ? l10n.getString("class-led-hint")
                : undefined
          }
          error={problem === "days" && l10n.getString("class-form-days-needed")}
        />
      )}
      {!saved && (
        <Localized id={now.once ? "class-form-weekly" : "class-form-once"}>
          <button
            type="button"
            className="link tap once"
            onClick={() => {
              haptics.selection();
              set({ once: !now.once });
              setProblem(null);
            }}
          />
        </Localized>
      )}
      {started && (
        <Field
          label={l10n.getString("class-form-applies")}
          hint={
            elsewhere
              ? plain(l10n.getString("class-form-applies-zone", { zone }))
              : l10n.getString("class-form-applies-hint")
          }
        >
          <DateInput
            value={applies}
            min={today}
            onChange={(e) => {
              setApplies(e.target.value);
            }}
          />
        </Field>
      )}
      <More
        label={l10n.getString("class-form-more")}
        summary={summary}
        open={more}
        onToggle={() => {
          haptics.selection();
          setMore(!more);
        }}
      >
        {!isWindow && (
          <Chips
            label={l10n.getString("class-form-length")}
            options={[
              ...LENGTHS.map((m) => ({ value: m, label: minutesChip(m) })),
              { value: OTHER, label: l10n.getString("class-form-length-other") },
            ]}
            value={custom ? OTHER : now.minutes}
            onPick={(minutes) => {
              haptics.selection();
              setCustom(minutes === OTHER);
              if (minutes !== OTHER) set({ minutes });
              setProblem(null);
            }}
          />
        )}
        {endField && (
          <Field
            label={l10n.getString(isWindow ? "class-form-until" : "class-form-ends")}
            error={windowError}
          >
            <TimeInput
              ref={end}
              value={endOf(now)}
              onChange={(e) => {
                set({ minutes: minutesUntil(now.start, e.target.value) });
                setProblem(null);
              }}
            />
          </Field>
        )}
        <Field label={l10n.getString("class-form-title")}>
          <TextInput
            value={now.title}
            maxLength={TITLE_MAX}
            onChange={(e) => {
              set({ title: e.target.value });
            }}
          />
        </Field>
        <Field label={l10n.getString("class-form-teacher")}>
          <Select
            value={now.teacher}
            onChange={(e) => {
              setTeacher(e.target.value);
            }}
          >
            <option value="">{l10n.getString("class-form-no-teacher")}</option>
            {staff.map((s) => (
              <option key={s.id} value={s.id}>
                {person(s)}
              </option>
            ))}
          </Select>
        </Field>
        {!now.once && (
          <Field label={l10n.getString("class-form-every")}>
            <Select
              value={now.every}
              onChange={(e) => {
                set({ every: Number(e.target.value) });
              }}
            >
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {everyN(n)}
                </option>
              ))}
            </Select>
          </Field>
        )}
        {!now.once && !started && (
          <Field label={l10n.getString("class-form-from")}>
            <DateInput
              value={now.from}
              onChange={(e) => {
                set({ from: e.target.value });
              }}
            />
          </Field>
        )}
        {!now.once && (
          <Field label={l10n.getString("class-form-end")}>
            <DateInput
              value={now.end}
              min={started ? applies : now.from}
              onChange={(e) => {
                set({ end: e.target.value });
              }}
            />
          </Field>
        )}
        <Check
          label={l10n.getString("class-form-online")}
          checked={now.online}
          onChange={() => {
            set({ online: !now.online });
          }}
        />
        {now.online && (
          <Field label={l10n.getString("class-form-zone")}>
            <Select
              value={now.city}
              onChange={(e) => {
                set({ city: e.target.value });
              }}
            >
              {cities?.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {cityName(c, c.slug, locale)}
                </option>
              ))}
            </Select>
          </Field>
        )}
      </More>
      {!problem && (failed || remove.isError) && (
        <Localized
          id={
            remove.isError ? "occurrence-failed" : capped ? "class-form-caps" : "class-form-failed"
          }
        >
          <p className="field-error" role="alert" />
        </Localized>
      )}
      {!mainButtonAvailable() && (
        <button type="submit" className="btn" disabled={pending}>
          {save}
        </button>
      )}
      {saved && (
        <Localized id="occurrence-delete">
          <button
            type="button"
            className="link danger tap delete"
            disabled={pending}
            onClick={() => {
              void removeAll();
            }}
          />
        </Localized>
      )}
    </form>
  );
}
