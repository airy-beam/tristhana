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
  useDeleteShala,
  useMe,
  useMoonCities,
  useRemoveShalaMember,
  useSetDayOff,
  useSetStaffRoles,
  useShala,
  useShalaJoinLink,
  useShalaStaffInvite,
  useShalaStudents,
  useUpdateShala,
  SHALA_STUDENTS_PAGE,
  type MoonPolicy,
  type Occurrence,
  type Shala,
  type ShalaLink,
  type ShalaRole,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { lazyRetry } from "../../shell/lazyRetry";
import type { ShalaOpen } from "../../shell/nav";
import {
  backButtonAvailable,
  confirmDestructive,
  haptics,
  openTelegramLink,
  useBackButton,
} from "../../telegram";
import { Chips } from "../../ui/Chips";
import { Check, Field, Select, TextInput } from "../../ui/controls";
import { cityName } from "../cityName";
import { Row } from "../Row";
import { labelOf } from "../settings/zones";
import { AskedLines, SaidLine } from "../teachers/Asked";
import { useTeacherChoices, type Said } from "../teachers/requests";
import { ownZone } from "../timeLabel";
import ClassForm, { type ClassEdit, type FormResult } from "./ClassForm";
import ShalaSchedule from "./ShalaSchedule";
import { WEEKDAYS, weekdayShort } from "./scheduleText";
import { SetupList, type SetupStep } from "./SetupList";
import "./shala.css";

const ROLES: ShalaRole[] = ["teacher", "assistant", "office", "admin"];
type Me = Shala["me"];

// The same rules as `application/policies.py`; the server decides, this only hides buttons.
const isStaff = (me: Me) => !me.student;
const manages = (me: Me) => isStaff(me) && (me.owner || me.roles.includes("admin"));
const grantable = (me: Me): ShalaRole[] =>
  me.owner ? ROLES : manages(me) ? ROLES.filter((r) => r !== "admin") : [];
// An owner's own roles are theirs to change (Q338): the one staff row with `owner` is mine.
const canEditRoles = (me: Me, target: Shala["staff"][number]) =>
  target.owner
    ? me.owner
    : grantable(me).length > 0 && (me.owner || !target.roles.includes("admin"));
/** What an owner may hold beside owning: never Manager (they already manage). */
const OWN_ROLES: ShalaRole[] = ["teacher", "assistant", "office"];
const canRemoveStudents = (me: Me) =>
  isStaff(me) && (me.owner || me.roles.includes("admin") || me.roles.includes("office"));

const plain = (text: string) => text.replace(/[\u2068\u2069]/g, "");

/** Telegram popups take 256 characters, and a long name can pass that in Russian. */
const POPUP_NAME_MAX = 40;
const short = (name: string) =>
  name.length > POPUP_NAME_MAX ? `${name.slice(0, POPUP_NAME_MAX)}…` : name;

interface Props {
  id: string;
  onBack: () => void;
  week?: number | undefined; // the schedule's first week shown (0-3), from My schedule
  /** UI-06: opened for one thing (Today's next step, the bot's "📣 Announce" from this shala):
   * the class form, the student invite or the message form is open and in view. Once: not
   * again after the announcements were opened from here. */
  open?: ShalaOpen | undefined;
}

/** The shala card (SC-01): the place, its zone, its moon city and its staff for every member;
 * students, links, roles and delete per role. Students never see other students. The class
 * form and the announcements open over the card as layers of their own (UI-06 stage 4); the
 * card stays mounted under them, so Back finds the week, the open date and the scroll as they
 * were left, and the focus returns to the row that opened the layer. */
const Announcements = lazyRetry(() => import("../announcements/Announcements"));
// UI-06 stage 4B: "🤝 Pick a teacher" opens the picker (and its copy) over the card.
const AskTeacher = lazyRetry(() => import("../teachers/AskTeacher"));

