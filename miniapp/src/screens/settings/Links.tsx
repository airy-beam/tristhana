import { Localized, useLocalization } from "@fluent/react";
import {
  Fragment,
  Suspense,
  useEffect,
  useRef,
  useState,
  type Ref,
  type SyntheticEvent,
} from "react";

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
import { confirmDestructive, haptics, openTelegramLink } from "../../telegram";
import type { Locale } from "../../i18n/negotiate";
import { lazyRetry } from "../../shell/lazyRetry";
import type { ShalaOpen, Start } from "../../shell/nav";
import { cityName } from "../cityName";
import { Row } from "../Row";
import { checkedMonth, useListing, type ListingMark } from "./listing";

// SC-01: the card is its own lazy chunk, loaded when a shala is opened.
const ShalaScreen = lazyRetry(() => import("../shalas/ShalaScreen"));
const Announcements = lazyRetry(() => import("../announcements/Announcements"));
// ID-05: the form (and its copy) loads when the row is tapped.
const DirectoryListing = lazyRetry(() => import("./DirectoryListing"));

interface Props {
  /** My students (ST-06), from the row in the students card. */
  onStudents: () => void;
  /** My schedule (SC-03), the first row for anyone in a shala. */
  onSchedule: () => void;
  /** UI-06: a one-time intent. `create`: the bot's "Create a shala" (`?open=new-shala`), the
   * form open with its name focused. `invite`: the invite card open. `shala:<id>`: that
   * shala's card open; `class:<id>` and `join:<id>`: that card with its class form or its
   * student invite open (Today's next step). */
  start?: Start | null | undefined;
  /** The shell focuses the heading after a tab switch. */
  headingRef?: Ref<HTMLHeadingElement> | undefined;
}

/** What a start opens on the lists themselves. */
type Intent = "create" | "invite";

const CARD = /^(shala|class|join):(.+)$/;
/** The shala card a start opens, and what for. */
function cardOf(start: Start | null): { id: string; open?: ShalaOpen } | null {
  const [, kind, id] = (start && CARD.exec(start)) ?? [];
  if (!id) return null;
  return kind === "class" || kind === "join" ? { id, open: kind } : { id };
}

/** The Shala tab's root (UI-06): my schedule, my teachers, my students, my invite, my shalas
 * (ID-04, SC-01). A root registers no Back layer; a shala's card, the announcements and the
 * directory line open over it and do. An invite is confirmed in the bot. A teacher never sees
 * who chose them as main. Loaded lazily. Writes are not optimistic. */
export default function Links({ onStudents, onSchedule, start = null, headingRef }: Props) {
  // Once: back on the lists, a tap on the same shala opens its card plainly.
  const [shala, setShala] = useState(() => cardOf(start));
  const [feed, setFeed] = useState(false);
  const [listing, setListing] = useState(false);
  // Once: coming back from a card, the feed or the directory line finds the form closed.
  const [intent, setIntent] = useState<Intent | null>(
    start === "create" || start === "invite" ? start : null,
  );
  // After a start the full layout stays, also for someone with nobody on it yet.
  const [begun, setBegun] = useState(intent !== null);
  const locale: Locale = useMe().data?.locale ?? "en";
  if (listing)
    return (
      <Suspense fallback={null}>
        <DirectoryListing
          locale={locale}
          onBack={() => {
            setListing(false);
          }}
        />
      </Suspense>
    );
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
          id={shala.id}
          open={shala.open}
          onBack={() => {
            setShala(null);
          }}
        />
      </Suspense>
    );
  return (
    <Lists
      onStudents={onStudents}
      onSchedule={onSchedule}
      headingRef={headingRef}
      intent={intent}
      begun={begun}
      onStart={(chosen) => {
        setIntent(chosen);
        setBegun(true);
      }}
      onShala={(id) => {
        setIntent(null);
        setShala({ id });
      }}
      onFeed={() => {
        setIntent(null);
        setFeed(true);
      }}
      onListing={() => {
        setIntent(null);
        setListing(true);
      }}
      locale={locale}
    />
  );
}

