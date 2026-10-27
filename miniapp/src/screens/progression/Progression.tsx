import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import {
  ApiError,
  useCatalog,
  useProgression,
  useProgressionEvent,
  useUndoProgression,
  type Catalog,
  type Progression as ProgressionValue,
  type ProgressionChange,
  type ProgressionEventBody,
  type ProgressionPosition,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { backButtonAvailable, haptics, useBackButton } from "../../telegram";
import { lengthText } from "../practiceText";
import { CelebrationCard } from "./CelebrationCard";
import { celebrationLines, get, isStanding, itemLabel, stopLabel } from "./progressionText";

interface Props {
  locale: Locale;
  onBack: () => void;
}

type Target = { series: string | null; last: string | null };

/** "🧘 My asanas" (PR-08): where the practice ends now, a new asana, the milestone items,
 * a correction (never celebrated), and a short history with Undo on the newest entry.
 * Loaded lazily, so Home stays light. Writes are not optimistic. */
export default function Progression({ locale, onBack }: Props) {
  useBackButton(onBack);
  const catalog = useCatalog().data;
  const progression = useProgression();
  const data = progression.data;
  return (
    <main className="screen progression">
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      <Localized id="progression-title">
        <h1 />
      </Localized>
      {catalog && data ? (
        <Body catalog={catalog} progression={data} locale={locale} />
      ) : (
        <div aria-busy="true" />
      )}
    </main>
  );
}

function Body({
  catalog,
  progression,
  locale,
}: {
  catalog: Catalog;
  progression: ProgressionValue;
  locale: Locale;
}) {
  const { l10n } = useLocalization();
  const change = useProgressionEvent();
  const undo = useUndoProgression();
  const [lines, setLines] = useState<string[] | null>(null);
  const [failed, setFailed] = useState<"changed" | "failed" | null>(null);
  const [editing, setEditing] = useState(!progression.set);
  const today = progression.today ?? "";
  const [day, setDay] = useState(today);

  const send = (body: Omit<ProgressionEventBody, "expected_event_id" | "occurred_on">) => {
    haptics.impact("light");
    setFailed(null);
    change.mutate(
      {
        ...body,
        occurred_on: day && day !== today ? day : null,
        expected_event_id: progression.last_event_id,
      },
      {
        onSuccess: (done: ProgressionChange) => {
          const found = celebrationLines(l10n, catalog, done.celebrations, locale);
          if (found.length) {
            haptics.notify("success");
            setLines(found);
          } else if (body.kind === "given" && done.event) {
            const asana = stopLabel(catalog, done.event.to, locale);
            setLines([get(l10n, "progression-back", { asana })]);
          } else {
            setLines(null);
          }
          if (body.kind === "set") setEditing(false);
        },
        onError: (error) => {
          haptics.notify("error");
          setFailed(error instanceof ApiError && error.status === 409 ? "changed" : "failed");
        },
      },
    );
  };
  const position = progression.position;
  const busy = change.isPending || undo.isPending;

  return (
    <>
      {lines && (
        <CelebrationCard
          lines={lines}
          onDismiss={() => {
            setLines(null);
          }}
        />
      )}
      {failed && (
        <Localized id={failed === "changed" ? "progression-changed" : "progression-save-failed"}>
          <p className="status" role="alert" />
        </Localized>
      )}
      <section className="card">
        {!progression.set ? (
          <>
            <Localized id="progression-unset">
              <p />
            </Localized>
            {progression.suggested && progression.suggested_length && (
              <button
                type="button"
                className="chip"
                disabled={busy}
                onClick={() => {
                  if (progression.suggested) send({ kind: "set", ...progression.suggested });
                }}
              >
                {get(l10n, "progression-suggest", {
                  length: lengthText(l10n, catalog, progression.suggested_length, locale),
                })}
              </button>
            )}
          </>
        ) : (
          <Current catalog={catalog} progression={progression} locale={locale} />
        )}
        {progression.set && progression.next && (
          <button
            type="button"
            className="row-button"
            disabled={busy}
            onClick={() => {
              if (progression.next) send({ kind: "given", ...progression.next });
            }}
          >
            {get(l10n, "progression-new", {
              asana: stopLabel(catalog, progression.next, locale),
            })}
          </button>
        )}
        {progression.set && progression.later.length > 1 && (
          <label className="label">
            <Localized id="progression-new-other">
              <span />
            </Localized>
            <select
              value=""
              disabled={busy}
              onChange={(e) => {
                const target = progression.later[Number(e.target.value)];
                if (target) send({ kind: "given", ...target });
              }}
            >
              <option value="" disabled />
              {progression.later.slice(1).map((p, i) => (
                <option key={`${p.series ?? ""}:${p.last ?? ""}`} value={i + 1}>
                  {stopLabel(catalog, p, locale)}
                </option>
              ))}
            </select>
          </label>
        )}
        {progression.set && (
          <div className="chips" role="group">
            {catalog.milestone_items.map((item) => {
              const given = progression.items.includes(item.key);
              return (
                <button
                  key={item.key}
                  type="button"
                  className="chip"
                  aria-pressed={given}
                  disabled={busy}
                  onClick={() => {
                    send({ kind: given ? "item_removed" : "item_given", item: item.key });
                  }}
                >
                  {given
                    ? itemLabel(l10n, catalog, item.key, locale)
                    : get(l10n, "progression-item-new", {
                        item: itemLabel(l10n, catalog, item.key, locale),
                      })}
                </button>
              );
            })}
          </div>
        )}
        {editing ? (
          <ChangeForm
            catalog={catalog}
            position={position ?? null}
            locale={locale}
            busy={busy}
            onSave={(target) => {
              send({ kind: "set", ...target });
            }}
            onCancel={
              progression.set
                ? () => {
                    setEditing(false);
                  }
                : undefined
            }
          />
        ) : (
          <Localized id="progression-change">
            <button
              type="button"
              className="link"
              onClick={() => {
                setEditing(true);
              }}
            />
          </Localized>
        )}
        {today && (
          <label className="label">
            <Localized id="progression-date">
              <span />
            </Localized>
            <input
              type="date"
              value={day}
              max={today}
              min="2000-01-01"
              onChange={(e) => {
                setDay(e.target.value || today);
              }}
            />
          </label>
        )}
      </section>
      {progression.events.length > 0 && (
        <History
          catalog={catalog}
          progression={progression}
          locale={locale}
          busy={busy}
          onUndo={(id) => {
            haptics.impact("light");
            setLines(null);
            undo.mutate(id, {
              onError: () => {
                haptics.notify("error");
                setFailed("changed");
              },
            });
          }}
        />
      )}
    </>
  );
}

function Current({
  catalog,
  progression,
  locale,
}: {
  catalog: Catalog;
  progression: ProgressionValue;
  locale: Locale;
}) {
  const { l10n } = useLocalization();
  const length = progression.length
    ? lengthText(l10n, catalog, progression.length, locale)
    : isStanding(progression.position)
      ? get(l10n, "progression-standing-only")
      : stopLabel(catalog, progression.position, locale);
  const items = catalog.milestone_items
    .filter((i) => progression.items.includes(i.key))
    .map((i) => itemLabel(l10n, catalog, i.key, locale));
  return (
    <>
      <p>{get(l10n, "progression-current", { length })}</p>
      {items.length > 0 && (
        <p className="hint">{get(l10n, "progression-items", { items: items.join(", ") })}</p>
      )}
    </>
  );
}

/** Two native selects (as PracticeDetails "Other…"): a series (or standing only), then
 * its last asana. */
function ChangeForm({
  catalog,
  position,
  locale,
  busy,
  onSave,
  onCancel,
}: {
  catalog: Catalog;
  position: ProgressionPosition | null;
  locale: Locale;
  busy: boolean;
  onSave: (target: Target) => void;
  onCancel: (() => void) | undefined;
}) {
  const [series, setSeries] = useState(position?.series ?? catalog.series[0]?.slug ?? "");
  const stops = catalog.series.find((s) => s.slug === series)?.stops ?? [];
  const [last, setLast] = useState(position?.last ?? "");
  const lastValid = series === "" || stops.some((s) => s.key === last);
  return (
    <div className="details">
      <Localized id="progression-change-explain">
        <p className="hint" />
      </Localized>
      <label className="label">
        <Localized id="progression-pick-series">
          <span />
        </Localized>
        <select
          value={series}
          onChange={(e) => {
            setSeries(e.target.value);
            setLast("");
          }}
        >
          {catalog.series.map((s) => (
            <Localized key={s.slug} id="series-name" vars={{ n: s.number }}>
              <option value={s.slug} />
            </Localized>
          ))}
          <Localized id="progression-standing-only">
            <option value="" />
          </Localized>
        </select>
      </label>
      {series !== "" && (
        <label className="label">
          <Localized id="progression-pick-asana">
            <span />
          </Localized>
          <select
            value={last}
            onChange={(e) => {
              setLast(e.target.value);
            }}
          >
            <option value="" disabled />
            {stops.map((s) => (
              <option key={s.key} value={s.key}>
                {locale === "ru" ? s.ru : s.latin}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="chips">
        <Localized id="progression-save">
          <button
            type="button"
            className="chip"
            disabled={busy || !lastValid}
            onClick={() => {
              onSave(series === "" ? { series: null, last: null } : { series, last });
            }}
          />
        </Localized>
        {onCancel && (
          <Localized id="progression-cancel">
            <button type="button" className="chip" onClick={onCancel} />
          </Localized>
        )}
      </div>
    </div>
  );
}

function History({
  catalog,
  progression,
  locale,
  busy,
  onUndo,
}: {
  catalog: Catalog;
  progression: ProgressionValue;
  locale: Locale;
  busy: boolean;
  onUndo: (id: number) => void;
}) {
  const { l10n } = useLocalization();
  const format = new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  const [newest] = progression.events;
  return (
    <section className="card history">
      <Localized id="progression-history">
        <h2 />
      </Localized>
      <ol>
        {progression.events.map((e) => {
          const asana = isStanding(e.to)
            ? get(l10n, "progression-standing-only")
            : stopLabel(catalog, e.to, locale);
          const item = e.item ? itemLabel(l10n, catalog, e.item, locale) : "";
          return (
            <li key={e.id}>
              <span className="hint">{format.format(new Date(`${e.occurred_on}T00:00:00Z`))}</span>{" "}
              {get(l10n, "progression-event", { kind: e.kind, asana, item })}
            </li>
          );
        })}
      </ol>
      {newest && (
        <Localized id="progression-undo">
          <button
            type="button"
            className="link"
            disabled={busy}
            onClick={() => {
              onUndo(newest.id);
            }}
          />
        </Localized>
      )}
    </section>
  );
}