/** The class form: a new class, or a saved one opened from a date. */
type Form = { edit?: ClassEdit };

export default function ShalaScreen({ id, onBack, week, open }: Props) {
  const me = useMe().data;
  const locale: Locale = me?.locale ?? "en";
  const shala = useShala(id).data;
  const [announcements, setAnnouncements] = useState<{
    view: "feed" | "compose";
    draft?: string;
  } | null>(null);
  const [opened, setOpened] = useState(open);
  const [form, setForm] = useState<Form | null>(open === "class" ? {} : null);
  const [gone, setGone] = useState(false);
  // A student asking a teacher here, and the line the ask or a withdraw left (QE).
  const [asking, setAsking] = useState(false);
  const [said, setSaid] = useState<Said | null>(null);
  // Only for those who manage classes; a start asking for the form leaves the others the card.
  const editing = form !== null && shala?.me.schedule === true;
  // QF: only for those who may announce here; the others (and a former member) get the card.
  const layer =
    announcements ??
    (opened === "announce" && shala?.me.announce ? { view: "compose" as const } : null);
  const covered = editing || layer !== null || asking;
  // Where the card was scrolled when a layer opened, and what had the focus, to give both back.
  const left = useRef<{ top: number; from: Element | null } | null>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const wasCovered = useRef(covered);
  useEffect(() => {
    const uncovered = wasCovered.current && !covered;
    wasCovered.current = covered;
    if (!uncovered) return;
    if (left.current === null) {
      // A layer a start opened (the bot's "📣 Announce", Today's "add a class"): nothing on the
      // card had the focus, so the card's title takes it rather than the page's body.
      window.scrollTo({ top: 0 });
      title.current?.focus({ preventScroll: true });
      return;
    }
    const { top, from } = left.current;
    left.current = null;
    window.scrollTo({ top });
    // The row may be gone with its class; then the focus stays where the browser put it.
    if (from instanceof HTMLElement && from.isConnected) from.focus({ preventScroll: true });
  }, [covered]);
  const cover = () => {
    left.current = { top: window.scrollY, from: document.activeElement };
    window.scrollTo({ top: 0 });
  };
  const openForm = (next: Form) => {
    cover();
    setGone(false);
    setForm(next);
  };
  const closeForm = (result?: FormResult) => {
    setForm(null);
    setOpened(undefined);
    setGone(result === "gone");
  };
  return (
    <>
      <div hidden={covered}>
        <Card
          id={id}
          onBack={onBack}
          week={week}
          open={opened}
          gone={gone}
          said={said}
          titleRef={title}
          onSaid={setSaid}
          onPick={() => {
            cover();
            setAsking(true);
          }}
          onAnnouncements={(view, draft) => {
            cover();
            setOpened(undefined);
            setAnnouncements(draft === undefined ? { view } : { view, draft });
          }}
          onAdd={() => {
            openForm({});
          }}
          onEdit={(o) => {
            openForm({ edit: { classId: o.class_id, date: o.key, startsAt: o.starts_at } });
          }}
        />
      </div>
      {editing && <ClassForm shala={shala} edit={form.edit} onDone={closeForm} />}
      {asking && shala && (
        <Suspense fallback={<main className="screen" aria-busy="true" />}>
          <AskTeacher
            shala={shala}
            onDone={(line) => {
              // The line takes the focus; the scroll goes back to where the card was.
              if (line && left.current) left.current = { ...left.current, from: null };
              setAsking(false);
              if (line) setSaid(line);
            }}
          />
        </Suspense>
      )}
      {layer && (
        <Suspense fallback={<main className="screen" aria-busy="true" />}>
          <Announcements
            mode={{ ...layer, shala: id }}
            locale={locale}
            onBack={() => {
              setAnnouncements(null);
              setOpened(undefined);
            }}
          />
        </Suspense>
      )}
    </>
  );
}

