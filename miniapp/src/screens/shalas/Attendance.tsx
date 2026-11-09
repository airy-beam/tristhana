import { Localized, useLocalization } from "@fluent/react";
import { useDeferredValue, useState } from "react";

import {
  ApiError,
  useMarkAttendance,
  useRoster,
  type AttendanceDelta,
  type RosterPerson,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { haptics } from "../../telegram";
import { zoneLabel } from "../practiceText";
import { useTypeName } from "./ClassForm";
import { DASH, dayName, plain, timeIn } from "./scheduleText";

const PAGE = 50;
/** The server takes at most 100 ids per list (`MAX_DELTA`); more must be saved first. */
const MAX_DELTA = 100;

interface Props {
  shalaId: string;
  classId: string;
  occurrenceKey: string;
  locale: Locale;
  onClose: () => void;
}

/** Staff on one occurrence (SC-05, ADR-0039): who came. Ticks are deltas sent in one PATCH
 * by a sticky Save, not optimistic; a closed occurrence (409) refetches and says so. A mark
 * is presence only: nothing here reads or writes anyone's log. Loaded lazily. */
export default function Attendance({ shalaId, classId, occurrenceKey, locale, onClose }: Props) {
  const { l10n } = useLocalization();
  const typeName = useTypeName();
  const [q, setQ] = useState("");
  const query = useDeferredValue(q.trim());
  const [offset, setOffset] = useState(0);
  const roster = useRoster(shalaId, classId, occurrenceKey, query, offset);
  const mark = useMarkAttendance(shalaId, classId, occurrenceKey);
  // account id -> wanted present (true) or not (false); only the changes.
  const [changes, setChanges] = useState<Map<string, boolean>>(new Map());
  const [closed, setClosed] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const [full, setFull] = useState(false);
  const data = roster.data;
  const open = data?.attendable === true && !closed;

  const present = (p: RosterPerson) => changes.get(p.account_id) ?? p.state === "confirmed";
  const toggle = (p: RosterPerson) => {
    haptics.selection();
    const next = new Map(changes);
    const wanted = !present(p);
    if (wanted === (p.state === "confirmed")) next.delete(p.account_id);
    else if (!next.has(p.account_id) && next.size >= MAX_DELTA) {
      setFull(true); // ticks on other pages and searches add up: save these first
      return;
    } else next.set(p.account_id, wanted);
    setFull(false);
    setChanges(next);
  };
  const failed = (e: unknown) => {
    if (e instanceof ApiError && e.status === 409) setClosed(true);
    else setSaveFailed(true); // 422 (someone left meanwhile), 5xx, offline: the ticks stay
  };
  const send = (confirmClaims: boolean) => {
    haptics.impact("light");
    setSaveFailed(false);
    const body: AttendanceDelta = { confirm_claims: confirmClaims };
    const present = [...changes].filter(([, v]) => v).map(([id]) => id);
    const removed = [...changes].filter(([, v]) => !v).map(([id]) => id);
    if (present.length > 0) body.present = present;
    if (removed.length > 0) body.removed = removed;
    mark.mutate(body, {
      onSuccess: () => {
        setChanges(new Map());
        setFull(false);
      },
      onError: failed,
    });
  };
  const save = () => {
    send(false);
  };
  // Pending ticks go with it, so none is lost or left showing a stale state.
  const confirmAll = () => {
    send(true);
  };

  const o = data?.occurrence;
  const start = o ? timeIn(o.starts_at, o.zone) : "";
  const title = o
    ? `${typeName(o.type)}${o.title ? ` ${o.title}` : ""} · ${dayName(o.on, locale)}, ${start}${DASH}${o.end}`
    : "";
  const where = o ? zoneLabel(o.zone, o.on, start) : "";
  return (
    <section className="card attendance" aria-busy={roster.isPending || mark.isPending}>
      <Localized id="attend-title">
        <h3 />
      </Localized>
      {roster.isError && (
        <Localized id="attend-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {data && (
        <>
          <p className="label">{title}</p>
          <p className="hint small">{where}</p>
          <p className="hint" role="status">
            {plain(
              l10n.getString("attend-roster-counts", {
                confirmed: data.confirmed,
                claimed: data.claimed,
              }),
            )}
          </p>
          {open ? (
            data.people.length > 0 && (
              <Localized id="attend-roster-hint">
                <p className="hint small" />
              </Localized>
            )
          ) : (
            <Localized id="attend-not-open">
              <p className="hint" role="alert" />
            </Localized>
          )}
          <label className="label">
            <Localized id="attend-search">
              <span />
            </Localized>
            <input
              type="search"
              value={q}
              maxLength={64}
              onChange={(e) => {
                setQ(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          {open && data.claimed > 0 && (
            <button
              type="button"
              className="row-button"
              disabled={mark.isPending}
              onClick={confirmAll}
            >
              {plain(l10n.getString("attend-confirm-all", { n: data.claimed }))}
            </button>
          )}
          {data.people.length === 0 && offset === 0 && !query && (
            <Localized id="attend-empty">
              <p className="hint" />
            </Localized>
          )}
          <ul className="attendance-people">
            {data.people.map((p) => (
              <li key={p.account_id}>
                <label className="attendance-person">
                  <input
                    type="checkbox"
                    checked={present(p)}
                    disabled={!open || mark.isPending}
                    onChange={() => {
                      toggle(p);
                    }}
                  />
                  <span className="link-person">
                    {p.state === "claimed" && !changes.has(p.account_id) ? "🙋 " : ""}
                    {p.name ?? plain(l10n.getString("link-no-name"))}
                  </span>
                  {p.staff && (
                    <Localized id="attend-staff-tag">
                      <span className="hint small" />
                    </Localized>
                  )}
                </label>
              </li>
            ))}
          </ul>
          <div className="paging">
            {offset > 0 && (
              <Localized id="page-prev">
                <button
                  type="button"
                  className="link"
                  onClick={() => {
                    setOffset(Math.max(0, offset - PAGE));
                  }}
                />
              </Localized>
            )}
            {data.more && (
              <Localized id="page-next">
                <button
                  type="button"
                  className="link"
                  onClick={() => {
                    setOffset(offset + PAGE);
                  }}
                />
              </Localized>
            )}
          </div>
        </>
      )}
      {saveFailed && (
        <Localized id="attend-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {full && (
        <Localized id="attend-save-first">
          <p className="hint" role="alert" />
        </Localized>
      )}
      <div className="sticky-actions">
        {changes.size > 0 && open && (
          <button type="button" className="primary" disabled={mark.isPending} onClick={save}>
            {plain(l10n.getString("attend-save", { n: changes.size }))}
          </button>
        )}
        <Localized id="attend-close">
          <button type="button" className="link" onClick={onClose} />
        </Localized>
      </div>
    </section>
  );
}
