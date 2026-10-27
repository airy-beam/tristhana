import { Localized, useLocalization } from "@fluent/react";
import { useState } from "react";

import { ApiError, useDeleteAccount, useSendExport } from "../../api/client";
import { confirmDestructive, haptics } from "../../telegram";

/** 📦 My data (ST-09, ADR-0027): the bot sends the export to the chat; deleting is two steps
 * (this card's explanation, then Telegram's native confirm) and can't be undone. */
export function MyData() {
  const { l10n } = useLocalization();
  const send = useSendExport();
  const remove = useDeleteAccount();
  const [explaining, setExplaining] = useState(false);

  const download = () => {
    haptics.impact("light");
    send.mutate(undefined, {
      onSuccess: () => {
        haptics.notify("success");
      },
      onError: () => {
        haptics.notify("error");
      },
    });
  };
  const confirm = async () => {
    const ok = await confirmDestructive(
      l10n.getString("delete-confirm-popup"),
      l10n.getString("delete-confirm"),
      l10n.getString("delete-cancel"),
    );
    if (!ok) return;
    haptics.impact("heavy");
    remove.mutate(undefined, {
      onError: () => {
        haptics.notify("error");
      },
    });
  };

  return (
    <section className="card" aria-labelledby="my-data-title">
      <Localized id="data-title">
        <h2 id="my-data-title" />
      </Localized>
      <Localized id="data-intro">
        <p className="hint" />
      </Localized>
      <Localized id={send.isPending ? "export-sending" : "export-button"}>
        <button type="button" className="row-button" disabled={send.isPending} onClick={download} />
      </Localized>
      <ExportStatus error={send.error} sent={send.isSuccess} />
      {!explaining ? (
        <Localized id="delete-button">
          <button
            type="button"
            className="link danger"
            onClick={() => {
              setExplaining(true);
            }}
          />
        </Localized>
      ) : (
        <div className="delete-explain">
          <Localized id="delete-explain">
            <p />
          </Localized>
          <ul className="hint small">
            <Localized id="delete-explain-chat">
              <li />
            </Localized>
            <Localized id="delete-explain-backups">
              <li />
            </Localized>
            <Localized id="delete-explain-fresh">
              <li />
            </Localized>
          </ul>
          <Localized id="delete-export-first">
            <button
              type="button"
              className="row-button"
              disabled={send.isPending}
              onClick={download}
            />
          </Localized>
          <Localized id="delete-confirm">
            <button
              type="button"
              className="row-button danger"
              disabled={remove.isPending}
              onClick={() => {
                void confirm();
              }}
            />
          </Localized>
          {remove.isError && (
            <Localized id="delete-failed">
              <p className="status" role="alert" />
            </Localized>
          )}
        </div>
      )}
    </section>
  );
}

function ExportStatus({ error, sent }: { error: Error | null; sent: boolean }) {
  if (sent) {
    return (
      <Localized id="export-sent-app">
        <p className="status" role="status" />
      </Localized>
    );
  }
  if (!error) return null;
  const code = error instanceof ApiError ? error.code : null;
  if (code === "export_too_soon") {
    const wait = error instanceof ApiError ? (error.retryAfterS ?? 600) : 600;
    return (
      <Localized id="export-too-soon" vars={{ minutes: Math.max(1, Math.ceil(wait / 60)) }}>
        <p className="status" role="alert" />
      </Localized>
    );
  }
  const key =
    code === "bot_unreachable"
      ? "export-unreachable"
      : code === "export_too_large"
        ? "export-too-large"
        : "export-failed";
  return (
    <Localized id={key}>
      <p className="status" role="alert" />
    </Localized>
  );
}
