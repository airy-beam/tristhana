import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import {
  useCatalog,
  useDismissNewAsanaHint,
  useMe,
  usePracticePresets,
  useProgression,
  useProgressionEvent,
  useSavePractice,
  type Catalog,
  type Length,
  type Practice,
  type PracticeBody,
  type PracticeContext,
} from "../api/client";
import type { Locale } from "../i18n/negotiate";
import { haptics } from "../telegram";
import {
  lengthOf,
  lengthText,
  rangeOf,
  rangeText,
  sameLength,
  zoneLabel,
  type Range,
} from "./practiceText";
import { CelebrationCard } from "./progression/CelebrationCard";
import { placeFor } from "./settings/zones";
import { celebrationLines, get, stopLabel } from "./progression/progressionText";

const CONTEXTS: readonly PracticeContext[] = ["mysore", "led", "private", "self"];
const DURATIONS = [30, 45, 60, 75, 90, 120, 150, 180];
const STATIC_LABELS: Record<string, string> = {
  short: "preset-short",
  half_primary: "preset-half-primary",
  full_primary: "preset-full-primary",
};

interface Props {
  date: string;
  practice: Practice | null;
  /** The account's IANA zone; the start time is offered only when it is known. */
  zone: string | null;
  locale: Locale;
}

/** Details of today's practice (PR-02 context, PR-03 length, PR-05 duration and start). */
export function PracticeDetails({ date, practice, zone, locale }: Props) {
  const { l10n } = useLocalization();
  const me = useMe().data; // cached: the home city for the time label (MD-04)
  const catalog = useCatalog().data;
  const presets = usePracticePresets(date, true).data;
  const save = useSavePractice();
  const [custom, setCustom] = useState(false);
  // PR-08: "New asana? 🎉" after a length change past the last asana (the PUT's answer).
  const [hint, setHint] = useState<{ series: string; last: string } | null>(null);

  const current: PracticeBody = {
    context: practice?.context ?? null,
    online: practice?.online ?? false,
    length: practice?.length ?? null,
    duration_min: practice?.duration_min ?? null,
    start_time: practice?.start_time?.slice(0, 5) ?? null,
  };
  const update = (change: Partial<PracticeBody>) => {
    haptics.impact("light");
    const body = { ...current, ...change };
    if (body.context === "self") body.online = false;
    save.mutate(
      { date, body },
      {
        onSuccess: (saved) => {
          if (saved?.new_asana_hint) setHint(saved.new_asana_hint);
          else if ("length" in change) setHint(null);
        },
        onError: () => {
          haptics.notify("error");
        },
      },
    );
  };
  const last = presets?.last;
  const hasDetails =
    !!current.context || !!current.length || !!current.duration_min || !!current.start_time;

  return (
    <div className="details">
      <Localized id="practice-title">
        <h3 />
      </Localized>
      {last && !current.length && (
        <Localized id="practice-same-as-last">
          <button
            type="button"
            className="chip"
            onClick={() => {
              update({
                context: last.context ?? null,
                online: last.online,
                length: last.length ?? null,
                duration_min: last.duration_min ?? null,
              });
            }}
          />
        </Localized>
      )}
      <div className="chips" role="group">
        {CONTEXTS.map((c) => (
          <Localized key={c} id={`context-${c}`}>
            <button
              type="button"
              className="chip"
              aria-pressed={current.context === c}
              onClick={() => {
                update({ context: current.context === c ? null : c });
              }}
            />
          </Localized>
        ))}
        {current.context && current.context !== "self" && (
          <Localized id="practice-online">
            <button
              type="button"
              className="chip"
              aria-pressed={current.online}
              onClick={() => {
                update({ online: !current.online });
              }}
            />
          </Localized>
        )}
      </div>

      <Localized id="practice-length">
        <p className="label" />
      </Localized>
      <div className="chips" role="group">
        {presets?.presets.map((p) => {
          const text = catalog ? lengthText(l10n, catalog, p.length, locale) : "";
          const label =
            STATIC_LABELS[p.kind] !== undefined
              ? get(l10n, STATIC_LABELS[p.kind] ?? "")
              : p.kind === "mine"
                ? get(l10n, "preset-mine", { length: text })
                : text;
          return (
            <button
              key={`${p.kind}:${p.length.series.join()}:${p.length.end ?? ""}:${p.length.first_part ?? ""}`}
              type="button"
              className="chip"
              aria-pressed={sameLength(current.length, p.length)}
              onClick={() => {
                update({ length: p.length });
              }}
            >
              {label}
            </button>
          );
        })}
        <Localized id="preset-other">
          <button
            type="button"
            className="chip"
            aria-expanded={custom}
            onClick={() => {
              setCustom(!custom);
            }}
          />
        </Localized>
      </div>
      {custom && catalog && (
        <CustomLength
          catalog={catalog}
          value={current.length ?? null}
          locale={locale}
          onChange={(length) => {
            update({ length });
          }}
        />
      )}
      {current.length &&
        catalog &&
        !presets?.presets.some((p) => sameLength(p.length, current.length)) && (
          <p className="hint">{lengthText(l10n, catalog, current.length, locale)}</p>
        )}
      {hint && catalog && (
        <NewAsanaQuestion
          date={date}
          target={hint}
          catalog={catalog}
          locale={locale}
          onDone={() => {
            setHint(null);
          }}
        />
      )}

      <Localized id="practice-duration">
        <p className="label" />
      </Localized>
      <div className="chips" role="group">
        {DURATIONS.map((m) => (
          <Localized key={m} id="duration-min" vars={{ min: m }}>
            <button
              type="button"
              className="chip"
              aria-pressed={current.duration_min === m}
              onClick={() => {
                update({ duration_min: current.duration_min === m ? null : m });
              }}
            />
          </Localized>
        ))}
      </div>

      {zone && (
        <StartTime
          key={current.start_time ?? ""} // a new saved value resets the draft
          value={current.start_time ?? null}
          zone={practice?.timezone ?? zone}
          place={placeFor(me?.home_city, practice?.timezone ?? zone, locale)}
          date={date}
          onCommit={(start_time) => {
            if (start_time !== current.start_time) update({ start_time });
          }}
        />
      )}

      {hasDetails && (
        <Localized id="practice-clear">
          <button
            type="button"
            className="link"
            onClick={() => {
              haptics.impact("light");
              save.mutate({ date, body: null });
            }}
          />
        </Localized>
      )}
    </div>
  );
}

