import { useLocalization } from "@fluent/react";
import { useEffect, useRef } from "react";

import { confirmDestructive, haptics } from "../../telegram";
import { useWithdrawRequest, type Said, type TeacherChoice } from "./requests";

/** Telegram popups take 256 characters, and a long name can pass that in Russian. */
const POPUP_NAME_MAX = 40;
const short = (name: string) =>
  name.length > POPUP_NAME_MAX ? `${name.slice(0, POPUP_NAME_MAX)}…` : name;

/** ID-07, UI-06 stage 4B: the teachers I asked and wait for, as the bot's shala card has them:
 * "⏳ Waiting for an answer: Anna" and "Withdraw: Anna…" (one native confirm). The same line
 * whatever the teacher did: no state, date or count, so a quiet "no" reads as silence. On the
 * Shala tab's teachers card and on the shala's card. */
export function AskedLines({
  asked,
  onWithdrawn,
}: {
  asked: TeacherChoice[];
  /** After the server took it back and the lists were read again. */
  onWithdrawn: () => void;
}) {
  const { l10n } = useLocalization();
  const withdraw = useWithdrawRequest();
  const name = (teacher: TeacherChoice) => teacher.name ?? l10n.getString("link-no-name");

  const confirm = async (teacher: TeacherChoice) => {
    const ok = await confirmDestructive(
      l10n.getString("request-withdraw-ask", { name: short(name(teacher)) }),
      l10n.getString("request-withdraw-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("light");
    try {
      // Awaited rather than a callback: the line may be gone (and this with it) by the time
      // the lists are read again.
      await withdraw.mutateAsync(teacher.id);
      onWithdrawn();
    } catch {
      haptics.notify("error");
    }
  };

  return (
    <>
      {asked.map((teacher) => (
        <div key={teacher.id} className="link-person asked">
          <span>{l10n.getString("request-waiting-line", { name: name(teacher) })}</span>
          <button
            type="button"
            className="link"
            disabled={withdraw.isPending}
            onClick={() => {
              void confirm(teacher);
            }}
          >
            {l10n.getString("request-withdraw", { name: name(teacher) })}
          </button>
        </div>
      ))}
      {withdraw.isError && (
        <p className="hint" role="alert">
          {l10n.getString("settings-save-failed")}
        </p>
      )}
    </>
  );
}

/** The one line an ask or a withdraw leaves where it was done (spec §3 row 1, QE). It takes the
 * focus, so the picker's closing doesn't leave it on nothing, and a screen reader reads it. */
export function SaidLine({ said }: { said: Said }) {
  const line = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    line.current?.focus({ preventScroll: true });
  }, [said]);
  return (
    <p
      ref={line}
      tabIndex={-1}
      className={said.alert ? "hint said" : "status said"}
      role={said.alert ? "alert" : "status"}
    >
      {said.text}
    </p>
  );
}
