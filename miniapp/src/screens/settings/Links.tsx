import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import {
  useInvite,
  useLinks,
  useMakeMainTeacher,
  useRemoveStudent,
  useRemoveTeacher,
  type Invite,
  type LinkedStudent,
  type LinkedTeacher,
} from "../../api/client";
import {
  backButtonAvailable,
  confirmDestructive,
  haptics,
  openTelegramLink,
  useBackButton,
} from "../../telegram";

interface Props {
  onBack: () => void;
}

/** "👥 Teachers and students" (ID-04): my teachers, my students, my invite. Only names cross
 * accounts, and an invite is confirmed in the bot. A teacher never sees who chose them as
 * main. Loaded lazily, so Settings stays light. Writes are not optimistic. */
export default function Links({ onBack }: Props) {
  useBackButton(onBack);
  const query = useLinks();
  const links = query.data;
  return (
    <main className="screen links">
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      <Localized id="links-title">
        <h1 />
      </Localized>
      {query.isError && (
        <Localized id="links-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {links && (
        <>
          <Teachers teachers={links.teachers} />
          <Students students={links.students} />
          <InviteCard hasStudents={links.students.length > 0} />
        </>
      )}
    </main>
  );
}

/** Telegram popups take 256 characters, and two long names can pass that in Russian. */
const POPUP_NAME_MAX = 40;
const short = (name: string) =>
  name.length > POPUP_NAME_MAX ? `${name.slice(0, POPUP_NAME_MAX)}…` : name;

function useName() {
  const { l10n } = useLocalization();
  return (name: string | null) => name ?? l10n.getString("link-no-name");
}

function Teachers({ teachers }: { teachers: LinkedTeacher[] }) {
  const { l10n } = useLocalization();
  const name = useName();
  const makeMain = useMakeMainTeacher();
  const remove = useRemoveTeacher();
  const several = teachers.length >= 2;
  const main = teachers.find((t) => t.primary);

  const confirmRemove = async (teacher: LinkedTeacher) => {
    const parts = [l10n.getString("link-unlink-ask", { name: short(name(teacher.name)) })];
    // Oldest first, as the API sorts them: the same rule the server reads the default by.
    const next = teacher.primary ? teachers.find((t) => t.id !== teacher.id) : undefined;
    if (next) parts.push(l10n.getString("link-next-main", { name: short(name(next.name)) }));
    const ok = await confirmDestructive(
      parts.join(" "),
      l10n.getString("links-remove-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("light");
    remove.mutate(teacher.id);
  };

  return (
    <section className="card">
      {teachers.length === 0 && (
        <Localized id="links-empty">
          <p className="hint" />
        </Localized>
      )}
      {several && main && (
        <>
          <p>
            {l10n.getString(main.primary_chosen ? "links-main-chosen" : "links-main-auto", {
              name: name(main.name),
            })}
          </p>
          <Localized id="links-primary-hint">
            <p className="hint" />
          </Localized>
        </>
      )}
      {teachers.map((teacher) => (
        <div className="link-person" key={teacher.id}>
          <span>{name(teacher.name)}</span>
          {several && !teacher.primary && (
            <Localized id="links-make-main">
              <button
                type="button"
                className="link"
                disabled={makeMain.isPending}
                onClick={() => {
                  haptics.selection();
                  makeMain.mutate(teacher.id);
                }}
              />
            </Localized>
          )}
          <Localized id="links-remove">
            <button
              type="button"
              className="link"
              onClick={() => {
                void confirmRemove(teacher);
              }}
            />
          </Localized>
        </div>
      ))}
    </section>
  );
}

function Students({ students }: { students: LinkedStudent[] }) {
  const { l10n } = useLocalization();
  const name = useName();
  const remove = useRemoveStudent();

  const confirmRemove = async (student: LinkedStudent) => {
    const ok = await confirmDestructive(
      l10n.getString("link-remove-ask", { name: name(student.name) }),
      l10n.getString("links-remove-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("light");
    remove.mutate(student.id);
  };

  return (
    <section className="card">
      {students.length === 0 && (
        <Localized id="links-no-students">
          <p className="hint" />
        </Localized>
      )}
      {students.map((student) => (
        <div className="link-person" key={student.id}>
          <span>{name(student.name)}</span>
          <Localized id="links-remove">
            <button
              type="button"
              className="link"
              onClick={() => {
                void confirmRemove(student);
              }}
            />
          </Localized>
        </div>
      ))}
    </section>
  );
}

function InviteCard({ hasStudents }: { hasStudents: boolean }) {
  const { l10n } = useLocalization();
  const invite = useInvite();
  const [shown, setShown] = useState<Invite | null>(null);
  const [copied, setCopied] = useState(false);

  const load = (rotate: boolean) => {
    invite.mutate(rotate, {
      onSuccess: (found) => {
        setShown(found);
        setCopied(false);
      },
      onError: () => {
        haptics.notify("error");
      },
    });
  };
  const rotate = async () => {
    const ok = await confirmDestructive(
      l10n.getString("invite-new-ask"),
      l10n.getString("invite-new-yes"),
      l10n.getString("delete-cancel"),
    );
    if (ok) load(true);
  };
  const copy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      haptics.notify("success");
      setCopied(true);
    } catch {
      haptics.notify("error"); // no clipboard here: the link stays on screen to select
    }
  };
  const share = (url: string) => {
    const text = l10n.getString("invite-share-text");
    openTelegramLink(
      `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`,
    );
  };

  if (!shown) {
    return (
      <>
        <Localized id={hasStudents ? "links-invite" : "links-invite-first"}>
          <button
            type="button"
            className="row-button"
            disabled={invite.isPending}
            onClick={() => {
              load(false);
            }}
          />
        </Localized>
        {invite.isError && (
          <Localized id="settings-save-failed">
            <p className="hint" role="alert" />
          </Localized>
        )}
      </>
    );
  }
  return (
    <section className="card invite">
      <img className="invite-qr" src={shown.qr} alt={l10n.getString("invite-qr-alt")} />
      <p className="invite-url">{shown.url}</p>
      <Localized id="invite-hint">
        <p className="hint" />
      </Localized>
      <Localized id={copied ? "invite-copied" : "invite-copy"}>
        <button
          type="button"
          className="row-button"
          onClick={() => {
            void copy(shown.url);
          }}
        />
      </Localized>
      <Localized id="invite-share">
        <button
          type="button"
          className="row-button"
          onClick={() => {
            share(shown.url);
          }}
        />
      </Localized>
      <Localized id="invite-new">
        <button
          type="button"
          className="row-button"
          disabled={invite.isPending}
          onClick={() => {
            void rotate();
          }}
        />
      </Localized>
      {invite.isError && (
        <Localized id="settings-save-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </section>
  );
}