interface CardProps extends Props {
  gone: boolean;
  said: Said | null;
  titleRef: Ref<HTMLHeadingElement>;
  onSaid: (said: Said) => void;
  onPick: () => void;
  onAnnouncements: (view: "feed" | "compose", draft?: string) => void;
  onAdd: () => void;
  onEdit: (occurrence: Occurrence) => void;
}

function Card({
  id,
  onBack,
  week,
  open,
  gone,
  said,
  titleRef,
  onSaid,
  onPick,
  onAnnouncements,
  onAdd,
  onEdit,
}: CardProps) {
  useBackButton(onBack);
  const { l10n } = useLocalization();
  const query = useShala(id);
  const me = useMe().data;
  const shala = query.data;
  const locale: Locale = me?.locale ?? "en";
  // The invite a start or a setup step asks for: a new number each time it is asked.
  const [ask, setAsk] = useState({ join: open === "join" ? 1 : 0, staff: 0 });
  const setup = (step: SetupStep) => {
    if (step === "add_class") onAdd();
    else if (step === "invite_students") setAsk((n) => ({ ...n, join: n.join + 1 }));
    else setAsk((n) => ({ ...n, staff: n.staff + 1 }));
  };
  return (
    <main className="screen shala">
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      {query.isError && (
        <Localized id="shala-load-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {shala && (
        <>
          <h1 ref={titleRef} tabIndex={-1}>
            {l10n.getString("shala-title", { shala: shala.name })}
          </h1>
          {said && <SaidLine said={said} />}
          {shala.me.student && <Asking shala={shala} onSaid={onSaid} onPick={onPick} />}
          <SetupList shala={shala} onOpen={setup} />
          <Place shala={shala} locale={locale} viewer={me?.timezone} />
          <DayOffOffer shala={shala} />
          <section className="card">
            <Localized id="ann-list">
              <button
                type="button"
                className="row-button"
                onClick={() => {
                  onAnnouncements("feed");
                }}
              />
            </Localized>
            {shala.me.announce && (
              <Localized id="ann-announce">
                <button
                  type="button"
                  className="row-button"
                  onClick={() => {
                    onAnnouncements("compose");
                  }}
                />
              </Localized>
            )}
          </section>
          {manages(shala.me) && <Edit shala={shala} locale={locale} />}
          <ShalaSchedule
            shala={shala}
            week={week ?? 0}
            gone={gone}
            onAdd={onAdd}
            onEdit={onEdit}
            onTell={(draft) => {
              onAnnouncements("compose", draft);
            }}
          />
          <Staff shala={shala} />
          {isStaff(shala.me) && <Students shala={shala} />}
          {isStaff(shala.me) && <JoinLink shala={shala} ask={ask.join} />}
          {grantable(shala.me).length > 0 && <StaffInvite shala={shala} ask={ask.staff} />}
          <Leave shala={shala} myId={me?.id} onDone={onBack} />
          {shala.me.owner && <Delete shala={shala} onDone={onBack} />}
        </>
      )}
    </main>
  );
}

/** ID-07, UI-06 stage 4B (spec §4): the bot's student part of the card. One line per teacher I
 * wait for here, each with Withdraw, then "🤝 Pick a teacher" while someone can be picked.
 * Students only: staff never read who can be picked. */
function Asking({
  shala,
  onSaid,
  onPick,
}: {
  shala: Shala;
  onSaid: (said: Said) => void;
  onPick: () => void;
}) {
  const { l10n } = useLocalization();
  const { offer = [], waiting = [] } = useTeacherChoices(shala.id, true).data ?? {};
  return (
    <>
      {waiting.length > 0 && (
        <section className="card">
          <AskedLines
            asked={waiting}
            onWithdrawn={() => {
              onSaid({ text: l10n.getString("request-withdrawn") });
            }}
          />
        </section>
      )}
      {offer.length > 0 && (
        <Localized id="request-open">
          <button
            type="button"
            className="row-button"
            onClick={() => {
              haptics.selection();
              onPick();
            }}
          />
        </Localized>
      )}
    </>
  );
}

