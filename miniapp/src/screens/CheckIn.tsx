import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import {
  useCatalog,
  useMe,
  useSaveCheckIn,
  type CheckIn as CheckInValue,
  type CheckInBody,
  type CheckInTag,
} from "../api/client";
import { haptics } from "../telegram";

interface Props {
  date: string;
  /** The day's check-ins from the server (absent from an older API). */
  checkIns: CheckInValue[] | undefined;
  /** The server's today: the device date may differ. */
  today: string;
}

const SCALE = [1, 2, 3, 4, 5] as const;
type ScaleField = "mood" | "energy" | "effort";

const EMPTY: CheckInBody = { mood: null, energy: null, effort: null, tags: [] };

// Fluent's bidi isolation marks around variables: noise in an aria label.
const plain = (text: string) => text.replace(/[\u2068\u2069]/g, "");

function dayBefore(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

function isEmpty(c: CheckInBody): boolean {
  return c.mood == null && c.energy == null && c.effort == null && c.tags.length === 0;
}

/** After-practice check-in (PR-06): mood, energy, effort and body-and-mind tags. Open for
 * today and yesterday (setting on) or when one exists; otherwise a "✨ Check-in" link. */
export function CheckIn({ date, checkIns, today }: Props) {
  const { l10n } = useLocalization();
  const offered = useMe().data?.offer_check_in === true;
  const tags = useCatalog().data?.check_in_tags ?? [];
  const save = useSaveCheckIn();
  const [expanded, setExpanded] = useState(false);

  const stored = checkIns?.[0];
  const current: CheckInBody = stored
    ? {
        mood: stored.mood ?? null,
        energy: stored.energy ?? null,
        effort: stored.effort ?? null,
        tags: stored.tags,
      }
    : EMPTY;
  const exists = stored !== undefined && !isEmpty(current);
  const recent = date === today || date === dayBefore(today);
  if (!exists && !expanded && !(offered && recent)) {
    return (
      <Localized id="checkin-edit">
        <button
          type="button"
          className="link"
          onClick={() => {
            setExpanded(true);
          }}
        />
      </Localized>
    );
  }

  const update = (change: Partial<CheckInBody>) => {
    haptics.impact("light");
    const body = { ...current, ...change };
    save.mutate(
      { date, body: isEmpty(body) ? null : body }, // nothing left: DELETE, not an empty row
      {
        onError: () => {
          haptics.notify("error");
        },
      },
    );
  };
  const chosen = new Set(current.tags);
  const toggle = (tag: CheckInTag) => {
    const next = new Set(chosen);
    if (next.has(tag)) next.delete(tag);
    else next.add(tag);
    update({ tags: tags.map((t) => t.key).filter((k) => next.has(k)) }); // display order
  };
  const scale = (
    field: ScaleField,
    chip: (n: number) => React.ReactNode,
    label?: (n: number) => string,
  ) => (
    <div className="chips" role="group" aria-label={l10n.getString(`checkin-${field}`)}>
      {SCALE.map((n) => (
        <button
          key={n}
          type="button"
          className="chip"
          aria-pressed={current[field] === n}
          aria-label={label?.(n)}
          onClick={() => {
            update({ [field]: current[field] === n ? null : n });
          }}
        >
          {chip(n)}
        </button>
      ))}
    </div>
  );
  const tagGroup = (group: "body" | "mind") => (
    <div className="chips" role="group" aria-label={l10n.getString(`checkin-${group}`)}>
      {tags
        .filter((t) => t.group === group)
        .map((t) => (
          <Localized key={t.key} id="checkin-tag" vars={{ tag: t.key }}>
            <button
              type="button"
              className="chip"
              aria-pressed={chosen.has(t.key)}
              onClick={() => {
                toggle(t.key);
              }}
            />
          </Localized>
        ))}
    </div>
  );

  return (
    <div className="details">
      <Localized id="checkin-title">
        <h3 />
      </Localized>
      {scale(
        "mood",
        (n) => l10n.getString("checkin-mood-chip", { n }),
        (n) => plain(l10n.getString("checkin-mood-label", { n })),
      )}
      <Localized id="checkin-energy">
        <p className="label" />
      </Localized>
      {scale("energy", (n) => n)}
      <Localized id="checkin-effort">
        <p className="label" />
      </Localized>
      {scale("effort", (n) => n)}
      <Localized id="checkin-body">
        <p className="label" />
      </Localized>
      {tagGroup("body")}
      <Localized id="checkin-mind">
        <p className="label" />
      </Localized>
      {tagGroup("mind")}
      {exists && (
        <Localized id="checkin-clear">
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
      {save.isError && (
        <Localized id="checkin-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </div>
  );
}
