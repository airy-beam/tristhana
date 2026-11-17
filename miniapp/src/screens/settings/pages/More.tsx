import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import {
  useCalendarFeed,
  useLinks,
  useMoonCities,
  useMoonDays,
  useMyShalas,
  usePatchMe,
  useSetMoonLocation,
  type Me,
} from "../../../api/client";
import { haptics } from "../../../telegram";
import { Check, Field, Select, TextInput } from "../../../ui/controls";
import { More as Fold } from "../../../ui/More";
import { cityName } from "../../cityName";
import { MoonSource } from "../../moon/MoonScreen";
import CalendarFeedCard from "../../shalas/CalendarFeedCard";
import { loadShowLadies, saveShowLadies } from "../../stats/cells";
import { MyData } from "../MyData";
import { Page, SaveFailed, type PageProps } from "./Page";

// `stats-show-ladies-hint` lives with the Practice tab's copy (added once, by that module).
import "../../stats/practiceCopy";

/** Settings → "More…" (UI-06 stage 3): what is set once and rarely again. The name; "Your
 * log" (the moon calendar's city, the 🌸 button, 🌸 on this phone's calendar, the check-in);
 * "Privacy" (the calendar link, what others see, My data). */
export default function More({ me, onBack }: PageProps) {
  const { l10n } = useLocalization();
  const feed = useCalendarFeed().data;
  const [fold, setFold] = useState<"feed" | "privacy" | null>(null);
  const toggle = (name: "feed" | "privacy") => () => {
    haptics.selection();
    setFold(fold === name ? null : name);
  };
  return (
    <Page title="settings-more-title" onBack={onBack}>
      <Name me={me} />
      <Localized id="settings-log-title">
        <h2 className="starts" />
      </Localized>
      <section className="card">
        <MoonCity me={me} />
        <Log me={me} />
      </section>
      <Localized id="settings-privacy">
        <h2 className="starts" />
      </Localized>
      {/* SC-06: absent when the server offers no calendar links. */}
      {feed?.available && (
        <Fold label={l10n.getString("feed-open")} open={fold === "feed"} onToggle={toggle("feed")}>
          <CalendarFeedCard locale={me.locale} />
        </Fold>
      )}
      <Fold
        label={l10n.getString("settings-privacy-open")}
        open={fold === "privacy"}
        onToggle={toggle("privacy")}
      >
        <Localized id="settings-privacy-ladies">
          <p className="hint" />
        </Localized>
        <Localized id="settings-privacy-sharing">
          <p className="hint" />
        </Localized>
      </Fold>
      <MyData />
    </Page>
  );
}

/** The name: how the app greets, and what teachers and students see. Saved on blur. */
function Name({ me }: { me: Me }) {
  const { l10n } = useLocalization();
  const patch = usePatchMe();
  const custom = me.name_from_telegram ? "" : (me.display_name ?? "");
  const [name, setName] = useState(custom);
  const save = () => {
    if (name.trim() === custom.trim()) return;
    patch.mutate({ display_name: name.trim() || null });
  };
  return (
    <section className="card">
      <Field label={l10n.getString("settings-name")} hint={l10n.getString("settings-name-hint")}>
        <TextInput
          maxLength={64}
          value={name}
          placeholder={me.name_from_telegram ? (me.display_name ?? "") : ""}
          onChange={(e) => {
            setName(e.target.value);
          }}
          onBlur={save}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
        />
      </Field>
      <SaveFailed when={patch.isError} />
    </section>
  );
}

const FOLLOW = "-teacher"; // never a city slug
const FOLLOW_SHALA = "-shala"; // SC-01

/** The moon calendar's city (MD-02, MD-04, SC-01): follow my teacher, my shala, my own city,
 * or any listed one; under it, where the city comes from. */
