// ST-07 (ADR-0040): the share sheet, a lazy chunk. The server draws the card (two tones, no
// name, no rest or 🌸 days); this sheet previews it and offers what the client supports:
// Share to story (mobile), Save image (Bot API 8.0+), Send to my chat (always).
import { Localized, useLocalization } from "@fluent/react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import {
  ApiError,
  type ShareFormat,
  type ShareSubject,
  useSendShareCard,
  useShareCard,
} from "../../api/client";
import { haptics, useBackButton } from "../../telegram";
import { canDownload, canShareStory, saveImage, shareToStory } from "../../telegram/share";

export default function ShareSheet({
  subject,
  onClose,
}: {
  subject: ShareSubject;
  onClose: () => void;
}) {
  const { l10n } = useLocalization();
  const story = canShareStory();
  const [format, setFormat] = useState<ShareFormat>(story ? "story" : "square");
  const card = useShareCard(subject, format);
  const send = useSendShareCard();
  const [saved, setSaved] = useState(false);
  const title = useRef<HTMLHeadingElement>(null);
  useBackButton(onClose);
  useEffect(() => {
    // A modal: focus moves in, Escape closes, focus goes back to the Share button after.
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    title.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus();
    };
  }, [onClose]);
  // Sending twice (reopened within the cache window) is still "sent", not a failure.
  const sent =
    send.isSuccess || (send.error instanceof ApiError && send.error.code === "already_sent");

  const failed =
    card.error instanceof ApiError && card.error.code === "rate_limited"
      ? "share-rate-limited"
      : card.error
        ? "share-failed"
        : null;
  const data = card.data;

  return createPortal(
    <div className="share-backdrop" onClick={onClose}>
      <section
        className="share-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="share-title"
        onClick={(e) => {
          e.stopPropagation();
        }}
      >
        <div className="share-head">
          <Localized id="share-title">
            <h2 id="share-title" ref={title} tabIndex={-1} />
          </Localized>
          <Localized id="share-close" attrs={{ "aria-label": true }}>
            <button type="button" className="link" onClick={onClose} />
          </Localized>
        </div>
        <div className="chips" role="group" aria-labelledby="share-title">
          {(["story", "square"] as const).map((f) => (
            <Localized key={f} id={f === "story" ? "share-format-story" : "share-format-square"}>
              <button
                type="button"
                className="chip"
                aria-pressed={format === f}
                onClick={() => {
                  haptics.selection();
                  setFormat(f);
                  setSaved(false);
                  send.reset(); // the other format is another card, not sent yet
                }}
              />
            </Localized>
          ))}
        </div>
        <div className={`share-preview ${format}`} aria-busy={card.isPending}>
          {data ? (
            <img
              src={data.image_url}
              width={data.width}
              height={data.height}
              alt={l10n.getString("share-preview-alt")}
            />
          ) : failed ? (
            <Localized id={failed}>
              <p className="hint" role="alert" />
            </Localized>
          ) : (
            <Localized id="share-loading">
              <p className="hint" />
            </Localized>
          )}
        </div>
        <Localized id="share-privacy-note">
          <p className="hint small" />
        </Localized>
        {data && (
          <div className="share-actions">
            {story && format === "story" && (
              <Localized id="share-to-story">
                <button
                  type="button"
                  className="row-button primary"
                  onClick={() => {
                    haptics.impact("light");
                    shareToStory(data.image_url, l10n.getString("share-story-caption"));
                  }}
                />
              </Localized>
            )}
            {canDownload() && (
              <Localized id={saved ? "share-saved" : "share-save"}>
                <button
                  type="button"
                  className="row-button"
                  onClick={() => {
                    haptics.impact("light");
                    void saveImage(data.image_url, data.file_name).then(setSaved);
                  }}
                />
              </Localized>
            )}
            <Localized id={sent ? "share-sent" : "share-send-chat"}>
              <button
                type="button"
                className="row-button"
                disabled={send.isPending || sent}
                onClick={() => {
                  haptics.impact("light");
                  send.mutate(data.id, {
                    onSuccess: () => {
                      haptics.notify("success");
                    },
                    onError: () => {
                      haptics.notify("error");
                    },
                  });
                }}
              />
            </Localized>
            {send.error && !sent && (
              <Localized
                id={
                  send.error instanceof ApiError && send.error.code === "bot_unreachable"
                    ? "share-send-unreachable"
                    : "share-failed"
                }
              >
                <p className="hint" role="alert" />
              </Localized>
            )}
          </div>
        )}
      </section>
    </div>,
    document.body,
  );
}
