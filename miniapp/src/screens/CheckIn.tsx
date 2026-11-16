import { Localized, useLocalization } from "@fluent/react";

import {
  useCatalog,
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
}

const SCALE = [1, 2, 3, 4, 5] as const;
type ScaleField = "mood" | "energy" | "effort";

const EMPTY: CheckInBody = { mood: null, energy: null, effort: null, tags: [] };

// Fluent's bidi isolation marks around variables: noise in an aria label.
const plain = (text: string) => text.replace(/[\u2068\u2069]/g, "");

function isEmpty(c: CheckInBody): boolean {
  return c.mood == null && c.energy == null && c.effort == null && c.tags.length === 0;
}

/** The after-practice check-in (PR-06): mood, energy, effort and body-and-mind tags. The
 * editor only: the day card decides whether its "How do you feel?" entry shows and opens it
 * (UI-06). Lazy, in the `dayExtras` chunk. */
export function CheckIn({ date, checkIns }: Props) {
  const { l10n } = useLocalization();
  const tags = useCatalog().data?.check_in_tags ?? [];
  const save = useSaveCheckIn();

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
