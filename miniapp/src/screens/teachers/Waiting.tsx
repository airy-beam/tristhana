import { useLocalization } from "@fluent/react";
import { useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { confirmAction, haptics } from "../../telegram";
import { get } from "../progression/progressionText";
import {
  REQUESTS_PAGE,
  useAnswerRequest,
  useApproveAll,
  useStudentRequests,
  type Answer,
  type StudentRequest,
  type StudentRequests,
} from "./requests";

/** A row answered "Not my student" on this visit: kept where it was, for its Undo. The Shala
 * tab holds these, so they outlast a shala's card, the announcements or the directory line
 * opened over the list, and end when the tab is left. */
export interface Declined {
  row: StudentRequest;
  at: number;
}

/** ID-07: the people who named me as their teacher in a shala, on top of the Shala tab (UI-06
 * stage 4B, QC). Each answer is one request and waits for the server. "Not my student" tells
 * the person nothing and keeps its row with an Undo until the tab is left (`declined`, held by
 * the tab); "Confirm all" asks once and sends back the moment the list was drawn. A request
 * that is no longer open (404, one line for every reason) or a full list (409, the request
 * stays) is a short line, and the list is read again. Renders nothing when nobody waits. */
export function Waiting({
  declined,
  setDeclined,
}: {
  declined: Declined[];
  setDeclined: (change: (rows: Declined[]) => Declined[]) => void;
}) {
  const { l10n } = useLocalization();
  const [pages, setPages] = useState(1);
  const [line, setLine] = useState<{ text: string; alert: boolean } | null>(null);
  // The line sits over the block: an answer far down a long list brings it into view.
  const said = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (line) said.current?.scrollIntoView({ block: "nearest" });
  }, [line]);
  const queries = useStudentRequests(pages);
  const name = (row: StudentRequest) => row.name ?? l10n.getString("link-no-name");
  const forget = (id: string) => {
    setDeclined((rows) => rows.filter((d) => d.row.student_id !== id));
  };
  // An older API answers without the fields: then nobody waits.
  const read = queries.map((query) => query.data as Partial<StudentRequests> | undefined);
  const total = read[0]?.total ?? 0;
  const asOf = read[0]?.as_of;
  const gone = new Set(declined.map((d) => d.row.student_id));
  const shown = read
    .flatMap((page) => page?.requests ?? [])
    .filter((row) => !gone.has(row.student_id))
    .map((row) => ({ row, declined: false }));
  for (const { row, at } of [...declined].sort((x, y) => x.at - y.at)) {
    shown.splice(Math.min(at, shown.length), 0, { row, declined: true });
  }

  const answer = useAnswerRequest((sent) => {
    // Before the list is read again, so the row never leaves the screen in between.
    const at = shown.findIndex((s) => s.row.student_id === sent.id);
    const row = shown[at]?.row;
    if (!row) return;
    if (sent.answer === "decline") {
      setDeclined((rows) => [...rows, { row, at }]);
    } else if (sent.answer === "approve") {
      haptics.impact("light");
      setLine({ text: l10n.getString("link-student-joined", { name: name(row) }), alert: false });
    }
  });
  const all = useApproveAll();
  const busy = answer.isPending || all.isPending;

  const send = (row: StudentRequest, what: Answer) => {
    setLine(null);
    answer.mutate(
      { id: row.student_id, answer: what },
      {
        // After the list is read again: the row is back among the waiting ones by now.
        onSuccess: () => {
          if (what === "reopen") forget(row.student_id);
        },
        onError: (error) => {
          if (error instanceof ApiError && error.code === "request_gone") {
            forget(row.student_id);
            setLine({ text: l10n.getString("request-gone"), alert: false });
            return;
          }
          haptics.notify("error");
          const full = error instanceof ApiError && error.code === "list_full";
          const id = full ? "request-list-full" : "settings-save-failed";
          setLine({ text: l10n.getString(id), alert: true });
        },
      },
    );
  };

  const confirmAll = async () => {
    if (!asOf) return;
    const ok = await confirmAction(
      get(l10n, "request-all-ask", { count: total }),
      get(l10n, "request-all-yes"),
      get(l10n, "delete-cancel"),
    );
    if (!ok) return;
    setLine(null);
    all.mutate(asOf, {
      onSuccess: (done) => {
        haptics.impact("light");
        // As the bot: the number confirmed; whoever is left is still on the list above.
        const text = l10n.getString("request-all-done", { count: done.approved });
        setLine({ text, alert: false });
      },
      onError: () => {
        haptics.notify("error");
        setLine({ text: l10n.getString("settings-save-failed"), alert: true });
      },
    });
  };

  return (
    <>
      {queries.some((query) => query.isError) && (
        <p className="hint" role="alert">
          {l10n.getString("request-load-failed")}
        </p>
      )}
      {line &&
        (line.alert ? (
          <p ref={said} className="status" role="alert">
            {line.text}
          </p>
        ) : (
          <p ref={said} className="status" role="status">
            {line.text}
          </p>
        ))}
      {shown.length > 0 && (
        <section className="card waiting">
          <h2>
            {total > 0
              ? l10n.getString("request-waiting-open", { count: total })
              : l10n.getString("request-list-empty")}
          </h2>
          {total > 0 && <p className="hint">{l10n.getString("request-list-hint")}</p>}
          <ul>
            {shown.map(({ row, declined: answered }) => (
              <li key={row.student_id}>
                <span className="student-name">{name(row)}</span>
                <p className="hint small">{row.shala.name}</p>
                {answered ? (
                  <>
                    <p className="hint small">
                      {l10n.getString("request-declined", { name: name(row) })}
                    </p>
                    <div className="chips">
                      <button
                        type="button"
                        className="chip"
                        disabled={busy}
                        onClick={() => {
                          send(row, "reopen");
                        }}
                      >
                        {l10n.getString("request-undo")}
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="chips">
                    <button
                      type="button"
                      className="chip primary"
                      disabled={busy}
                      onClick={() => {
                        send(row, "approve");
                      }}
                    >
                      {l10n.getString("request-yes-mine")}
                    </button>
                    <button
                      type="button"
                      className="chip"
                      disabled={busy}
                      onClick={() => {
                        send(row, "decline");
                      }}
                    >
                      {l10n.getString("request-not-mine")}
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
          {pages * REQUESTS_PAGE < total && (
            <button
              type="button"
              className="row-button"
              onClick={() => {
                setPages(pages + 1);
              }}
            >
              {l10n.getString("students-more")}
            </button>
          )}
          {total > 1 && (
            <button
              type="button"
              className="row-button"
              disabled={busy}
              onClick={() => {
                void confirmAll();
              }}
            >
              {l10n.getString("request-all", { count: total })}
            </button>
          )}
        </section>
      )}
    </>
  );
}