function Lists({
  onStudents,
  onSchedule,
  headingRef,
  intent,
  begun,
  onStart,
  onShala,
  onFeed,
  onListing,
  locale,
}: Pick<Props, "onStudents" | "onSchedule" | "headingRef"> & {
  intent: Intent | null;
  begun: boolean;
  onStart: (intent: Intent) => void;
  onShala: (id: string) => void;
  onFeed: () => void;
  onListing: () => void;
  locale: Locale;
}) {
  const query = useLinks();
  const links = query.data;
  const shalas = useMyShalas();
  // Both lists decide between the layout and "nobody yet": neither is drawn on a guess.
  const settled = begun || ((links || query.isError) && (shalas.data || shalas.isError));
  const nobody =
    !begun &&
    links?.teachers.length === 0 &&
    links.students.length === 0 &&
    shalas.data?.length === 0;
  return (
    <main className="screen links" aria-busy={settled ? undefined : true}>
      <Localized id="tab-shala">
        <h1 ref={headingRef} tabIndex={-1} />
      </Localized>
      {query.isError && (
        <Localized id="links-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {nobody ? (
        <Nobody onStart={onStart} />
      ) : (
        settled && (
          <>
            {shalas.data && shalas.data.length > 0 && (
              <Localized id="my-schedule-open">
                <button
                  type="button"
                  className="row-button"
                  onClick={() => {
                    haptics.selection();
                    onSchedule();
                  }}
                />
              </Localized>
            )}
            {links && links.teachers.length > 0 && (
              <Localized id="ann-list">
                <button type="button" className="row-button" onClick={onFeed} />
              </Localized>
            )}
            {links && (
              <>
                <Teachers teachers={links.teachers} locale={locale} />
                <Students students={links.students} onOpen={onStudents} />
                <InviteCard hasStudents={links.students.length > 0} open={intent === "invite"} />
                <ListingRow onOpen={onListing} />
              </>
            )}
            <Shalas onOpen={onShala} create={intent === "create"} />
          </>
        )
      )}
    </main>
  );
}

/** Nobody yet (UI-06): no teacher, no student, no shala. One plain line, then two starts as
 * list rows in one small card, with the bot's labels under the bot's name for that row, so a
 * student reads past them. */
function Nobody({ onStart }: { onStart: (intent: Intent) => void }) {
  const { l10n } = useLocalization();
  const start = (intent: Intent) => () => {
    haptics.selection();
    onStart(intent);
  };
  return (
    <>
      <Localized id="shala-empty">
        <p className="hint" />
      </Localized>
      <Localized id="shala-starts-title">
        <h2 className="starts" />
      </Localized>
      <div className="card list">
        <Row label={l10n.getString("shala-start-invite")} onClick={start("invite")} />
        <Row label={l10n.getString("shala-start-shala")} onClick={start("create")} />
      </div>
    </>
  );
}

const ROLES: ShalaRole[] = ["teacher", "assistant", "office", "admin"];
const NAME_MAX = 64;

/** SC-01: my shalas, and the create form (Q103: creating is in the Mini App only). */
function Shalas({ onOpen, create }: { onOpen: (id: string) => void; create: boolean }) {
  const { l10n } = useLocalization();
  const mine = useMyShalas().data;
  const [creating, setCreating] = useState(create);
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
          focus={create}
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

function CreateShala({ onDone, focus }: { onDone: (id: string) => void; focus: boolean }) {
  const { l10n } = useLocalization();
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (focus) first.current?.focus();
  }, [focus]);
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
          ref={first}
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

/** ID-05: the quiet way in to the directory line. Hidden while it loads, and when requests
 * aren't taken (`available` false) unless I have a request or a line to look at or remove;
 * its failure is never this screen's error. */
function ListingRow({ onOpen }: { onOpen: () => void }) {
  const { data } = useListing();
  const mine = data && data.status !== "none" && data.status !== "withdrawn";
  if (!data || !(data.available || mine)) return null;
  return (
    <Localized id="listing-open">
      <button
        type="button"
        className="row-button"
        onClick={() => {
          haptics.selection();
          onOpen();
        }}
      />
    </Localized>
  );
}

/** ID-05: the directory line, its own element under the name (never part of it). A tap opens
 * what it means, and only there the level in the teacher's own words. A teacher without a
 * line renders nothing at all. */
function ListingLine({ mark, locale }: { mark: ListingMark; locale: Locale }) {
  const { l10n } = useLocalization();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="listing-mark"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
        }}
      >
        {l10n.getString("listing-mark", {
          listed: mark.name_as_listed,
          when: checkedMonth(mark.checked_on, locale),
        })}
      </button>
      {open && (
        <>
          {mark.declared_level && (
            <p className="hint small">
              {l10n.getString("listing-level", {
                level: l10n.getString("listing-level-name", { level: mark.declared_level }),
              })}
            </p>
          )}
          <Localized id="listing-about">
            <p className="hint small" />
          </Localized>
        </>
      )}
    </>
  );
}

function Teachers({ teachers, locale }: { teachers: LinkedTeacher[]; locale: Locale }) {
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
        <Fragment key={teacher.id}>
          <div className="link-person">
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
          {teacher.listing && <ListingLine mark={teacher.listing} locale={locale} />}
        </Fragment>
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

function InviteCard({ hasStudents, open }: { hasStudents: boolean; open: boolean }) {
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
  // UI-06: "Invite students" opens the card itself, as a tap on the row would.
  const opened = useRef(false);
  useEffect(() => {
    if (!open || opened.current) return;
    opened.current = true;
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, when asked to open
  }, [open]);
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
