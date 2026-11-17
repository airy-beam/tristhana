import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import {
  useLinks,
  useMyShalas,
  useNotificationSettings,
  usePatchNotificationSettings,
  type NotificationSettings,
} from "../../../api/client";
import { haptics } from "../../../telegram";
import { Chips } from "../../../ui/Chips";
import { Check, Field, Select } from "../../../ui/controls";
import { More } from "../../../ui/More";
import { inQuiet, PracticeReminderCard } from "../../PracticeReminderCard";
import { labelOf, placeFor } from "../zones";
import { Page, SaveFailed, type PageProps } from "./Page";

const OFFSETS = [7, 3, 1] as const;
const MOON_TIMES = ["07:00", "12:00", "19:00", "21:00"] as const;
const CAPS = [1, 2, 3, 5] as const;
const HOURS = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, "0")}:00`);

/** Settings → "🔔 Reminders" (NT-01/02, PR-10): the practice reminder, the moon reminders,
 * quiet hours with the daily limit (folded), and the announcements switch. The place of every
 * time on the page is named once, at the top (ADR-0044); while no zone is known that line
 * says so, and the times wait. It reads the notification settings, and my teachers and
 * shalas for the announcements switch. */
export default function Reminders({ me, onBack }: PageProps) {
  const settings = useNotificationSettings().data;
  const zone = me.timezone;
  return (
    <Page title="settings-reminders-title" onBack={onBack} busy={!settings}>
      {zone ? (
        <Localized
          id="settings-times-place"
          // My own zone: the place, no offset.
          vars={{ zone: labelOf(zone, placeFor(me.home_city, zone, me.locale), zone) }}
        >
          <p className="hint" />
        </Localized>
      ) : (
        <Localized id="moon-zone-needed-app">
          <p className="hint" />
        </Localized>
      )}
      <PracticeReminderCard zone={zone} />
      {settings && zone && <MoonReminders settings={settings} />}
      {settings && zone && <Quiet settings={settings} />}
      {settings && <Announcements settings={settings} />}
    </Page>
  );
}

/** Times of the reminders that are on: quiet hours may not swallow them. */
function activeTimes(settings: NotificationSettings): string[] {
  const out: string[] = [];
  if (settings.moon.offsets.length) out.push(settings.moon.at);
  if (settings.practice.on) out.push(settings.practice.at);
  return out;
}

/** A tap saves: only what was tapped is sent, so a change made in the bot meanwhile stays
 * (ADR-0021). */
function useSave() {
  const save = usePatchNotificationSettings();
  const tap = (body: Parameters<typeof save.mutate>[0]) => {
    haptics.impact("light");
    save.mutate(body, {
      onError: () => {
        haptics.notify("error");
      },
    });
  };
  return [tap, save.isError] as const;
}

/** Moon day reminders (NT-01): how many days before, and at what time. */
function MoonReminders({ settings }: { settings: NotificationSettings }) {
  const { l10n } = useLocalization();
  const [tap, failed] = useSave();
  const offsets = settings.moon.offsets;
  return (
    <section className="card" aria-labelledby="moon-remind-title">
      <Localized id="status-moon">
        <h2 id="moon-remind-title" />
      </Localized>
      <Chips
        label={l10n.getString("moon-reminders-label")}
        options={OFFSETS.map((n) => ({ value: n, label: l10n.getString("moon-offset", { n }) }))}
        value={offsets}
        onPick={(k) => {
          tap({
            moon: {
              offsets: offsets.includes(k) ? offsets.filter((o) => o !== k) : [...offsets, k],
            },
          });
        }}
      />
      <Chips
        label={l10n.getString("settings-moon-time")}
        options={MOON_TIMES.map((t) => ({
          value: t,
          label: t,
          disabled: inQuiet(settings.quiet, t),
        }))}
        value={settings.moon.at.slice(0, 5)}
        onPick={(t) => {
          tap({ moon: { at: `${t}:00` } });
        }}
      />
      <SaveFailed when={failed} />
    </section>
  );
}

/** Quiet hours and the daily limit (NT-02), folded: the closed row says what is set, in the
 * bot's words. */
function Quiet({ settings }: { settings: NotificationSettings }) {
  const { l10n } = useLocalization();
  const [open, setOpen] = useState(false);
  const [tap, failed] = useSave();
  const start = settings.quiet.start.slice(0, 5);
  const end = settings.quiet.end.slice(0, 5);
  const none = start === end;
  const times = activeTimes(settings);
  const conflict = (s: string, e: string) =>
    times.some((t) => inQuiet({ start: `${s}:00`, end: `${e}:00` }, t));
  const setQuiet = (s: string, e: string) => {
    tap({ quiet: { start: `${s}:00`, end: `${e}:00` } });
  };
  const from = none ? "22:00" : start;
  const until = none ? "07:00" : end;
  return (
    <More
      label={l10n.getString("settings-quiet")}
      summary={
        none
          ? l10n.getString("settings-quiet-off-line", { n: settings.daily_cap })
          : l10n.getString("settings-quiet-line", { start, end, n: settings.daily_cap })
      }
      open={open}
      onToggle={() => {
        haptics.selection();
        setOpen(!open);
      }}
    >
      <Field label={l10n.getString("settings-quiet-from")}>
        <Select
          value={none ? "" : start}
          onChange={(e) => {
            setQuiet(e.target.value, until);
          }}
        >
          <option value="" disabled />
          {HOURS.map((h) => (
            <option key={h} value={h} disabled={conflict(h, until)}>
              {h}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={l10n.getString("settings-quiet-to")}>
        <Select
          value={none ? "" : end}
          onChange={(e) => {
            setQuiet(from, e.target.value);
          }}
        >
          <option value="" disabled />
          {HOURS.map((h) => (
            <option key={h} value={h} disabled={conflict(from, h)}>
              {h}
            </option>
          ))}
        </Select>
      </Field>
      <div className="switch">
        <Check
          label={l10n.getString("settings-quiet-off")}
          checked={none}
          onChange={(e) => {
            if (e.target.checked) setQuiet("00:00", "00:00");
            else tap({ quiet: null }); // back to the default 22:00–07:00
          }}
        />
        {conflict(start, end) && (
          <Localized id="settings-quiet-conflict">
            <p className="field-hint" />
          </Localized>
        )}
      </div>
      <Chips
        label={l10n.getString("settings-cap", { n: settings.daily_cap })}
        options={CAPS.map((n) => ({ value: n, label: String(n) }))}
        value={settings.daily_cap}
        onPick={(n) => {
          tap({ daily_cap: n });
        }}
      />
      <SaveFailed when={failed} />
    </More>
  );
}

/** NT-03 (Q167): one switch for every teacher's and shala's announcements in the bot; each
 * source also has its own mute. Shown once there is a teacher or a shala to hear from. */
function Announcements({ settings }: { settings: NotificationSettings }) {
  const { l10n } = useLocalization();
  const links = useLinks().data;
  const shalas = useMyShalas().data;
  const save = usePatchNotificationSettings();
  const [on, setOn] = useState<boolean | null>(null);
  if (!links?.teachers.length && !shalas?.length) return null;
  return (
    <section className="card">
      <Check
        label={l10n.getString("settings-announcements")}
        checked={on ?? settings.announcements}
        onChange={(e) => {
          const value = e.target.checked;
          haptics.impact("light");
          setOn(value); // optimistic
          save.mutate(
            { announcements: value ? null : false }, // null: back to the default (on)
            {
              onError: () => {
                setOn(!value);
                haptics.notify("error");
              },
            },
          );
        }}
      />
      <SaveFailed when={save.isError} />
    </section>
  );
}