function MoonCity({ me }: { me: Me }) {
  const { l10n } = useLocalization();
  const moon = useMoonDays().data;
  const cities = useMoonCities().data;
  const setLocation = useSetMoonLocation();
  const main = useLinks().data?.teachers.find((t) => t.primary);
  const firstShala = useMyShalas().data?.[0];
  if (!moon || !cities) return null;
  const { locale, home_city: home } = me;
  const slug = moon.location.slug;
  // MD-02: the select's value for "Follow my teacher" (sent as null), shown only with a
  // main teacher; selected while the city comes from them or following was chosen.
  const following = !!main && (moon.location.source === "teacher" || moon.location.follow_chosen);
  // SC-01: "Follow my shala", shown only with a shala; selected while the city comes from it.
  const shala = moon.location.shala ?? firstShala;
  const onShala = moon.location.source === "shala";
  const city = cityName(
    cities.find((c) => c.slug === slug),
    slug,
    locale,
  );
  return (
    <div className="field">
      <label htmlFor="moon-calendar-city">{l10n.getString("moon-title", { city })}</label>
      <Select
        id="moon-calendar-city"
        value={following ? FOLLOW : onShala ? FOLLOW_SHALA : slug}
        onChange={(e) => {
          haptics.impact("light");
          const value = e.target.value;
          setLocation.mutate(
            value === FOLLOW ? null : value === FOLLOW_SHALA ? { follow: "shala" } : value,
          );
        }}
      >
        {main && (
          <option value={FOLLOW}>
            {l10n.getString("moon-follow-teacher", {
              name: main.name ?? l10n.getString("link-no-name"),
            })}
          </option>
        )}
        {shala && (
          <option value={FOLLOW_SHALA}>
            {l10n.getString("moon-follow-shala", { shala: shala.name })}
          </option>
        )}
        {/* MD-04: stores the slug (a snapshot); a later trip never moves the calendar. */}
        {home && home.slug !== slug && (
          <Localized id="moon-same-as-city" vars={{ city: cityName(home, home.slug, locale) }}>
            <option value={home.slug} />
          </Localized>
        )}
        {cities.map((c) => (
          <option key={c.slug} value={c.slug}>
            {cityName(c, c.slug, locale)}
          </option>
        ))}
      </Select>
      <MoonSource
        location={moon.location}
        city={city}
        fallback={cityName(cities[0], "mysuru", locale)}
      />
      {setLocation.isError && (
        <Localized id="moon-save-failed">
          <p className="status" role="alert" />
        </Localized>
      )}
    </div>
  );
}

/** Three switches about the log: the 🌸 button (WH-01, one account setting for the bot and the
 * app), 🌸 on this phone's calendar (device-only, QB), and "How do you feel?" (PR-06). */
function Log({ me }: { me: Me }) {
  const { l10n } = useLocalization();
  const [showLadies, setShowLadies] = useState(loadShowLadies);
  const [button, setButton] = useState(!me.hide_ladies);
  const [offer, setOffer] = useState(me.offer_check_in);
  const patch = usePatchMe();
  return (
    <>
      <div className="switch">
        <Check
          label={l10n.getString("settings-ladies-button")}
          aria-describedby="ladies-button-hint"
          checked={button}
          onChange={(e) => {
            const shown = e.target.checked;
            haptics.impact("light");
            setButton(shown); // optimistic
            patch.mutate(
              { hide_ladies: !shown },
              {
                onError: () => {
                  setButton(!shown);
                  haptics.notify("error");
                },
              },
            );
          }}
        />
        <Localized id="settings-ladies-button-hint">
          <p id="ladies-button-hint" className="field-hint" />
        </Localized>
      </div>
      <div className="switch">
        <Check
          label={l10n.getString("stats-show-ladies")}
          aria-describedby="show-ladies-hint"
          checked={showLadies}
          onChange={(e) => {
            haptics.impact("light");
            setShowLadies(e.target.checked);
            saveShowLadies(e.target.checked); // on this phone only; the Practice tab follows
          }}
        />
        <Localized id="stats-show-ladies-hint">
          <p id="show-ladies-hint" className="field-hint" />
        </Localized>
      </div>
      <div className="switch">
        <Check
          label={l10n.getString("settings-checkin")}
          aria-describedby="checkin-hint"
          checked={offer}
          onChange={(e) => {
            const offered = e.target.checked;
            haptics.impact("light");
            setOffer(offered); // optimistic
            patch.mutate(
              { offer_check_in: offered },
              {
                onError: () => {
                  setOffer(!offered);
                  haptics.notify("error");
                },
              },
            );
          }}
        />
        <Localized id="settings-checkin-hint">
          <p id="checkin-hint" className="field-hint" />
        </Localized>
      </div>
      <SaveFailed when={patch.isError} />
    </>
  );
}
