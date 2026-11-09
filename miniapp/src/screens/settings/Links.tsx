import { Localized, useLocalization } from "@fluent/react";
import { lazy, Suspense, useState, type SyntheticEvent } from "react";

import {
  ApiError,
  useCreateShala,
  useMe,
  useMoonCities,
  useMyShalas,
  type MyShala,
  type ShalaRole,
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
import type { Locale } from "../../i18n/negotiate";
import { cityName } from "../MoonCard";

// SC-01: the card is its own lazy chunk, loaded when a shala is opened.
const ShalaScreen = lazy(() => import("../shalas/ShalaScreen"));
const Announcements = lazy(() => import("../announcements/Announcements"));

interface Props {
  onBack: () => void;
  onStudents: () => void;
}

/** "👥 Teachers and students" (ID-04): my teachers, my students, my invite. An invite is
 * confirmed in the bot. A teacher never sees who chose them as main. Loaded lazily, so Settings stays light. Writes are not optimistic. */
export default function Links({ onBack, onStudents }: Props) {
  const [shala, setShala] = useState<string | null>(null);
  const [feed, setFeed] = useState(false);
  const locale: Locale = useMe().data?.locale ?? "en";
  if (feed)
    return (
      <Suspense fallback={null}>
        <Announcements
          mode={{ view: "feed", shala: null }}
          locale={locale}
          onBack={() => {
            setFeed(false);
          }}
        />
      </Suspense>
    );
  if (shala)
    return (
      <Suspense fallback={null}>
        <ShalaScreen
          id={shala}
          onBack={() => {
            setShala(null);
          }}
        />
      </Suspense>
    );
  return (
    <Lists
      onBack={onBack}
      onStudents={onStudents}
      onShala={setShala}
      onFeed={() => {
        setFeed(true);
      }}
    />
  );
}

function Lists({
  onBack,
  onStudents,
  onShala,
  onFeed,
}: Props & { onShala: (id: string) => void; onFeed: () => void }) {
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
      {links && links.teachers.length > 0 && (
        <Localized id="ann-list">
          <button type="button" className="row-button" onClick={onFeed} />
        </Localized>
      )}
      {links && (
        <>
          <Teachers teachers={links.teachers} />
          <Students students={links.students} onOpen={onStudents} />
          <InviteCard hasStudents={links.students.length > 0} />
        </>
      )}
      <Shalas onOpen={onShala} />
    </main>
  );
}

const ROLES: ShalaRole[] = ["teacher", "assistant", "office", "admin"];
const NAME_MAX = 64;

/** SC-01: my shalas, and the create form (Q103: creating is in the Mini App only). */
function Shalas({ onOpen }: { onOpen: (id: string) => void }) {
  const { l10n } = useLocalization();
  const mine = useMyShalas().data;
  const [creating, setCreating] = useState(false);
  return (
    <section className="card">
      <Localized id="links-shalas-title">
        <h2 />
      </Localized>
      {mine?.map((s: MyShala) => (
        <button
          key={s.id}
          type="button"
          className="row-button"
          onClick={() => {
            haptics.selection();
            onOpen(s.id);
          }}
        >
          {l10n.getString("shala-title", { shala: s.name })}
        </button>
      ))}
      {creating ? (
        <CreateShala
          onDone={(id) => {
            setCreating(false);
            onOpen(id);
          }}
        />
      ) : (
        <Localized id="shala-create">
          <button
            type="button"
            className="row-button"
            onClick={() => {
              setCreating(true);
            }}
          />
        </Localized>
      )}
    </section>
  );
}

function CreateShala({ onDone }: { onDone: (id: string) => void }) {
  const { l10n } = useLocalization();
  const me = useMe().data;
  const cities = useMoonCities().data;
  const create = useCreateShala();
  const locale: Locale = me?.locale ?? "en";
  const [name, setName] = useState("");
  const [city, setCity] = useState<string | null>(null);
  const [online, setOnline] = useState(false);
  const [roles, setRoles] = useState<ShalaRole[]>(["teacher"]);
  const [blank, setBlank] = useState(false);
  const chosen = city ?? me?.home_city?.slug ?? cities?.[0]?.slug ?? "";
  const submit = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setBlank(true);
      return;
    }
    setBlank(false);
    haptics.impact("light");
    create.mutate(
      { name, city: chosen, online, roles },
      {
        onSuccess: (shala) => {
          onDone(shala.id);
        },
        onError: () => {
          haptics.notify("error");
        },
      },
    );
  };
  const capped = create.error instanceof ApiError && create.error.code === "shala_caps";
  return (
    <form className="shala-form" onSubmit={submit}>
      <label className="label">
        <Localized id="shala-name-label">
          <span />
        </Localized>
        <input
          type="text"
          value={name}
          maxLength={NAME_MAX}
          onChange={(e) => {
            setName(e.target.value);
          }}
        />
      </label>
      <label className="label">
        <Localized id="shala-city-label">
          <span />
        </Localized>
        <select
          value={chosen}
          onChange={(e) => {
            setCity(e.target.value);
          }}
        >
          {cities?.map((c) => (
            <option key={c.slug} value={c.slug}>
              {cityName(c, c.slug, locale)}
            </option>
          ))}
        </select>
      </label>
      <label className="toggle">
        <input
          type="checkbox"
          checked={online}
          onChange={() => {
            setOnline(!online);
          }}
        />
        {l10n.getString("shala-online-only")}
      </label>
      <Localized id="shala-my-roles">
        <p className="label" />
      </Localized>
      {ROLES.map((role) => (
        <label key={role} className="toggle">
          <input
            type="checkbox"
            checked={roles.includes(role)}
            onChange={() => {
              setRoles((now) =>
                now.includes(role) ? now.filter((r) => r !== role) : [...now, role],
              );
            }}
          />
          {l10n.getString("shala-role", { role })}
        </label>
      ))}
      <Localized id="shala-create-submit">
        <button type="submit" className="row-button" disabled={create.isPending} />
      </Localized>
      {(blank || create.isError) && (
        <Localized
          id={
            blank ||
            (create.error instanceof ApiError && create.error.code === "invalid_shala_name")
              ? "shala-name-invalid"
              : capped
                ? "shala-caps"
                : "shala-save-failed"
          }
        >
          <p className="hint" role="alert" />
        </Localized>
      )}
    </form>
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

function Students({ students, onOpen }: { students: LinkedStudent[]; onOpen: () => void }) {
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
      {students.length > 0 && (
        <Localized id="link-students-open">
          <button type="button" className="row-button" onClick={onOpen} />
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
