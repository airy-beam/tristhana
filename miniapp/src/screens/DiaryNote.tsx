import { Localized, useLocalization } from "@fluent/react";
import { useEffect, useState } from "react";

import { useSaveDiaryNote, type DayNote } from "../api/client";
import { disableClosingConfirmation, enableClosingConfirmation, haptics } from "../telegram";

interface Props {
  date: string;
  /** The day's note from the server (absent from an older API, or when there is none). */
  note: DayNote | undefined;
}

const MAX = 2000;
const COUNTER_FROM = 1800;

/** Code points, as the server counts them (an emoji is one). */
const length = (text: string) => Array.from(text).length;

/** The day's private diary note (PR-07): any status or none. Explicit Save / Cancel (never on
 * blur: Telegram's WebView blurs on keyboard hide), no drafts kept anywhere. */
export function DiaryNote({ date, note }: Props) {
  const { l10n } = useLocalization();
  const save = useSaveDiaryNote();
  const [draft, setDraft] = useState<string | null>(null); // null: not editing
  const [confirming, setConfirming] = useState(false);
  const [removed, setRemoved] = useState(false);
  const dirty = draft !== null && draft !== (note?.text ?? "");

  useEffect(() => {
    if (!dirty) return;
    enableClosingConfirmation();
    return () => {
      disableClosingConfirmation();
    };
  }, [dirty]);

  const close = () => {
    setDraft(null);
    save.reset();
  };
  const commit = (text: string | null) => {
    haptics.impact("light");
    save.mutate(
      { date, text },
      {
        onSuccess: (saved) => {
          setRemoved(text === null || saved.text === null);
          setConfirming(false);
          close();
        },
        onError: () => {
          haptics.notify("error");
        },
      },
    );
  };

  if (draft !== null) {
    const n = length(draft);
    return (
      <div className="details">
        <Localized id="diary-title">
          <h3 />
        </Localized>
        <textarea
          value={draft}
          rows={5}
          placeholder={l10n.getString("diary-placeholder")}
          aria-label={l10n.getString("diary-title")}
          onChange={(e) => {
            setDraft(e.target.value);
          }}
        />
        {n >= COUNTER_FROM && (
          <Localized id="diary-counter" vars={{ n, max: MAX }}>
            <p
              className={n > MAX ? "status small" : "hint small"}
              role={n > MAX ? "alert" : undefined}
            />
          </Localized>
        )}
        <Localized id="diary-private-hint">
          <p className="hint small" />
        </Localized>
        <div className="row">
          <Localized id="diary-save">
            <button
              type="button"
              className="chip"
              disabled={save.isPending || n > MAX} // the server would refuse it
              onClick={() => {
                commit(draft.trim() === "" ? null : draft); // blank: DELETE, not an empty PUT
              }}
            />
          </Localized>
          <Localized id="diary-cancel">
            <button type="button" className="link" onClick={close} />
          </Localized>
        </div>
        {save.isError && (
          <Localized id="diary-save-failed">
            <p className="status" role="alert" />
          </Localized>
        )}
      </div>
    );
  }

  const exists = note !== undefined && (note.text !== null || note.unreadable);
  if (!exists) {
    return (
      <div className="details">
        {removed && (
          <Localized id="diary-removed">
            <p className="hint" role="status" />
          </Localized>
        )}
        <Localized id="diary-add">
          <button
            type="button"
            className="link"
            onClick={() => {
              setRemoved(false);
              setDraft("");
            }}
          />
        </Localized>
      </div>
    );
  }

  return (
    <div className="details">
      <Localized id="diary-title">
        <h3 />
      </Localized>
      {note.text !== null ? (
        <p className="note">{note.text}</p>
      ) : (
        <Localized id="diary-unreadable">
          <p className="hint" />
        </Localized>
      )}
      {confirming ? (
        <div className="row">
          <Localized id="diary-clear-confirm">
            <span />
          </Localized>
          <Localized id="diary-clear-yes">
            <button
              type="button"
              className="link"
              onClick={() => {
                commit(null);
              }}
            />
          </Localized>
          <Localized id="diary-cancel">
            <button
              type="button"
              className="link"
              onClick={() => {
                setConfirming(false);
              }}
            />
          </Localized>
        </div>
      ) : (
        <div className="row">
          <Localized id="diary-edit">
            <button
              type="button"
              className="link"
              onClick={() => {
                setDraft(note.text ?? "");
              }}
            />
          </Localized>
          <Localized id="diary-clear">
            <button
              type="button"
              className="link"
              onClick={() => {
                setConfirming(true);
              }}
            />
          </Localized>
        </div>
      )}
      {save.isError && (
        <Localized id="diary-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </div>
  );
}