function Place({
  shala,
  locale,
  viewer,
}: {
  shala: Shala;
  locale: Locale;
  /** The account's zone: a member in the shala's own zone reads no offset (ADR-0044). */
  viewer: string | null | undefined;
}) {
  const cities = useMoonCities().data;
  const { l10n } = useLocalization();
  const moon = shala.moon_city ? cities?.find((c) => c.slug === shala.moon_city) : undefined;
  // A moon city since removed from the list falls back to the shala's own city (Q111).
  const moonName = moon ? cityName(moon, moon.slug, locale) : shala.city.name;
  const place = shala.online
    ? l10n.getString("shala-online")
    : l10n.getString("shala-place", { city: shala.city.name });
  // "Shala time" only where it differs from the viewer's own, with the offset (ADR-0044), as
  // the bot's card says it. A city gone from the list comes as `Etc/UTC` (the API's stand-in):
  // as in the bot, the line always says "shala time" and names the city as the shala has it.
  const gone = shala.zone === "Etc/UTC";
  const line =
    !gone && ownZone(shala.zone, viewer)
      ? place
      : l10n.getString("shala-time", {
          place,
          zone: gone ? shala.city.name : labelOf(shala.zone, shala.city.name, viewer),
        });
  const days = useDaysOff()(shala.days_off);
  return (
    <section className="card">
      <p>{line}</p>
      <p>{l10n.getString("shala-moon-line", { city: moonName })}</p>
      <p>{l10n.getString("shala-moon-policy", { p: shala.moon_policy })}</p>
      {days && <p>{plain(l10n.getString("shala-day-off-line", { days }))}</p>}
      {manages(shala.me) && (
        <Localized id="shala-moon-shared">
          <p className="hint small" />
        </Localized>
      )}
    </section>
  );
}

/** "Saturday", "Saturday, Sunday"; null when the shala has no day off. */
function useDaysOff() {
  const { l10n } = useLocalization();
  return (days: number[] | null) =>
    days && days.length > 0
      ? days.map((d) => l10n.getString("day-off-weekday", { d })).join(", ")
      : null;
}

/** Q109, Q119: no silent inheritance; one tap for a member who never chose a day off. */
function DayOffOffer({ shala }: { shala: Shala }) {
  const { l10n } = useLocalization();
  const me = useMe().data;
  const setDayOff = useSetDayOff();
  const days = useDaysOff()(shala.days_off);
  if (!me || me.day_off !== null || !days || !shala.days_off) return null;
  const off = shala.days_off;
  return (
    <button
      type="button"
      className="row-button"
      disabled={setDayOff.isPending}
      onClick={() => {
        haptics.impact("light");
        setDayOff.mutate(off);
      }}
    >
      {plain(l10n.getString("shala-day-off-adopt", { days }))}
    </button>
  );
}

const MOON_POLICIES: MoonPolicy[] = ["closed", "pranayama", "open"];
const DAYS_OFF_MAX = 2;

const NAME_MAX = 64;
const SAME = ""; // the moon select's "same as the shala's city"