/** One tap: "Yes, new" gives the stop on that day (a celebration replaces the question);
 * "Not new" is remembered until the position changes. Never automatic. */
function NewAsanaQuestion({
  date,
  target,
  catalog,
  locale,
  onDone,
}: {
  date: string;
  target: { series: string; last: string };
  catalog: Catalog;
  locale: Locale;
  onDone: () => void;
}) {
  const { l10n } = useLocalization();
  const progression = useProgression();
  const give = useProgressionEvent();
  const dismiss = useDismissNewAsanaHint();
  const [lines, setLines] = useState<string[] | null>(null);
  const asana = stopLabel(catalog, target, locale);
  if (lines) {
    return <CelebrationCard lines={lines} onDismiss={onDone} />;
  }
  return (
    <div className="new-asana" role="group">
      <p>{get(l10n, "progression-ask-new", { asana })}</p>
      <div className="chips">
        <Localized id="progression-ask-yes">
          <button
            type="button"
            className="chip"
            disabled={!progression.data || give.isPending}
            onClick={() => {
              haptics.impact("light");
              give.mutate(
                {
                  kind: "given",
                  ...target,
                  occurred_on: date,
                  expected_event_id: progression.data?.last_event_id ?? null,
                },
                {
                  onSuccess: (done) => {
                    const found = celebrationLines(l10n, catalog, done.celebrations, locale);
                    if (found.length) haptics.notify("success");
                    setLines(found.length ? found : [get(l10n, "progression-back", { asana })]);
                  },
                  onError: () => {
                    haptics.notify("error");
                    onDone(); // stale (changed elsewhere): the question no longer applies
                  },
                },
              );
            }}
          />
        </Localized>
        <Localized id="progression-ask-no">
          <button
            type="button"
            className="chip"
            onClick={() => {
              haptics.impact("light");
              dismiss.mutate(target);
              onDone();
            }}
          />
        </Localized>
      </div>
    </div>
  );
}

function ranges(catalog: Catalog): Range[] {
  const out: Range[] = [];
  for (const s of catalog.series) {
    out.push({ first: s.number, last: s.number, firstPart: null });
    const previous = catalog.series.find((p) => p.number === s.number - 1);
    if (previous) {
      out.push({ first: previous.number, last: s.number, firstPart: null });
      if (previous.halves_split) {
        out.push({ first: previous.number, last: s.number, firstPart: "first_half" });
        out.push({ first: previous.number, last: s.number, firstPart: "second_half" });
      }
    }
  }
  return out;
}

const rangeKey = (r: Range) => `${String(r.first)}${String(r.last)}${r.firstPart ?? ""}`;

/** "Other…": series range, then the last asana (stop points only) or the full series. */
function CustomLength({
  catalog,
  value,
  locale,
  onChange,
}: {
  catalog: Catalog;
  value: Length | null;
  locale: Locale;
  onChange: (length: Length) => void;
}) {
  const { l10n } = useLocalization();
  const all = ranges(catalog);
  const initial = value ? rangeOf(catalog, value) : null;
  const [range, setRange] = useState<Range>(
    initial && initial.first > 0 ? initial : (all[0] ?? { first: 1, last: 1, firstPart: null }),
  );
  const last = catalog.series.find((s) => s.number === range.last);
  return (
    <div className="custom">
      <label className="label">
        <Localized id="length-pick-range">
          <span />
        </Localized>
        <select
          value={rangeKey(range)}
          onChange={(e) => {
            const next = all.find((r) => rangeKey(r) === e.target.value);
            if (next) setRange(next);
          }}
        >
          {all.map((r) => (
            <option key={rangeKey(r)} value={rangeKey(r)}>
              {rangeText(l10n, r, true)}
            </option>
          ))}
        </select>
      </label>
      <label className="label">
        <Localized id="length-pick-end">
          <span />
        </Localized>
        <select
          value=""
          onChange={(e) => {
            onChange(lengthOf(catalog, range, e.target.value === "full" ? null : e.target.value));
          }}
        >
          <Localized id="length-pick-end">
            <option value="" disabled />
          </Localized>
          <Localized id="length-full-series">
            <option value="full" />
          </Localized>
          {last?.stops.map((s) => (
            <option key={s.key} value={s.key}>
              {locale === "ru" ? s.ru : s.latin}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

/** Saved on blur or Enter, not on every keystroke; labelled with the zone it's stored in. */
function StartTime({
  value,
  zone,
  place,
  date,
  onCommit,
}: {
  value: string | null;
  zone: string;
  /** The home city's name when it names `zone` (MD-04). */
  place: string | undefined;
  date: string;
  onCommit: (time: string | null) => void;
}) {
  const [draft, setDraft] = useState(value ?? "");
  return (
    <label className="label time">
      <Localized id="practice-start-time">
        <span />
      </Localized>
      <input
        type="time"
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
        }}
        onBlur={() => {
          onCommit(draft || null);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") onCommit(draft || null);
        }}
      />
      <span className="hint">{zoneLabel(zone, date, value ?? undefined, place)}</span>
    </label>
  );
}
