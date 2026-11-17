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
  disableClosingConfirmation,
  enableClosingConfirmation,
  haptics,
  mainButtonAvailable,
  useBackButton,
  useMainButton,
} from "../../telegram";
import { Chips } from "../../ui/Chips";
import {
  Check,
  DateInput,
  Field,
  NumberInput,
  Select,
  TextInput,
  TimeInput,
} from "../../ui/controls";
import { More } from "../../ui/More";
import { cityName } from "../cityName";
import { labelOf } from "../settings/zones";
import {
  LENGTHS,
  TITLE_MAX,
  appliesFrom,
  bodyOf,
  changed,
  defaultFrom,
  defaultTeacher,
  draftOf,
  endOf,
  hasStarted,
  minutesUntil,
  newDraft,
  problemOf,
  retyped,
  runsOn,
  teacherChoices,
  type Draft,
  type Problem,
} from "./classForm";
import { CLASS_TYPES, useTypeName } from "./classText";
import { WEEKDAYS, dayName, fullDate, plain, timeIn, todayIn, weekdayShort } from "./scheduleText";
import "./shalaCopy";
import "./shala.css";

/** How the form closed: saved (or deleted), or the class was no longer there. */
export type FormResult = "saved" | "gone";

/** A saved class opened for a change: its id, the date that was tapped, and when that date's
 * class begins (an instant), so a class that has already begun today is left as it ran. */
export interface ClassEdit {
  classId: string;
  date: string;
  startsAt?: string | undefined;
}

interface Props {
  shala: Shala;
  edit?: ClassEdit | undefined;
  /** Back, a save, or a class that is gone. */
  onDone: (result?: FormResult) => void;
}

const OTHER = 0; // the "Other" length chip
const WEEKLY = "weekly";
const ONCE = "once";

/** A class, new or saved (SC-02, UI-06 stage 4): a full-screen layer with its own Back. Three
 * things to choose (type, start, days), the rest under "More options". Times are wall clock in
 * the shala's zone; an online class may run in another listed city's (Q124). A change to a
 * weekly class that has run applies from a date, and earlier dates stay (ADR-0048). */
export default function ClassForm({ shala, edit, onDone }: Props) {
  const { l10n } = useLocalization();
  // Whether something was typed and not saved: Back asks before it is dropped.
  const dirty = useRef(false);
  const back = useCallback(() => {
    if (!dirty.current) {
      onDone();
      return;
    }
    confirmDestructive(
      l10n.getString("class-form-discard-ask"),
      l10n.getString("class-form-discard-yes"),
      l10n.getString("class-form-discard-no"),
    )
      .then((discard) => {
        if (discard) onDone();
      })
      .catch(() => undefined); // a second press while the popup is open: it is still asking
  }, [onDone, l10n]);
  useBackButton(back);
  const classes = useClasses(shala.id, edit !== undefined);
  const refresh = useRefreshSchedule(shala.id);
  // The class as first read by this form, from a list fetched after the form opened: a list
  // left in the cache by an earlier visit may lack a class added since. Read once: what the
  // list says later (after my own save or delete) is no news about the class I opened.
  const fresh = classes.isSuccess && classes.isFetchedAfterMount && !classes.isFetching;
  const [saved, setSaved] = useState<ClassSeries | null>();
  if (edit && saved === undefined && fresh)
    setSaved(classes.data.find((c) => c.id === edit.classId) ?? null);
  // Opened for a class that is no longer in the list: say so on the schedule, at once.
  const gone = saved === null;
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
  const noted = useCallback((changedNow: boolean) => {
    dirty.current = changedNow;
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
        <Fields
          shala={shala}
          saved={saved ?? undefined}
          edit={edit}
          onDirty={noted}
          onDone={onDone}
        />
      )}
    </main>
  );
}

/** Whether the class on the date a change would start from has already begun. The tapped
 * date's own instant when it is that date; else the rule's wall clock in the shala's zone. */
function hasBegun(
  c: ClassSeries,
  edit: ClassEdit | undefined,
  today: string,
  zone: string,
): boolean {
  const tapped = edit?.date ?? today;
  if (tapped > today) return false;
  if (tapped === today && edit?.startsAt) return Date.parse(edit.startsAt) <= Date.now();
  return runsOn(c, today) && c.start.slice(0, 5) <= timeIn(new Date().toISOString(), zone);
}