/** Owners and managers (Q103: editing is in the Mini App only). */
function Edit({ shala, locale }: { shala: Shala; locale: Locale }) {
  const { l10n } = useLocalization();
  const cities = useMoonCities().data;
  const update = useUpdateShala(shala.id);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(shala.name);
  const [city, setCity] = useState(shala.city.slug);
  const [online, setOnline] = useState(shala.online);
  const [moon, setMoon] = useState(shala.moon_city ?? SAME);
  const [policy, setPolicy] = useState<MoonPolicy>(shala.moon_policy);
  const [daysOff, setDaysOff] = useState<number[]>(shala.days_off ?? []);
  const [blank, setBlank] = useState(false);
  const toggleDay = (d: number) => {
    setDaysOff((now) =>
      now.includes(d)
        ? now.filter((x) => x !== d)
        : now.length < DAYS_OFF_MAX
          ? [...now, d].sort((a, b) => a - b)
          : now,
    );
  };
  const submit = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setBlank(true);
      return;
    }
    setBlank(false);
    haptics.impact("light");
    update.mutate(
      {
        name,
        city,
        online,
        moon_city: moon === SAME ? null : moon,
        moon_policy: policy,
        days_off: daysOff,
      },
      {
        onSuccess: () => {
          setOpen(false);
        },
        onError: () => {
          haptics.notify("error");
        },
      },
    );
  };
  if (!open)
    return (
      <Localized id="shala-edit">
        <button
          type="button"
          className="row-button"
          onClick={() => {
            setOpen(true);
          }}
        />
      </Localized>
    );
  return (
    <form className="card" noValidate onSubmit={submit}>
      <Field
        label={l10n.getString("shala-name-label")}
        error={blank && l10n.getString("shala-name-invalid")}
      >
        <TextInput
          value={name}
          maxLength={NAME_MAX}
          onChange={(e) => {
            setName(e.target.value);
          }}
        />
      </Field>
      <Field label={l10n.getString("shala-city-label")}>
        <Select
          value={city}
          onChange={(e) => {
            setCity(e.target.value);
          }}
        >
          {cities?.map((c) => (
            <option key={c.slug} value={c.slug}>
              {cityName(c, c.slug, locale)}
            </option>
          ))}
        </Select>
      </Field>
      <Check
        label={l10n.getString("shala-online-only")}
        checked={online}
        onChange={() => {
          setOnline(!online);
        }}
      />
      <Field label={l10n.getString("shala-moon-city")}>
        <Select
          value={moon}
          onChange={(e) => {
            setMoon(e.target.value);
          }}
        >
          <option value={SAME}>{l10n.getString("shala-moon-same")}</option>
          {cities?.map((c) => (
            <option key={c.slug} value={c.slug}>
              {cityName(c, c.slug, locale)}
            </option>
          ))}
        </Select>
      </Field>
      <Field
        label={l10n.getString("shala-moon-policy-label")}
        hint={l10n.getString("shala-moon-policy-note")}
      >
        <Select
          value={policy}
          onChange={(e) => {
            setPolicy(e.target.value as MoonPolicy);
          }}
        >
          {MOON_POLICIES.map((p) => (
            <option key={p} value={p}>
              {l10n.getString("shala-moon-policy-option", { p })}
            </option>
          ))}
        </Select>
      </Field>
      <Chips
        label={l10n.getString("shala-day-off-label")}
        options={WEEKDAYS.map((d) => ({
          value: d,
          label: weekdayShort(d, locale),
          name: l10n.getString("day-off-weekday", { d }),
        }))}
        value={daysOff}
        onPick={toggleDay}
      />
      <Localized id="shala-roles-save">
        <button type="submit" className="btn" disabled={update.isPending} />
      </Localized>
      {update.isError && (
        <Localized id="shala-save-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </form>
  );
}

function useRoleLabel() {
  const { l10n } = useLocalization();
  return (role: ShalaRole | "owner") => l10n.getString("shala-role", { role });
}

function Staff({ shala }: { shala: Shala }) {
  const { l10n } = useLocalization();
  const label = useRoleLabel();
  const [editing, setEditing] = useState<string | null>(null);
  const rolesOf = (s: Shala["staff"][number]) =>
    [...(s.owner ? (["owner"] as const) : []), ...s.roles].map(label).join(", ");
  return (
    <section className="card">
      <Localized id="shala-staff-title">
        <h2 />
      </Localized>
      <div className="list">
        {shala.staff.map((s) => {
          const name = s.name ?? l10n.getString("link-no-name");
          const roles = rolesOf(s);
          return canEditRoles(shala.me, s) ? (
            <Fragment key={s.id}>
              <Row
                label={name}
                sub={roles || undefined}
                expanded={editing === s.id}
                onClick={() => {
                  haptics.selection();
                  setEditing(editing === s.id ? null : s.id);
                }}
              />
              {editing === s.id && (
                <RoleEditor
                  shala={shala}
                  person={s}
                  onDone={() => {
                    setEditing(null);
                  }}
                />
              )}
            </Fragment>
          ) : (
            <div key={s.id} className="lrow plain">
              <span className="lrow-text">
                <span className="lrow-label">
                  <span className="lrow-title">{name}</span>
                </span>
                {roles && <span className="lrow-sub">{roles}</span>}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function RoleEditor({
  shala,
  person,
  onDone,
}: {
  shala: Shala;
  person: Shala["staff"][number];
  onDone: () => void;
}) {
  const { l10n } = useLocalization();
  const label = useRoleLabel();
  const save = useSetStaffRoles(shala.id);
  const remove = useRemoveShalaMember(shala.id);
  const [roles, setRoles] = useState<ShalaRole[]>(person.roles);
  // My own row as the owner (Q338): what I do here beside owning it; nobody removes an owner.
  const mine = person.owner;
  const allowed = mine ? OWN_ROLES : grantable(shala.me);
  const toggle = (role: ShalaRole) => {
    setRoles((now) => (now.includes(role) ? now.filter((r) => r !== role) : [...now, role]));
  };
  const confirmRemove = async () => {
    const name = short(person.name ?? l10n.getString("link-no-name"));
    const ok = await confirmDestructive(
      l10n.getString("shala-remove-ask", { name }),
      l10n.getString("shala-remove-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("light");
    remove.mutate({ account: person.id, side: "staff" }, { onSuccess: onDone });
  };
  return (
    <div className="panel">
      {mine && (
        <Localized id="shala-my-roles">
          <p className="group-title" />
        </Localized>
      )}
      {ROLES.filter((r) => allowed.includes(r)).map((role) => (
        <Check
          key={role}
          label={label(role)}
          checked={roles.includes(role)}
          onChange={() => {
            toggle(role);
          }}
        />
      ))}
      <Localized id="shala-roles-save">
        <button
          type="button"
          className="btn"
          disabled={save.isPending}
          onClick={() => {
            haptics.impact("light");
            // Only what this editor offers: a role it does not show is not its to send.
            save.mutate(
              { account: person.id, roles: roles.filter((r) => allowed.includes(r)) },
              { onSuccess: onDone },
            );
          }}
        />
      </Localized>
      {!mine && (
        <Localized id="shala-remove">
          <button
            type="button"
            className="link tap"
            onClick={() => {
              void confirmRemove();
            }}
          />
        </Localized>
      )}
      {(save.isError || remove.isError) && (
        <Localized id="shala-save-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </div>
  );
}

function Students({ shala }: { shala: Shala }) {
  const { l10n } = useLocalization();
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const page = useShalaStudents(shala.id, offset, open).data;
  const remove = useRemoveShalaMember(shala.id);
  if (shala.students_total === null) return null;
  const confirmRemove = async (student: { id: string; name: string | null }) => {
    const name = short(student.name ?? l10n.getString("link-no-name"));
    const ok = await confirmDestructive(
      l10n.getString("shala-remove-ask", { name }),
      l10n.getString("shala-remove-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("light");
    remove.mutate({ account: student.id, side: "students" });
  };
  return (
    <section className="card">
      <button
        type="button"
        className="row-button"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
        }}
      >
        {plain(l10n.getString("shala-students", { n: shala.students_total }))}
      </button>
      {open && page?.students.length === 0 && (
        <Localized id="shala-no-students">
          <p className="hint" />
        </Localized>
      )}
      {open &&
        page?.students.map((s) => (
          <div className="link-person" key={s.id}>
            <span>{s.name ?? l10n.getString("link-no-name")}</span>
            {canRemoveStudents(shala.me) && (
              <Localized id="shala-remove">
                <button
                  type="button"
                  className="link"
                  onClick={() => {
                    void confirmRemove(s);
                  }}
                />
              </Localized>
            )}
          </div>
        ))}
      {open && page && (offset > 0 || offset + SHALA_STUDENTS_PAGE < page.total) && (
        <div className="paging">
          {offset > 0 && (
            <Localized id="page-prev">
              <button
                type="button"
                className="link"
                onClick={() => {
                  setOffset(Math.max(0, offset - SHALA_STUDENTS_PAGE));
                }}
              />
            </Localized>
          )}
          {offset + SHALA_STUDENTS_PAGE < page.total && (
            <Localized id="page-next">
              <button
                type="button"
                className="link"
                onClick={() => {
                  setOffset(offset + SHALA_STUDENTS_PAGE);
                }}
              />
            </Localized>
          )}
        </div>
      )}
    </section>
  );
}

function LinkCard({ shala, link, hint }: { shala: Shala; link: ShalaLink; hint: string }) {
  const { l10n } = useLocalization();
  const share = () => {
    const text = l10n.getString("shala-share-text", { shala: shala.name });
    openTelegramLink(
      `https://t.me/share/url?url=${encodeURIComponent(link.url)}&text=${encodeURIComponent(text)}`,
    );
  };
  return (
    <div className="invite">
      <img className="invite-qr" src={link.qr} alt={l10n.getString("shala-qr-alt")} />
      <p className="invite-url">{link.url}</p>
      <p className="hint">{hint}</p>
      <Localized id="invite-share">
        <button type="button" className="row-button" onClick={share} />
      </Localized>
    </div>
  );
}

function JoinLink({ shala, ask }: { shala: Shala; ask: number }) {
  const { l10n } = useLocalization();
  const link = useShalaJoinLink(shala.id);
  const [shown, setShown] = useState<ShalaLink | null>(null);
  const load = (rotate: boolean) => {
    link.mutate(rotate, {
      onSuccess: setShown,
      onError: () => {
        haptics.notify("error");
      },
    });
  };
  // UI-06: asked for the invite (Today's next step, the setup list), the card makes the link
  // as a tap on the row would, and brings it into view once it is there.
  const section = useRef<HTMLElement>(null);
  const wanted = useRef(false);
  useEffect(() => {
    if (!ask) return;
    if (shown) {
      section.current?.scrollIntoView({ block: "start" });
      return;
    }
    wanted.current = true;
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per ask
  }, [ask]);
  useEffect(() => {
    if (!wanted.current || !shown) return;
    wanted.current = false;
    section.current?.scrollIntoView({ block: "start" });
  }, [shown]);
  const rotate = async () => {
    const ok = await confirmDestructive(
      l10n.getString("invite-new-ask"),
      l10n.getString("invite-new-yes"),
      l10n.getString("delete-cancel"),
    );
    if (ok) load(true);
  };
  return (
    <section className="card" ref={section}>
      {!shown ? (
        <Localized id="shala-invite-students">
          <button
            type="button"
            className="row-button"
            disabled={link.isPending}
            onClick={() => {
              load(false);
            }}
          />
        </Localized>
      ) : (
        <>
          <LinkCard shala={shala} link={shown} hint={l10n.getString("shala-join-hint")} />
          {manages(shala.me) && (
            <Localized id="invite-new">
              <button
                type="button"
                className="row-button"
                onClick={() => {
                  void rotate();
                }}
              />
            </Localized>
          )}
        </>
      )}
      {link.isError && (
        <Localized id="shala-save-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </section>
  );
}

function StaffInvite({ shala, ask }: { shala: Shala; ask: number }) {
  const { l10n } = useLocalization();
  const label = useRoleLabel();
  const invite = useShalaStaffInvite(shala.id);
  const [picking, setPicking] = useState(false);
  const [shown, setShown] = useState<{ link: ShalaLink; role: ShalaRole } | null>(null);
  // UI-06 stage 4: the setup list's third step ("Invite teachers") opens the role picker, in
  // view, with Teacher marked and under the finger. Nothing is made until a role is tapped:
  // a staff link works once.
  const section = useRef<HTMLElement>(null);
  const suggested = useRef<HTMLButtonElement>(null);
  const [asked, setAsked] = useState(0);
  const [suggest, setSuggest] = useState(false);
  if (ask !== asked) {
    setAsked(ask);
    setPicking(true);
    setSuggest(true);
    setShown(null);
  }
  useEffect(() => {
    if (!ask) return;
    section.current?.scrollIntoView({ block: "start" });
    suggested.current?.focus({ preventScroll: true });
  }, [ask]);
  const create = (role: ShalaRole) => {
    invite.mutate(role, {
      onSuccess: (link) => {
        setShown({ link, role });
        setPicking(false);
      },
      onError: () => {
        haptics.notify("error");
      },
    });
  };
  const capped = invite.error instanceof ApiError && invite.error.code === "shala_caps";
  return (
    <section className="card" ref={section}>
      <Localized id="shala-invite-staff">
        <button
          type="button"
          className="row-button"
          aria-expanded={picking}
          onClick={() => {
            setPicking(!picking);
            setSuggest(false);
            setShown(null);
          }}
        />
      </Localized>
      {picking && (
        <>
          <Localized id="shala-staff-pick">
            <p className="hint" />
          </Localized>
          {grantable(shala.me).map((role) => (
            <button
              key={role}
              ref={suggest && role === "teacher" ? suggested : undefined}
              type="button"
              className={suggest && role === "teacher" ? "chip primary" : "chip"}
              aria-current={suggest && role === "teacher" ? "true" : undefined}
              disabled={invite.isPending}
              onClick={() => {
                create(role);
              }}
            >
              {label(role)}
            </button>
          ))}
        </>
      )}
      {shown && (
        <LinkCard
          shala={shala}
          link={shown.link}
          hint={l10n.getString("shala-staff-link-hint", { role: label(shown.role) })}
        />
      )}
      {invite.isError && (
        <Localized id={capped ? "shala-caps" : "shala-save-failed"}>
          <p className="hint" role="alert" />
        </Localized>
      )}
    </section>
  );
}

function Leave({
  shala,
  myId,
  onDone,
}: {
  shala: Shala;
  myId: string | undefined;
  onDone: () => void;
}) {
  const { l10n } = useLocalization();
  const remove = useRemoveShalaMember(shala.id);
  if (shala.me.owner || !myId) return null; // Q102: the owner can't leave
  const leave = async () => {
    const ok = await confirmDestructive(
      l10n.getString("shala-leave-ask", { shala: short(shala.name) }),
      l10n.getString("shala-leave-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("light");
    remove.mutate(
      { account: myId, side: shala.me.student ? "students" : "staff" },
      { onSuccess: onDone },
    );
  };
  return (
    <>
      <Localized id="shala-leave">
        <button
          type="button"
          className="link"
          onClick={() => {
            void leave();
          }}
        />
      </Localized>
      {remove.isError && (
        <Localized id="shala-save-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </>
  );
}

function Delete({ shala, onDone }: { shala: Shala; onDone: () => void }) {
  const { l10n } = useLocalization();
  const remove = useDeleteShala(shala.id);
  const ask = async () => {
    const ok = await confirmDestructive(
      l10n.getString("shala-delete-ask", { shala: short(shala.name) }),
      l10n.getString("shala-delete-yes"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("heavy");
    remove.mutate(undefined, { onSuccess: onDone });
  };
  return (
    <>
      <Localized id="shala-delete">
        <button
          type="button"
          className="link danger"
          onClick={() => {
            void ask();
          }}
        />
      </Localized>
      {remove.isError && (
        <Localized id="shala-save-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </>
  );
}
