import { Localized, useLocalization } from "@fluent/react";
import { Fragment, Suspense, useEffect, useRef, useState, type Ref } from "react";

import {
  useInvite,
  useLinks,
  useMakeMainTeacher,
  useMe,
  useMyShalas,
  useRemoveTeacher,
  type Invite,
  type LinkedTeacher,
  type TeacherLinks,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { lazyRetry } from "../../shell/lazyRetry";
import type { ShalaOpen, Start } from "../../shell/nav";
import { confirmDestructive, haptics, openTelegramLink } from "../../telegram";
import { Row } from "../Row";
import { checkedMonth, useListing, type ListingMark } from "../settings/listing";
import { useWithdrawRequest, type AskedTeacher } from "../teachers/requests";
import { Waiting } from "../teachers/Waiting";
import CreateShala from "./CreateShala";
import "./shala.css";

// SC-01: the card is its own lazy chunk, loaded when a shala is opened.
const ShalaScreen = lazyRetry(() => import("./ShalaScreen"));
const Announcements = lazyRetry(() => import("../announcements/Announcements"));
// ID-05: the form (and its copy) loads when the row is tapped.
const DirectoryListing = lazyRetry(() => import("../settings/DirectoryListing"));

interface Props {
  /** My students (ST-06), from the "👥 My students" row. */
  onStudents: () => void;
  /** My schedule (SC-03), the first row for anyone in a shala. */
  onSchedule: () => void;
  /** UI-06: a one-time intent. `create`: the bot's "Create a shala" (`?open=new-shala`), the
   * group's create form open with its name focused. `invite`: the group's invite open.
   * `shala:<id>`: that shala's card open; `class:<id>`, `join:<id>` and `announce:<id>`: that
   * card with its class form, its student invite or its message form open. */
  start?: Start | null | undefined;
  /** The shell focuses the heading after a tab switch. */
  headingRef?: Ref<HTMLHeadingElement> | undefined;
}

/** What a start opens in the group "For teachers and shalas". */
type Intent = "create" | "invite";

const CARD = /^(shala|class|join|announce):(.+)$/;
/** The shala card a start opens, and what for. */
function cardOf(start: Start | null): { id: string; open?: ShalaOpen } | null {
  const [, kind, id] = (start && CARD.exec(start)) ?? [];
  if (!id) return null;
  return kind === "shala" ? { id } : { id, open: kind as ShalaOpen };
}

/** The Shala tab's root (UI-06 stage 4B, spec §3): one list in a fixed order, each part only
 * when it has something, the first row the main one: the people waiting for my answer, my
 * schedule, my shalas, my teachers, my students, then the quiet group for teachers and shalas.
 * A root registers no Back layer; a shala's card, the announcements and the directory line
 * open over it and do. Loaded lazily. Writes are not optimistic. */
export default function ShalaTab({ onStudents, onSchedule, start = null, headingRef }: Props) {
  // Once: back on the list, a tap on the same shala opens its card plainly.
  const [shala, setShala] = useState(() => cardOf(start));
  const [feed, setFeed] = useState(false);
  const [listing, setListing] = useState(false);
  // Once: coming back from a card, the feed or the directory line finds the group closed.
  const [intent, setIntent] = useState<Intent | null>(
    start === "create" || start === "invite" ? start : null,
  );
  // After a start the list draws at once, and never as "nobody yet".
  const begun = start === "create" || start === "invite";
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
    <Root
      onStudents={onStudents}
      onSchedule={onSchedule}
      headingRef={headingRef}
      intent={intent}
      begun={begun}
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

function Root({
  onStudents,
  onSchedule,
  headingRef,
  intent,
  begun,
  onShala,
  onFeed,
  onListing,
  locale,
}: Pick<Props, "onStudents" | "onSchedule" | "headingRef"> & {
  intent: Intent | null;
  begun: boolean;
  onShala: (id: string) => void;
  onFeed: () => void;
  onListing: () => void;
  locale: Locale;
}) {
  const { l10n } = useLocalization();
  const query = useLinks();
  const links = query.data;
  // ID-07: the teachers I asked and wait for, and how many people wait for my answer. An
  // older payload has neither.
  const { asked = [], waiting = 0 }: Partial<TeacherLinks> = links ?? {};
  const shalas = useMyShalas();
  const mine = shalas.data ?? [];
  const students = links?.students.length ?? 0;
  // QC: the people waiting for my answer, on top. Read only when someone waits; once shown it
  // stays for this visit, so the Undo and the line after the last answer stay on screen.
  const [answering, setAnswering] = useState(false);
  if (waiting > 0 && !answering) setAnswering(true);
  // Both lists decide between the list and "nobody yet": neither is drawn on a guess.
  const settled = begun || ((links || query.isError) && (shalas.data || shalas.isError));
  const nobody =
    !begun &&
    links?.teachers.length === 0 &&
    students === 0 &&
    asked.length === 0 &&
    waiting === 0 &&
    shalas.data?.length === 0;
  // The first row present is the main one (spec §3). UI-06 stage 4B slice 3: "🤝 Pick a
  // teacher" (QA) comes first and takes it when it shows.
  const main = mine.length > 0 ? "schedule" : students > 0 ? "students" : null;
  return (
    <main className="screen shala-tab" aria-busy={settled ? undefined : true}>
      <Localized id="tab-shala">
        <h1 ref={headingRef} tabIndex={-1} />
      </Localized>
      {query.isError && (
        <Localized id="links-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {nobody && (
        <Localized id="shala-empty">
          <p className="hint" />
        </Localized>
      )}
      {settled && (
        <>
          {/* UI-06 stage 4B slice 3: the result line of an ask or a withdraw (§3 row 1) goes
              here, above the waiting block. */}
          {answering && <Waiting />}
          {/* UI-06 stage 4B slice 3: "🤝 Pick a teacher" (§3 row 3, QA) goes here. */}
          {mine.length > 0 && (
            <Door
              label={l10n.getString("my-schedule-open")}
              main={main === "schedule"}
              onOpen={onSchedule}
            />
          )}
          {mine.map((s) => (
            <Door
              key={s.id}
              label={l10n.getString("shala-title", { shala: s.name })}
              onOpen={() => {
                onShala(s.id);
              }}
            />
          ))}
          {links && (links.teachers.length > 0 || asked.length > 0) && (
            <Teachers teachers={links.teachers} asked={asked} locale={locale} onFeed={onFeed} />
          )}
          {/* QD: one row; the names, their week and Remove are on My students. */}
          {students > 0 && (
            <Door
              label={l10n.getString("link-students-open")}
              main={main === "students"}
              onOpen={onStudents}
            />
          )}
          <Group
            intent={intent}
            hasStudents={students > 0}
            onCreated={onShala}
            onListing={onListing}
          />
        </>
      )}
    </main>
  );
}

/** A row of the list that opens a place. The main one is the filled button (as the setup
 * list's due step); the others are plain rows. */
function Door({
  label,
  main = false,
  onOpen,
}: {
  label: string;
  main?: boolean;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      className={main ? "btn" : "row-button"}
      onClick={() => {
        haptics.selection();
        onOpen();
      }}
    >
      {label}
    </button>
  );
}

/** "For teachers and shalas" (UI-06): always there, quiet and last, as list rows under the
 * bot's name for that row, so a student reads past them. Invite and the create form open in
 * place, one at a time (the form ready to type); a start opens one of them. */
function Group({
  intent,
  hasStudents,
  onCreated,
  onListing,
}: {
  intent: Intent | null;
  hasStudents: boolean;
  onCreated: (id: string) => void;
  onListing: () => void;
}) {
  const { l10n } = useLocalization();
  const [open, setOpen] = useState<Intent | null>(intent);
  const toggle = (what: Intent) => () => {
    haptics.selection();
    setOpen(open === what ? null : what);
  };
  return (
    <>
      <Localized id="shala-starts-title">
        <h2 className="starts" />
      </Localized>
      <section className="card list">
        <Row
          label={l10n.getString(hasStudents ? "links-invite" : "shala-start-invite")}
          expanded={open === "invite"}
          onClick={toggle("invite")}
        />
        {open === "invite" && <InvitePanel />}
        <Row
          label={l10n.getString("shala-start-shala")}
          expanded={open === "create"}
          onClick={toggle("create")}
        />
        {open === "create" && (
          <CreateShala
            focus
            onDone={(id) => {
              setOpen(null);
              onCreated(id);
            }}
          />
        )}
        <ListingRow onOpen={onListing} />
      </section>
    </>
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
  const { l10n } = useLocalization();
  const { data } = useListing();
  const mine = data && data.status !== "none" && data.status !== "withdrawn";
  if (!data || !(data.available || mine)) return null;
  return (
    <Row
      label={l10n.getString("listing-open")}
      onClick={() => {
        haptics.selection();
        onOpen();
      }}
    />
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

/** My teachers (ID-04) and the teachers I asked (ID-07), then their announcements. Shown only
 * with a teacher or a request: no empty card. */
function Teachers({
  teachers,
  asked,
  locale,
  onFeed,
}: {
  teachers: LinkedTeacher[];
  asked: AskedTeacher[];
  locale: Locale;
  onFeed: () => void;
}) {
  const { l10n } = useLocalization();
  const name = useName();
  const makeMain = useMakeMainTeacher();
  const remove = useRemoveTeacher();
  const withdraw = useWithdrawRequest();
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

  const confirmWithdraw = async (teacher: AskedTeacher) => {
    const ok = await confirmDestructive(
      l10n.getString("request-withdraw-ask", { name: short(name(teacher.name)) }),
      l10n.getString("request-withdraw-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("light");
    withdraw.mutate(teacher.teacher_id);
  };

  return (
    <section className="card teachers">
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
      {/* ID-07: a teacher I asked in a shala. The line is the same whatever the teacher did:
          the name, the shala and Withdraw, with no state, date or count. */}
      {asked.map((teacher) => (
        <Fragment key={teacher.teacher_id}>
          <div className="link-person">
            <span>{name(teacher.name)}</span>
            <Localized id="request-withdraw">
              <button
                type="button"
                className="link"
                disabled={withdraw.isPending}
                onClick={() => {
                  void confirmWithdraw(teacher);
                }}
              />
            </Localized>
          </div>
          <p className="hint small asked-line">
            {l10n.getString("request-waiting-line", { shala: teacher.shala.name })}
          </p>
        </Fragment>
      ))}
      {withdraw.isError && (
        <Localized id="settings-save-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {teachers.length > 0 && (
        <Localized id="ann-list">
          <button
            type="button"
            className="row-button"
            onClick={() => {
              haptics.selection();
              onFeed();
            }}
          />
        </Localized>
      )}
    </section>
  );
}

/** My teacher invite (ID-04), open under its row: the link is asked for when it opens, never
 * built here, and the QR comes from the API. */
function InvitePanel() {
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
  // Once per opening, as a tap on the row asks for it.
  const asked = useRef(false);
  useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, when it opens
  }, []);
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

  return (
    <div className="panel invite" aria-busy={shown || invite.isError ? undefined : true}>
      {shown && (
        <>
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
        </>
      )}
      {invite.isError && (
        <Localized id="settings-save-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </div>
  );
}
