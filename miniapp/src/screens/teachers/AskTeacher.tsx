import { Localized, useLocalization } from "@fluent/react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { ApiError, useMe } from "../../api/client";
import { addMessages } from "../../i18n/lazyMessages";
import en from "../../locales/en/ask.ftl?raw";
import ru from "../../locales/ru/ask.ftl?raw";
import { backButtonAvailable, haptics, useBackButton } from "../../telegram";
import {
  useAskTeacher,
  useTeacherChoices,
  type AskResult,
  type Said,
  type TeacherChoice,
} from "./requests";

// The bot's own messages, copied under the same keys (ADR-0049): a test keeps them equal.
addMessages({ en, ru });

/** The bot's line for what a tap came to (`_ASKED` in bots/telegram/teacher_requests.py). */
const LINES: Record<AskResult, string> = {
  created: "request-asked",
  linked: "invite-already",
  waiting: "request-waiting",
  recent: "request-recent",
  too_many: "request-too-many",
  full: "request-full",
};

// Hangul fillers and the braille blank: letters that show nothing (the bot's `shown_name`).
const BLANK = /^[\p{C}\p{Z}\p{M}ᅟᅠ⠀ㅤﾠ]*$/u;

interface Props {
  shala: { id: string; name: string };
  /** Closes the picker: with the line to show where it was opened from, or null (Not now,
   * Back). */
  onDone: (said: Said | null) => void;
}

/** UI-06 stage 4B (spec §4, ADR-0049, ADR-0045): "Who is your teacher here?", the bot's
 * question screen line for line. A layer of its own, with Back. The short consent, or the full
 * text behind Details; a name (or Yes for the only one) on either layer is the consent to all
 * of `request-consent` and the request at once. The result goes back to the screen it was
 * opened from (QE). Nothing here can tell a teacher's "no" from silence: the server never
 * offers a pair it has a row for, and its answers are already projected. Its own chunk, with
 * its copy (`ask.ftl`). */
export default function AskTeacher({ shala, onDone }: Props) {
  const { l10n } = useLocalization();
  const close = useCallback(() => {
    onDone(null);
  }, [onDone]);
  useBackButton(close);
  const choices = useTeacherChoices(shala.id, true);
  const ask = useAskTeacher();
  const own = useMe().data?.display_name;
  const [details, setDetails] = useState(false);
  const [failed, setFailed] = useState(false);
  // While a tap is sent the names hold still: the list is read again before the answer comes.
  const [held, setHeld] = useState<TeacherChoice[] | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, []);
  const consentId = useId();
  const offer = held ?? choices.data?.offer ?? [];
  const name = (teacher: TeacherChoice) => teacher.name ?? l10n.getString("link-no-name");
  const me = own && !BLANK.test(own) ? ` (${own})` : "";

  const pick = (teacher: TeacherChoice) => {
    haptics.impact("light");
    setFailed(false);
    setHeld(offer);
    ask.mutate(
      { shala: shala.id, teacher: teacher.id },
      {
        onSuccess: (result) => {
          haptics.notify("success");
          onDone({ text: l10n.getString(LINES[result], { name: name(teacher) }) });
        },
        onError: (error) => {
          setHeld(null);
          haptics.notify("error");
          // Left the shala meanwhile: nothing to pick here any more.
          if (error instanceof ApiError && error.status === 404) {
            onDone({ text: l10n.getString("shala-load-failed"), alert: true });
          } else if (!(error instanceof ApiError && error.status === 403)) {
            setFailed(true);
          } // 403: no longer someone to ask; the list read again leaves the name out.
        },
      },
    );
  };

  return (
    <main className="screen ask-teacher" aria-busy={choices.isPending || undefined}>
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={close} />
        </Localized>
      )}
      <h1 ref={heading} tabIndex={-1}>
        {l10n.getString("shala-title", { shala: shala.name })}
      </h1>
      {choices.isError && !held && (
        <Localized id="shala-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {choices.isSuccess && offer.length === 0 && (
        <Localized id="request-nobody">
          <p role="status" />
        </Localized>
      )}
      {offer.length > 0 && (
        <>
          <p className="ask-question">
            {offer.length === 1 && offer[0]
              ? l10n.getString("request-ask-one", { name: name(offer[0]) })
              : l10n.getString("request-ask")}
          </p>
          <div id={consentId} className="consent">
            {details ? (
              <p>{l10n.getString("request-consent", { me })}</p>
            ) : (
              <>
                <p>{l10n.getString("request-consent-short", { me })}</p>
                <Localized id="request-until-yes">
                  <p />
                </Localized>
              </>
            )}
            <Localized id="request-know-them">
              <p />
            </Localized>
          </div>
          <div className="ask-names">
            {offer.length === 1 && offer[0] ? (
              <Pick
                label={l10n.getString("request-yes")}
                main
                busy={ask.isPending}
                onPick={() => {
                  if (offer[0]) pick(offer[0]);
                }}
              />
            ) : (
              offer.map((teacher) => (
                <Pick
                  key={teacher.id}
                  label={name(teacher)}
                  busy={ask.isPending}
                  onPick={() => {
                    pick(teacher);
                  }}
                />
              ))
            )}
          </div>
          {failed && (
            <Localized id="settings-save-failed">
              <p className="hint" role="alert" />
            </Localized>
          )}
          <div className="ask-more">
            <Localized id={details ? "consent-short-back" : "consent-details"}>
              <button
                type="button"
                className="link"
                aria-expanded={details}
                aria-controls={consentId}
                onClick={() => {
                  haptics.selection();
                  setDetails(!details);
                }}
              />
            </Localized>
            <Localized id="invite-decline">
              <button type="button" className="link" onClick={close} />
            </Localized>
          </div>
        </>
      )}
    </main>
  );
}

/** A name, or Yes when there is only one: the consent and the request in one tap. */
function Pick({
  label,
  main = false,
  busy,
  onPick,
}: {
  label: string;
  main?: boolean;
  busy: boolean;
  onPick: () => void;
}) {
  return (
    <button type="button" className={main ? "btn" : "row-button"} disabled={busy} onClick={onPick}>
      {label}
    </button>
  );
}
