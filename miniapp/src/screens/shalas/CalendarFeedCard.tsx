import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import {
  useCalendarFeed,
  useCreateCalendarFeed,
  useDeleteCalendarFeed,
  useMyShalas,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { confirmDestructive, haptics, openLink } from "../../telegram";
import { dayName, plain } from "./scheduleText";

/** "📅 Calendar subscription" (SC-06, ADR-0036): my classes and moon days in Google, Apple or
 * Outlook Calendar. The link is a secret: shown here, copied on a tap, never stored by the
 * app. Telegram opens https only, so Apple/Outlook go through our webcal:// redirect. Hidden
 * when the server offers no links. */
export default function CalendarFeedCard({ locale }: { locale: Locale }) {
  const { l10n } = useLocalization();
  const query = useCalendarFeed();
  const shalas = useMyShalas();
  const create = useCreateCalendarFeed();
  const remove = useDeleteCalendarFeed();
  const [copied, setCopied] = useState(false);
  const feed = query.data;
  if (!feed?.available) return null;
  const busy = create.isPending || remove.isPending;

  const copy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      haptics.notify("success");
      setCopied(true);
    } catch {
      // no clipboard (an old client): the link stays on screen to select
    }
  };
  const rotate = async () => {
    const ok = await confirmDestructive(
      plain(l10n.getString("feed-rotate-confirm")),
      plain(l10n.getString("feed-rotate")),
      plain(l10n.getString("delete-cancel")),
    );
    if (!ok) return;
    setCopied(false);
    create.mutate({ rotate: true });
  };
  const turnOff = async () => {
    const ok = await confirmDestructive(
      plain(l10n.getString("feed-off-confirm")),
      plain(l10n.getString("feed-off")),
      plain(l10n.getString("delete-cancel")),
    );
    if (!ok) return;
    setCopied(false);
    remove.mutate();
  };

  return (
    <section className="card calendar-feed" aria-busy={busy}>
      <Localized id="feed-title">
        <h2 />
      </Localized>
      <Localized id="feed-explain">
        <p className="hint small" />
      </Localized>
      {(create.isError || remove.isError) && (
        <Localized id="feed-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {!feed.on || !feed.url ? (
        <>
          {shalas.data?.length === 0 && (
            <Localized id="feed-moon-only">
              <p className="hint small" />
            </Localized>
          )}
          <Localized id="feed-create">
            <button
              type="button"
              className="row-button"
              disabled={busy}
              onClick={() => {
                create.mutate({ rotate: false });
              }}
            />
          </Localized>
        </>
      ) : (
        <>
          <p className="feed-url hint small">{feed.url}</p>
          <button
            type="button"
            className="row-button"
            onClick={() => {
              if (feed.url) void copy(feed.url);
            }}
          >
            {plain(l10n.getString(copied ? "feed-copied" : "feed-copy"))}
          </button>
          {feed.google_url && (
            <Localized id="feed-google">
              <button
                type="button"
                className="row-button"
                onClick={() => {
                  if (feed.google_url) openLink(feed.google_url);
                }}
              />
            </Localized>
          )}
          {feed.subscribe_url && (
            <Localized id="feed-apple">
              <button
                type="button"
                className="row-button"
                onClick={() => {
                  if (feed.subscribe_url) openLink(feed.subscribe_url);
                }}
              />
            </Localized>
          )}
          <Localized id="feed-private">
            <p className="hint small" />
          </Localized>
          <p className="hint small">
            {plain(
              l10n.getString("feed-checked", {
                day: feed.fetched_on ? dayName(feed.fetched_on, locale) : "none",
              }),
            )}
          </p>
          <div className="row">
            <Localized id="feed-rotate">
              <button
                type="button"
                className="link"
                disabled={busy}
                onClick={() => void rotate()}
              />
            </Localized>
            <Localized id="feed-off">
              <button
                type="button"
                className="link"
                disabled={busy}
                onClick={() => void turnOff()}
              />
            </Localized>
          </div>
        </>
      )}
    </section>
  );
}
