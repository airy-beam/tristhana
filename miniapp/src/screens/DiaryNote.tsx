import { Localized, useLocalization } from "@fluent/react";
import { useEffect, useState } from "react";

import { useSaveDiaryNote, type DayNote } from "../api/client";
import {
  confirmDestructive,
  disableClosingConfirmation,
  enableClosingConfirmation,
  haptics,
  useBackButton,
} from "../telegram";
import { Row } from "./Row";

interface Props {
  date: string;
  /** The day's note from the server (absent from an older API, or when there is none). */
  note: DayNote | undefined;
}

const MAX = 2000;
const COUNTER_FROM = 1800;

/** Code points, as the server counts them (an emoji is one). */
const length = (text: string) => Array.from(text).length;

/** The note's first line with something in it: what its row shows. */
const firstLine = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line !== "");

/** The day's private diary note (PR-07): any status or none. A list row: "Add a note", or the
 * note's first line, which opens the whole note with Edit and Remove. Explicit Save / Cancel
 * (never on blur: Telegram's WebView blurs on keyboard hide), no drafts kept anywhere. */
export function DiaryNote({ date, note }: Props) {
  const { l10n } = useLocalization();
  const save = useSaveDiaryNote();
  const [draft, setDraft] = useState<string | null>(null); // null: not editing
  const [confirming, setConfirming] = useState(false);
  const [removed, setRemoved] = useState(false);
  const [open, setOpen] = useState(false); // the whole note, under its row
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
  // Back while typing asks first; the text is kept nowhere else (Q68).
  useBackButton(() => {
    confirmDestructive(
      l10n.getString("diary-discard-confirm"),
      l10n.getString("diary-discard-yes"),
      l10n.getString("diary-discard-no"),
    )
      .then((discard) => {
        if (discard) close();
      })
      .catch(() => undefined); // a second press while the popup is open: it is still asking
  }, dirty);
  const commit = (text: string | null) => {
    haptics.impact("light");
    save.mutate(
      { date, text },
      {
        onSuccess: (saved) => {
          setRemoved(text === null || saved.text === null);
          setConfirming(false);
          setOpen(false);
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
      <div className="details note-edit">
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
      <>
        {removed && (
          <Localized id="diary-removed">
            <p className="hint" role="status" />
          </Localized>
        )}
        <Row
          label={l10n.getString("diary-add")}
          onClick={() => {
            setRemoved(false);
            setDraft("");
          }}
        />
      </>
    );
  }

  // A note that can't be read says so at once: there is no first line to show.
  const shown = open || note.text === null;
  return (
    <>
      <Row
        label={l10n.getString("diary-row")}
        sub={shown || note.text === null ? undefined : firstLine(note.text)}
        expanded={shown}
        onClick={() => {
          haptics.selection();
          setOpen(!open);
        }}
      />
      {shown && (
        <NoteBody
          note={note}
          confirming={confirming}
          failed={save.isError}
          onEdit={() => {
            setDraft(note.text ?? "");
          }}
          onConfirm={setConfirming}
          onRemove={() => {
            commit(null);
          }}
        />
      )}
    </>
  );
}

/** The whole note under its row, with Edit and Remove (asked inline first). */
function NoteBody({
  note,
  confirming,
  failed,
  onEdit,
  onConfirm,
  onRemove,
}: {
  note: DayNote;
  confirming: boolean;
  failed: boolean;
  onEdit: () => void;
  onConfirm: (asking: boolean) => void;
  onRemove: () => void;
}) {
  return (
    <div className="details">
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
            <button type="button" className="link" onClick={onRemove} />
          </Localized>
          <Localized id="diary-cancel">
            <button
              type="button"
              className="link"
              onClick={() => {
                onConfirm(false);
              }}
            />
          </Localized>
        </div>
      ) : (
        <div className="row">
          <Localized id="diary-edit">
            <button type="button" className="link" onClick={onEdit} />
          </Localized>
          <Localized id="diary-clear">
            <button
              type="button"
              className="link"
              onClick={() => {
                onConfirm(true);
              }}
            />
          </Localized>
        </div>
      )}
      {failed && (
        <Localized id="diary-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </div>
  );
}
