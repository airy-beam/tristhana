import { Localized, useLocalization } from "@fluent/react";
import { useState, type SyntheticEvent } from "react";

import {
  ANNOUNCEMENTS_PAGE,
  ApiError,
  useAnnouncements,
  useDeleteAnnouncement,
  useLinks,
  useMuteAnnouncements,
  usePinAnnouncement,
  useSendAnnouncement,
  useSentAnnouncements,
  useShala,
  type Announcement,
  type AnnouncementSource,
  type SentAnnouncement,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import {
  backButtonAvailable,
  confirmAction,
  confirmDestructive,
  haptics,
  useBackButton,
} from "../../telegram";

export const TEXT_MAX = 1000;
type PinDays = 0 | 7 | 30;

export type AnnouncementsMode =
  | { view: "compose"; shala: string | null } // null: all my students
  | { view: "feed"; shala: string | null }; // null: every teacher and shala of mine

interface Props {
  mode: AnnouncementsMode;
  locale: Locale;
  onBack: () => void;
}

/** NT-03 (ADR-0038): compose and my sent list (a teacher, or shala staff with the right), or
 * the feed of my teachers and shalas with a mute per source. Plain text, relayed as written;
 * the bot delivers it within about 10 minutes. Loaded lazily (its own chunk). */
export default function Announcements({ mode, locale, onBack }: Props) {
  useBackButton(onBack);
  return (
    <main className="screen announcements">
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={onBack} />
        </Localized>
      )}
      {mode.view === "compose" ? (
        <Compose shala={mode.shala} locale={locale} />
      ) : (
        <Feed shala={mode.shala} locale={locale} />
      )}
    </main>
  );
}

/** Only the date, in the device's zone: no time of day is shown, so no zone label (spec §7). */
function dateText(iso: string, locale: Locale): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(new Date(iso));
}

function plain(text: string): string {
  return text.replace(/[⁨⁩]/g, ""); // Fluent's isolation marks, for native popups
}

// --- compose --------------------------------------------------------------------------------

function useAudience(shala: string | null): { name: string | null; count: number | null } {
  const links = useLinks();
  const card = useShala(shala ?? "", shala !== null); // a teacher's compose asks for no shala
  if (shala === null) return { name: null, count: links.data ? links.data.students.length : null };
  const s = card.data;
  if (!s) return { name: null, count: null };
  return { name: s.name, count: s.staff.length + (s.students_total ?? 0) - 1 };
}

function Compose({ shala, locale }: { shala: string | null; locale: Locale }) {
  const { l10n } = useLocalization();
  const audience = useAudience(shala);
  const send = useSendAnnouncement();
  const [text, setText] = useState("");
  const [pin, setPin] = useState<PinDays>(0);
  const [sent, setSent] = useState(false);
  const length = Array.from(text.trim()).length; // code points, as the server counts
  const tooLong = length > TEXT_MAX;
  const counter = [length, TEXT_MAX].join(" / ");
  const limited = send.error instanceof ApiError && send.error.code === "announcement_limit";
  const count = audience.count ?? 0;

  const submit = async (e: SyntheticEvent) => {
    e.preventDefault();
    if (length === 0 || tooLong || count === 0) return;
    const ok = await confirmAction(
      plain(l10n.getString("ann-send-ask", { count })),
      plain(l10n.getString("ann-send")),
      plain(l10n.getString("delete-cancel")),
    );
    if (!ok) return;
    setSent(false);
    haptics.impact("light");
    send.mutate(
      shala === null
        ? { to: "students", text, pin_days: pin }
        : { to: "shala", shala_id: shala, text, pin_days: pin },
      {
        onSuccess: () => {
          haptics.notify("success");
          setText("");
          setPin(0);
          setSent(true);
        },
        onError: () => {
          haptics.notify("error"); // the text stays, to send later
        },
      },
    );
  };

  return (
    <>
      <Localized id="ann-compose-title">
        <h1 />
      </Localized>
      {audience.count !== null && (
        <p>
          {shala === null
            ? l10n.getString("ann-to-students", { count })
            : l10n.getString("ann-to-shala", { shala: audience.name ?? "", count })}
        </p>
      )}
      <form className="announce-form" onSubmit={(e) => void submit(e)}>
        <label className="label">
          <Localized id="ann-text-label">
            <span />
          </Localized>
          <textarea
            value={text}
            rows={6}
            onChange={(e) => {
              setText(e.target.value);
              setSent(false);
            }}
            aria-invalid={tooLong}
            aria-describedby="ann-count"
          />
        </label>
        <p id="ann-count" className={tooLong ? "hint small error" : "hint small"}>
          {counter}
        </p>
        <label className="label">
          <Localized id="ann-pin-label">
            <span />
          </Localized>
          <select
            value={pin}
            onChange={(e) => {
              setPin(Number(e.target.value) as PinDays);
            }}
          >
            <option value={0}>{l10n.getString("ann-pin-none")}</option>
            <option value={7}>{l10n.getString("ann-pin-week")}</option>
            <option value={30}>{l10n.getString("ann-pin-month")}</option>
          </select>
        </label>
        <Localized id="ann-hint">
          <p className="hint small" />
        </Localized>
        {shala !== null && (
          <Localized id="ann-hint-shala">
            <p className="hint small" />
          </Localized>
        )}
        {limited && (
          <Localized id="ann-limit">
            <p className="hint" role="alert" />
          </Localized>
        )}
        {send.isError && !limited && (
          <Localized id="feed-failed">
            <p className="hint" role="alert" />
          </Localized>
        )}
        {sent && (
          <Localized id="ann-sent">
            <p className="hint" role="status" />
          </Localized>
        )}
        <Localized id="ann-send">
          <button
            type="submit"
            className="primary"
            disabled={send.isPending || length === 0 || tooLong || count === 0}
          />
        </Localized>
      </form>
      <SentList shala={shala} locale={locale} />
    </>
  );
}