function Fields({
  shala,
  saved,
  edit,
  onDirty,
  onDone,
}: {
  shala: Shala;
  saved: ClassSeries | undefined;
  edit: ClassEdit | undefined;
  onDirty: (dirty: boolean) => void;
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
  // changed meanwhile stays (ADR-0048).
  const [base] = useState(() => (saved ? draftOf(saved, shala) : null));
  const [started] = useState(() => saved !== undefined && hasStarted(saved, today));
  const [first] = useState<Draft>(() => base ?? newDraft(shala, today, ""));
  const [draft, setDraft] = useState<Draft>(first);
  // Untouched in a new class, the teacher is me when I teach here (my account may load later).
  const [teacher, setTeacher] = useState<string | null>(base ? base.teacher : null);
  const [proposed] = useState(() =>
    saved
      ? defaultFrom(saved, edit?.date ?? today, today, hasBegun(saved, edit, today, shala.zone))
      : today,
  );
  const [applies, setApplies] = useState(proposed);
  // "Another date": the field behind the sentence.
  const [another, setAnother] = useState(false);
  const [more, setMore] = useState(false);
  const [custom, setCustom] = useState(() => !!base && !LENGTHS.includes(base.minutes));
  // The "Other" length as typed: it may be empty for a moment.
  const [typed, setTyped] = useState(() => String(first.minutes));
  const [problem, setProblem] = useState<Problem | null>(null);
  const [focus, setFocus] = useState<{ on: "length" | "last" | "applies"; n: number } | null>(null);
  const set = (patch: Partial<Draft>) => {
    setDraft((now) => ({ ...now, ...patch }));
  };
  const now: Draft = { ...draft, teacher: teacher ?? defaultTeacher(shala, me?.id) };
  const isWindow = now.type === "mysore";
  const pending = create.isPending || update.isPending || remove.isPending;
  // One press, one request: a second press before the screen redraws still sees no `pending`.
  const sending = useRef(false);

  const dirty = draft !== first || teacher !== (base ? base.teacher : null) || applies !== proposed;
  useEffect(() => {
    onDirty(dirty);
    if (!dirty) return;
    enableClosingConfirmation();
    return () => {
      disableClosingConfirmation();
    };
  }, [dirty, onDirty]);

  const start = useRef<HTMLInputElement>(null);
  const length = useRef<HTMLInputElement>(null);
  const last = useRef<HTMLInputElement>(null);
  const from = useRef<HTMLInputElement>(null);
  // A field that stopped the save, or one just brought into the form, takes the focus (the
  // ones under "More options" are there only once it is open).
  useEffect(() => {
    if (!focus) return;
    const field =
      focus.on === "last" ? last.current : focus.on === "applies" ? from.current : length.current;
    (field ?? start.current)?.focus();
  }, [focus]);
  const focusOn = (on: "length" | "last" | "applies") => {
    setFocus((was) => ({ on, n: (was?.n ?? 0) + 1 }));
  };

  const submit = () => {
    if (pending || sending.current) return;
    const found = problemOf(now, started ? appliesFrom(applies, today) : null);
    setProblem(found);
    if (found) {
      haptics.notify("error");
      if (found !== "days") {
        setMore(true);
        focusOn(found === "end" ? "last" : "length");
      }
      return;
    }
    haptics.impact("light");
    const body = bodyOf(now, shala);
    const settled = () => {
      sending.current = false;
    };
    const failed = (error: unknown) => {
      haptics.notify("error");
      // Removed, or changed by someone else from an earlier date: the schedule says which.
      if (saved && error instanceof ApiError && error.status === 404) onDone("gone");
    };
    const done = () => {
      onDone("saved");
    };
    if (!saved || !base) {
      sending.current = true;
      create.mutate(body, { onSuccess: done, onError: failed, onSettled: settled });
      return;
    }
    const patch: ClassPatch = changed(bodyOf(base, shala), body);
    if (Object.keys(patch).length === 0) {
      onDone();
      return;
    }
    // A class that has run changes from a date, never before the shala's today.
    if (started) patch.from = appliesFrom(applies, today);
    sending.current = true;
    update.mutate(
      { classId: saved.id, body: patch },
      { onSuccess: done, onError: failed, onSettled: settled },
    );
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
    // A class with a last date: the dates that go, by name. What comes after them (a later
    // change of the same class is a class of its own) stays, and the question says so.
    const ask = saved.ends_on
      ? plain(
          l10n.getString("class-delete-ask-range", {
            from: fullDate(saved.starts_on, locale),
            to: fullDate(saved.ends_on, locale),
          }),
        )
      : l10n.getString("occurrence-delete-ask");
    const ok = await confirmDestructive(
      ask,
      l10n.getString("occurrence-delete-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok || sending.current) return;
    haptics.impact("heavy");
    sending.current = true;
    remove.mutate(saved.id, {
      onSuccess: () => {
        onDone("saved");
      },
      onSettled: () => {
        sending.current = false;
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
  const endError =
    problem === "end" &&
    l10n.getString(started ? "class-form-end-before-applies" : "class-form-end-early");
  // What stays, and how far the change reaches when the class has a last date: the second
  // part of the sentence, and the date field's hint.
  const reach = [
    elsewhere
      ? plain(l10n.getString("class-form-applies-zone", { zone }))
      : l10n.getString("class-form-applies-hint"),
    now.end && plain(l10n.getString("class-form-applies-last", { date: dayName(now.end, locale) })),
  ]
    .filter(Boolean)
    .join(" ");
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
        error={!isWindow && !custom && windowError}
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
      {!saved && (
        <Chips
          label={l10n.getString("class-form-when")}
          options={[
            { value: WEEKLY, label: l10n.getString("class-form-weekly") },
            { value: ONCE, label: l10n.getString("class-form-once") },
          ]}
          value={now.once ? ONCE : WEEKLY}
          onPick={(kind) => {
            haptics.selection();
            set({ once: kind === ONCE });
            setProblem(null);
          }}
        />
      )}
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
      {started &&
        (another ? (
          <Field label={l10n.getString("class-form-applies")} hint={reach}>
            <DateInput
              ref={from}
              value={applies}
              min={today}
              onChange={(e) => {
                setApplies(e.target.value);
                setProblem(null);
              }}
            />
          </Field>
        ) : (
          <div className="applies">
            <p>
              {plain(
                l10n.getString("class-form-applies-on", {
                  date: dayName(appliesFrom(applies, today), locale),
                }),
              )}{" "}
              {reach}
            </p>
            <Localized id="class-form-applies-other">
              <button
                type="button"
                className="link tap"
                onClick={() => {
                  haptics.selection();
                  setAnother(true);
                  focusOn("applies");
                }}
              />
            </Localized>
          </div>
        ))}
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
              if (minutes === OTHER) setTyped(String(now.minutes));
              else set({ minutes });
              setProblem(null);
            }}
          />
        )}
        {isWindow && (
          <Field label={l10n.getString("class-form-until")} error={windowError}>
            <TimeInput
              ref={length}
              value={endOf(now)}
              onChange={(e) => {
                set({ minutes: minutesUntil(now.start, e.target.value) });
                setProblem(null);
              }}
            />
          </Field>
        )}
        {!isWindow && custom && (
          <Field
            label={l10n.getString("class-form-minutes")}
            error={problem === "window" && l10n.getString("class-form-minutes-invalid")}
          >
            <NumberInput
              ref={length}
              value={typed}
              min={15}
              max={480}
              step={5}
              suffix={l10n.getString("class-form-min")}
              onChange={(e) => {
                setTyped(e.target.value);
                // Not a whole number yet (empty, "1."): no length, and that does not save.
                set({ minutes: /^\d+$/.test(e.target.value) ? Number(e.target.value) : 0 });
                setProblem(null);
              }}
            />
          </Field>
        )}
        <Field label={l10n.getString("class-form-title")}>
          <TextInput
            value={now.title}
            maxLength={TITLE_MAX}
            placeholder={l10n.getString("class-form-title-example")}
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
                setProblem(null);
              }}
            />
          </Field>
        )}
        {!now.once && (
          <Field label={l10n.getString("class-form-end")} error={endError}>
            <DateInput
              ref={last}
              value={now.end}
              min={started ? applies : now.from}
              onChange={(e) => {
                set({ end: e.target.value });
                setProblem(null);
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
