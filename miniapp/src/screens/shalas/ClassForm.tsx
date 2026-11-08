import { Localized, useLocalization } from "@fluent/react";
import { useState, type SyntheticEvent } from "react";

import {
  ApiError,
  useCreateClass,
  useMe,
  useMoonCities,
  type ClassType,
  type Shala,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { haptics } from "../../telegram";
import { cityName } from "../MoonCard";
import { labelOf } from "../settings/zones";
import { WEEKDAYS, hmOf, minutesOf, plain, todayIn } from "./scheduleText";

export const CLASS_TYPES: ClassType[] = [
  "mysore",
  "led",
  "private",
  "conference",
  "pranayama",
  "chanting",
  "workshop",
];
const CONTEXT: Partial<Record<ClassType, string>> = {
  mysore: "context-mysore",
  led: "context-led",
  private: "context-private",
};
const DAY_MINUTES = 24 * 60;
const TITLE_MAX = 48;

/** Mysore, Led and 1:1 reuse the practice words; the rest have their own. */
export function useTypeName() {
  const { l10n } = useLocalization();
  return (type: ClassType) => {
    const context = CONTEXT[type];
    return context ? l10n.getString(context) : l10n.getString("class-type", { type });
  };
}

/** Mysore starts with every day but the shala's day off; other types with none (expert). */
const presetDays = (type: ClassType, shala: Shala): number[] =>
  type === "mysore" ? WEEKDAYS.filter((d) => !(shala.days_off ?? []).includes(d)) : [];

interface Props {
  shala: Shala;
  onDone: () => void;
}

/** A new class (SC-02, Q103: forms are in the Mini App). Times are wall clock in the shala's
 * zone; an online class may run in another listed city's (Q124). */
export default function ClassForm({ shala, onDone }: Props) {
  const { l10n } = useLocalization();
  const typeName = useTypeName();
  const locale: Locale = useMe().data?.locale ?? "en";
  const cities = useMoonCities().data;
  const create = useCreateClass(shala.id);
  const [type, setType] = useState<ClassType>("mysore");
  const [title, setTitle] = useState("");
  const [teacher, setTeacher] = useState("");
  const [start, setStart] = useState("06:00");
  const [until, setUntil] = useState("09:30");
  const [minutes, setMinutes] = useState(90);
  const [days, setDays] = useState<number[]>(() => presetDays("mysore", shala));
  const [every, setEvery] = useState(1);
  const [from, setFrom] = useState(() => todayIn(shala.zone));
  const [end, setEnd] = useState("");
  const [online, setOnline] = useState(false);
  const [city, setCity] = useState(shala.city.slug);
  const [invalid, setInvalid] = useState(false);
  const isWindow = type === "mysore";
  const teachers = shala.staff.filter(
    (s) => s.roles.includes("teacher") || s.roles.includes("assistant"),
  );
  const pick = (next: ClassType) => {
    haptics.selection();
    setType(next);
    setDays(presetDays(next, shala));
  };
  const toggle = (d: number) => {
    setDays((now) => (now.includes(d) ? now.filter((x) => x !== d) : [...now, d]));
  };
  const length = isWindow ? minutesOf(until) - minutesOf(start) : minutes;
  const submit = (e: SyntheticEvent) => {
    e.preventDefault();
    if (length < 15 || length > 480 || minutesOf(start) + length > DAY_MINUTES) {
      setInvalid(true);
      haptics.notify("error");
      return;
    }
    setInvalid(false);
    haptics.impact("light");
    create.mutate(
      {
        type,
        title: title.trim() || null,
        online,
        city: online && city !== shala.city.slug ? city : null,
        teacher_id: teacher || null,
        start: hmOf(minutesOf(start)),
        minutes: length,
        weekdays: [...days].sort((a, b) => a - b),
        every: days.length > 0 ? every : 1,
        starts_on: from,
        ends_on: days.length > 0 && end ? end : null,
      },
      {
        onSuccess: onDone,
        onError: () => {
          haptics.notify("error");
        },
      },
    );
  };
  // The start is wall clock where the class runs: another city's zone when online (Q124).
  const runsIn = online ? cities?.find((c) => c.slug === city) : undefined;
  const zone = runsIn
    ? labelOf(runsIn.timezone, cityName(runsIn, runsIn.slug, locale))
    : labelOf(shala.zone, shala.city.name);
  const offDay = days.some((d) => (shala.days_off ?? []).includes(d));
  const capped = create.error instanceof ApiError && create.error.code === "class_caps";
  return (
    <form className="card shala-form" onSubmit={submit}>
      <Localized id="class-form-type">
        <p className="label" />
      </Localized>
      <div className="chips">
        {CLASS_TYPES.map((t) => (
          <button
            key={t}
            type="button"
            className="chip"
            aria-pressed={t === type}
            onClick={() => {
              pick(t);
            }}
          >
            {typeName(t)}
          </button>
        ))}
      </div>
      {type === "led" && (
        <Localized id="class-led-hint">
          <p className="hint small" />
        </Localized>
      )}
      <label className="label">
        <Localized id="class-form-title">
          <span />
        </Localized>
        <input
          type="text"
          value={title}
          maxLength={TITLE_MAX}
          onChange={(e) => {
            setTitle(e.target.value);
          }}
        />
      </label>
      <label className="label">
        <Localized id="class-form-teacher">
          <span />
        </Localized>
        <select
          value={teacher}
          onChange={(e) => {
            setTeacher(e.target.value);
          }}
        >
          <Localized id="class-form-no-teacher">
            <option value="" />
          </Localized>
          {teachers.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name ?? l10n.getString("link-no-name")}
            </option>
          ))}
        </select>
      </label>
      <label className="label">
        <span>{plain(l10n.getString("class-form-start", { zone }))}</span>
        <input
          type="time"
          value={start}
          required
          onChange={(e) => {
            setStart(e.target.value);
          }}
        />
      </label>
      {isWindow ? (
        <label className="label">
          <Localized id="class-form-until">
            <span />
          </Localized>
          <input
            type="time"
            value={until}
            required
            onChange={(e) => {
              setUntil(e.target.value);
            }}
          />
        </label>
      ) : (
        <label className="label">
          <Localized id="class-form-length">
            <span />
          </Localized>
          <input
            type="number"
            min={15}
            max={480}
            step={5}
            value={minutes}
            onChange={(e) => {
              setMinutes(Number(e.target.value));
            }}
          />
        </label>
      )}
      <fieldset className="weekdays">
        <Localized id="class-form-days">
          <legend className="label" />
        </Localized>
        {WEEKDAYS.map((d) => (
          <label key={d} className="toggle">
            <input
              type="checkbox"
              checked={days.includes(d)}
              onChange={() => {
                toggle(d);
              }}
            />
            {l10n.getString("day-off-weekday", { d })}
          </label>
        ))}
      </fieldset>
      {offDay && (
        <Localized id="class-form-day-off-warning">
          <p className="hint small" />
        </Localized>
      )}
      {days.length > 0 && (
        <label className="label">
          <Localized id="class-form-every">
            <span />
          </Localized>
          <select
            value={every}
            onChange={(e) => {
              setEvery(Number(e.target.value));
            }}
          >
            {[1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>
                {plain(l10n.getString("class-form-every-n", { n }))}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="label">
        <Localized id="class-form-from">
          <span />
        </Localized>
        <input
          type="date"
          value={from}
          required
          onChange={(e) => {
            setFrom(e.target.value);
          }}
        />
      </label>
      {days.length > 0 && (
        <label className="label">
          <Localized id="class-form-end">
            <span />
          </Localized>
          <input
            type="date"
            value={end}
            min={from}
            onChange={(e) => {
              setEnd(e.target.value);
            }}
          />
        </label>
      )}
      <label className="toggle">
        <input
          type="checkbox"
          checked={online}
          onChange={() => {
            setOnline(!online);
          }}
        />
        {l10n.getString("class-form-online")}
      </label>
      {online && (
        <label className="label">
          <Localized id="class-form-zone">
            <span />
          </Localized>
          <select
            value={city}
            onChange={(e) => {
              setCity(e.target.value);
            }}
          >
            {cities?.map((c) => (
              <option key={c.slug} value={c.slug}>
                {cityName(c, c.slug, locale)}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="actions">
        <Localized id="class-form-save">
          <button type="submit" className="row-button" disabled={create.isPending} />
        </Localized>
        <Localized id="class-form-cancel">
          <button type="button" className="link" onClick={onDone} />
        </Localized>
      </div>
      {(invalid || create.isError) && (
        <Localized
          id={
            invalid ? "class-form-window-invalid" : capped ? "class-form-caps" : "class-form-failed"
          }
        >
          <p className="hint" role="alert" />
        </Localized>
      )}
    </form>
  );
}