function SentList({ shala, locale }: { shala: string | null; locale: Locale }) {
  const { l10n } = useLocalization();
  const query = useSentAnnouncements();
  const pin = usePinAnnouncement();
  const remove = useDeleteAnnouncement();
  const mine = (query.data ?? []).filter((s) =>
    shala === null ? s.source.kind === "teacher" : s.source.id === shala,
  );
  if (mine.length === 0) return null;

  const del = async (item: SentAnnouncement) => {
    const ok = await confirmDestructive(
      plain(l10n.getString("ann-delete-ask")),
      plain(l10n.getString("ann-delete")),
      plain(l10n.getString("delete-cancel")),
    );
    if (ok) remove.mutate(item.id);
  };

  return (
    <section className="card" aria-busy={pin.isPending || remove.isPending}>
      <Localized id="ann-sent-title">
        <h2 />
      </Localized>
      {(pin.isError || remove.isError) && (
        <Localized id="feed-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      <ul className="announcements-list">
        {mine.map((item) => (
          <li key={item.id}>
            <p className="hint small">
              {[
                dateText(item.created_at, locale),
                l10n.getString("ann-sent-to", { count: item.audience }),
                ...(item.pinned_until
                  ? [
                      l10n.getString("ann-pinned-until", {
                        date: dateText(item.pinned_until, locale),
                      }),
                    ]
                  : []),
              ].join(" · ")}
            </p>
            <p className="announcement-text clamp">{item.text}</p>
            <div className="row">
              {item.pinned_until ? (
                <Localized id="ann-unpin">
                  <button
                    type="button"
                    className="link"
                    onClick={() => {
                      pin.mutate({ id: item.id, days: 0 });
                    }}
                  />
                </Localized>
              ) : (
                <Localized id="ann-pin-week">
                  <button
                    type="button"
                    className="link"
                    onClick={() => {
                      pin.mutate({ id: item.id, days: 7 });
                    }}
                  />
                </Localized>
              )}
              <Localized id="ann-delete">
                <button type="button" className="link danger" onClick={() => void del(item)} />
              </Localized>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

// --- the feed -------------------------------------------------------------------------------

function sameSource(a: Announcement["source"], b: AnnouncementSource): boolean {
  return a.kind === b.kind && a.id === b.id;
}

type SourceRef = { kind: "teacher" | "shala"; id: string };

/** The feed: chips narrow it on the server (so a quiet source's older items still come), and
 * "More" pages through the 30-day window. */
function Feed({ shala, locale }: { shala: string | null; locale: Locale }) {
  const { l10n } = useLocalization();
  const base: SourceRef | null = shala ? { kind: "shala", id: shala } : null;
  const all = useAnnouncements(base); // the sources (and the first page when no chip is on)
  const [only, setOnly] = useState<SourceRef | null>(null);
  const [pages, setPages] = useState(1);
  const sources = all.data?.sources ?? [];
  const source = only ?? base;
  const shown = sources.filter((s) => only === null || (s.kind === only.kind && s.id === only.id));
  const pick = (next: SourceRef | null) => {
    setOnly(next);
    setPages(1);
  };
  return (
    <>
      <Localized id="ann-list">
        <h1 />
      </Localized>
      {all.isError && (
        <Localized id="feed-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {shala === null && sources.length > 1 && (
        <div className="chips" role="group" aria-label={l10n.getString("ann-list")}>
          <button
            type="button"
            className="chip"
            aria-pressed={only === null}
            onClick={() => {
              pick(null);
            }}
          >
            {l10n.getString("ann-all")}
          </button>
          {sources.map((s) => (
            <button
              key={`${s.kind}:${s.id}`}
              type="button"
              className="chip"
              aria-pressed={only?.id === s.id}
              onClick={() => {
                pick({ kind: s.kind, id: s.id });
              }}
            >
              {s.name ?? l10n.getString("link-no-name")}
            </button>
          ))}
        </div>
      )}
      {Array.from({ length: pages }, (_, n) => (
        <FeedPage
          key={`${source?.id ?? "all"}:${String(n)}`}
          source={source}
          offset={n * ANNOUNCEMENTS_PAGE}
          sources={sources}
          locale={locale}
          last={n === pages - 1}
          onMore={() => {
            setPages(pages + 1);
          }}
        />
      ))}
      {shown.map((s) => (
        <MuteSwitch key={`${s.kind}:${s.id}`} source={s} />
      ))}
    </>
  );
}

function FeedPage({
  source,
  offset,
  sources,
  locale,
  last,
  onMore,
}: {
  source: SourceRef | null;
  offset: number;
  sources: AnnouncementSource[];
  locale: Locale;
  last: boolean;
  onMore: () => void;
}) {
  const { l10n } = useLocalization();
  const { data } = useAnnouncements(source, offset);
  if (!data) return null;
  return (
    <>
      {offset === 0 && data.items.length === 0 && (
        <Localized id="ann-list-empty">
          <p className="hint" />
        </Localized>
      )}
      <ul className="announcements-list">
        {data.items.map((item) => {
          const from = sources.find((s) => sameSource(item.source, s));
          const by = item.author_name ?? from?.name ?? l10n.getString("link-no-name");
          return (
            <li key={item.id} className={item.pinned_until ? "pinned" : undefined}>
              {item.pinned_until && (
                <p className="hint small">
                  {l10n.getString("ann-pinned-until", {
                    date: dateText(item.pinned_until, locale),
                  })}
                </p>
              )}
              <p className="hint small">
                {[
                  dateText(item.created_at, locale),
                  by,
                  ...(item.source.kind === "shala" && from?.name && item.author_name
                    ? [from.name]
                    : []),
                ].join(" · ")}
              </p>
              <p className="announcement-text">{item.text}</p>
              {item.can_manage && <Moderate item={item} />}
            </li>
          );
        })}
      </ul>
      {last && data.more && (
        <Localized id="students-more">
          <button type="button" className="row-button" onClick={onMore} />
        </Localized>
      )}
    </>
  );
}

/** Spec §4: a shala's owner or manager moderates from the feed (the author too). */
function Moderate({ item }: { item: Announcement }) {
  const { l10n } = useLocalization();
  const pin = usePinAnnouncement();
  const remove = useDeleteAnnouncement();
  const del = async () => {
    const ok = await confirmDestructive(
      plain(l10n.getString("ann-delete-ask")),
      plain(l10n.getString("ann-delete")),
      plain(l10n.getString("delete-cancel")),
    );
    if (ok) remove.mutate(item.id);
  };
  return (
    <div className="row" aria-busy={pin.isPending || remove.isPending}>
      {item.pinned_until && (
        <Localized id="ann-unpin">
          <button
            type="button"
            className="link"
            onClick={() => {
              pin.mutate({ id: item.id, days: 0 });
            }}
          />
        </Localized>
      )}
      <Localized id="ann-delete">
        <button type="button" className="link danger" onClick={() => void del()} />
      </Localized>
      {(pin.isError || remove.isError) && (
        <Localized id="feed-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </div>
  );
}

function MuteSwitch({ source }: { source: AnnouncementSource }) {
  const { l10n } = useLocalization();
  const mute = useMuteAnnouncements();
  const on = !source.muted;
  return (
    <label className="switch-row">
      <input
        type="checkbox"
        role="switch"
        checked={on}
        disabled={mute.isPending}
        onChange={() => {
          mute.mutate({ kind: source.kind, id: source.id, muted: on });
        }}
      />
      <span>
        {l10n.getString("ann-send-to-me", {
          source: source.name ?? l10n.getString("link-no-name"),
        })}
      </span>
    </label>
  );
}
