import { Localized, useLocalization } from "@fluent/react";
import { useState, type SyntheticEvent } from "react";

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
  type Shala,
  type ShalaLink,
  type ShalaRole,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import {
  backButtonAvailable,
  confirmDestructive,
  haptics,
  openTelegramLink,
  useBackButton,
} from "../../telegram";
import { cityName } from "../MoonCard";
import { labelOf } from "../settings/zones";
import ShalaSchedule from "./ShalaSchedule";
import { WEEKDAYS } from "./scheduleText";

const ROLES: ShalaRole[] = ["teacher", "assistant", "office", "admin"];
type Me = Shala["me"];

// The same rules as `application/policies.py`; the server decides, this only hides buttons.
const isStaff = (me: Me) => !me.student;
const manages = (me: Me) => isStaff(me) && (me.owner || me.roles.includes("admin"));
const grantable = (me: Me): ShalaRole[] =>
  me.owner ? ROLES : manages(me) ? ROLES.filter((r) => r !== "admin") : [];
const canEditRoles = (me: Me, target: Shala["staff"][number]) =>
  !target.owner && grantable(me).length > 0 && (me.owner || !target.roles.includes("admin"));
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
  week?: number; // the schedule's first week shown (0-3), from My schedule
}

/** The shala card (SC-01): the place, its zone, its moon city and its staff for every member;
 * students, links, roles and delete per role. Students never see other students. */
export default function ShalaScreen({ id, onBack, week }: Props) {
  useBackButton(onBack);
  const { l10n } = useLocalization();
  const query = useShala(id);
  const me = useMe().data;
  const shala = query.data;
  const locale: Locale = me?.locale ?? "en";
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
          <h1>{l10n.getString("shala-title", { shala: shala.name })}</h1>
          <Place shala={shala} locale={locale} />
          <DayOffOffer shala={shala} />
          {manages(shala.me) && <Edit shala={shala} locale={locale} />}
          <ShalaSchedule shala={shala} week={week ?? 0} />
          <Staff shala={shala} />
          {isStaff(shala.me) && <Students shala={shala} />}
          {isStaff(shala.me) && <JoinLink shala={shala} />}
          {grantable(shala.me).length > 0 && <StaffInvite shala={shala} />}
          <Leave shala={shala} myId={me?.id} onDone={onBack} />
          {shala.me.owner && <Delete shala={shala} onDone={onBack} />}
        </>
      )}
    </main>
  );
}

function Place({ shala, locale }: { shala: Shala; locale: Locale }) {
  const cities = useMoonCities().data;
  const { l10n } = useLocalization();
  const moon = shala.moon_city ? cities?.find((c) => c.slug === shala.moon_city) : undefined;
  // A moon city since removed from the list falls back to the shala's own city (Q111).
  const moonName = moon ? cityName(moon, moon.slug, locale) : shala.city.name;
  const place = shala.online
    ? l10n.getString("shala-online")
    : l10n.getString("shala-place", { city: shala.city.name });
  const zone = labelOf(shala.zone, shala.city.name);
  const days = useDaysOff()(shala.days_off);
  return (
    <section className="card">
      <p>{l10n.getString("shala-time", { place, zone })}</p>
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
    <form className="card shala-form" onSubmit={submit}>
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
      <label className="label">
        <Localized id="shala-moon-city">
          <span />
        </Localized>
        <select
          value={moon}
          onChange={(e) => {
            setMoon(e.target.value);
          }}
        >
          <Localized id="shala-moon-same">
            <option value={SAME} />
          </Localized>
          {cities?.map((c) => (
            <option key={c.slug} value={c.slug}>
              {cityName(c, c.slug, locale)}
            </option>
          ))}
        </select>
      </label>
      <label className="label">
        <Localized id="shala-moon-policy-label">
          <span />
        </Localized>
        <select
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
        </select>
      </label>
      <Localized id="shala-moon-policy-note">
        <p className="hint small" />
      </Localized>
      <fieldset className="weekdays">
        <Localized id="shala-day-off-label">
          <legend className="label" />
        </Localized>
        {WEEKDAYS.map((d) => (
          <label key={d} className="toggle">
            <input
              type="checkbox"
              checked={daysOff.includes(d)}
              onChange={() => {
                toggleDay(d);
              }}
            />
            {l10n.getString("day-off-weekday", { d })}
          </label>
        ))}
      </fieldset>
      <Localized id="shala-roles-save">
        <button type="submit" className="row-button" disabled={update.isPending} />
      </Localized>
      {(blank || update.isError) && (
        <Localized id={blank ? "shala-name-invalid" : "shala-save-failed"}>
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
  const describe = (s: Shala["staff"][number]) => {
    const roles = [...(s.owner ? (["owner"] as const) : []), ...s.roles].map(label).join(", ");
    const name = s.name ?? l10n.getString("link-no-name");
    return roles ? l10n.getString("shala-person", { name, roles }) : name;
  };
  return (
    <section className="card">
      <Localized id="shala-staff-title">
        <h2 />
      </Localized>
      {shala.staff.map((s) =>
        canEditRoles(shala.me, s) ? (
          <div key={s.id}>
            <button
              type="button"
              className="row-button"
              aria-expanded={editing === s.id}
              onClick={() => {
                haptics.selection();
                setEditing(editing === s.id ? null : s.id);
              }}
            >
              {describe(s)}
            </button>
            {editing === s.id && (
              <RoleEditor
                shala={shala}
                person={s}
                onDone={() => {
                  setEditing(null);
                }}
              />
            )}
          </div>
        ) : (
          <p key={s.id} className="link-person">
            {describe(s)}
          </p>
        ),
      )}
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
  const allowed = grantable(shala.me);
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
    <div className="role-editor">
      {ROLES.filter((r) => allowed.includes(r)).map((role) => (
        <label key={role} className="toggle">
          <input
            type="checkbox"
            checked={roles.includes(role)}
            onChange={() => {
              toggle(role);
            }}
          />
          {label(role)}
        </label>
      ))}
      <Localized id="shala-roles-save">
        <button
          type="button"
          className="row-button"
          disabled={save.isPending}
          onClick={() => {
            haptics.impact("light");
            save.mutate({ account: person.id, roles }, { onSuccess: onDone });
          }}
        />
      </Localized>
      <Localized id="shala-remove">
        <button
          type="button"
          className="link"
          onClick={() => {
            void confirmRemove();
          }}
        />
      </Localized>
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

function JoinLink({ shala }: { shala: Shala }) {
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
  const rotate = async () => {
    const ok = await confirmDestructive(
      l10n.getString("invite-new-ask"),
      l10n.getString("invite-new-yes"),
      l10n.getString("delete-cancel"),
    );
    if (ok) load(true);
  };
  return (
    <section className="card">
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

function StaffInvite({ shala }: { shala: Shala }) {
  const { l10n } = useLocalization();
  const label = useRoleLabel();
  const invite = useShalaStaffInvite(shala.id);
  const [picking, setPicking] = useState(false);
  const [shown, setShown] = useState<{ link: ShalaLink; role: ShalaRole } | null>(null);
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
    <section className="card">
      <Localized id="shala-invite-staff">
        <button
          type="button"
          className="row-button"
          aria-expanded={picking}
          onClick={() => {
            setPicking(!picking);
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
              type="button"
              className="chip"
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
