import { Localized, useLocalization } from "@fluent/react";
import { useCallback, useEffect, useRef, useState, type SyntheticEvent } from "react";

import { ApiError } from "../../api/client";
import { addMessages } from "../../i18n/lazyMessages";
import type { Locale } from "../../i18n/negotiate";
import enListing from "../../locales/en/listing.ftl?raw";
import ruListing from "../../locales/ru/listing.ftl?raw";
import {
  backButtonAvailable,
  confirmAction,
  confirmDestructive,
  haptics,
  mainButtonAvailable,
  useBackButton,
  useMainButton,
} from "../../telegram";
import {
  checkedMonth,
  LEVELS,
  useListing,
  useRemoveListing,
  useSaveListing,
  type Listing,
  type ListingLevel,
} from "./listing";

addMessages({ en: enListing, ru: ruListing });

export const NAME_MAX = 100;
export const REGION_MAX = 60;
export const NOTE_MAX = 300;

interface Props {
  locale: Locale;
  onBack: () => void;
}

function plain(text: string): string {
  return text.replace(/[⁨⁩]/g, ""); // Fluent's isolation marks, for native popups
}

/** A request someone is looking at, or a line that shows: these have a status view, and the
 * form opens from "Edit". Everything else is the form itself. */
function settled(listing: Listing): boolean {
  return listing.status === "pending" || listing.status === "listed";
}

/** ID-05: a teacher asks for the "listed in the SYC directory" line, sees where the request
 * stands, edits or removes it. A person checks by hand; nothing here is automatic. Its own
 * chunk, with its copy (`listing.ftl`). */
export default function DirectoryListing({ locale, onBack }: Props) {
  const query = useListing();
  const listing = query.data;
  const [editing, setEditing] = useState(false);
  // Requests aren't taken (`available` false): no form, but my row can be read and removed.
  const open = listing?.available ?? false;
  const inForm = listing ? open && (editing || !settled(listing)) : false;
  const closeForm = useCallback(() => {
    setEditing(false);
  }, []);
  // Back from "Edit" returns to the status, not out of the screen.
  const back = listing && editing && settled(listing) ? closeForm : onBack;
  useBackButton(back);
  return (
    <main className="screen listing" aria-busy={query.isPending}>
      {!backButtonAvailable() && (
        <Localized id="stats-back">
          <button type="button" className="link" onClick={back} />
        </Localized>
      )}
      <Localized id="listing-open">
        <h1 />
      </Localized>
      {query.isError && (
        <Localized id="feed-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {listing && !inForm && settled(listing) && (
        <Status
          listing={listing}
          locale={locale}
          onEdit={
            open
              ? () => {
                  setEditing(true);
                }
              : null
          }
        />
      )}
      {listing && !open && listing.status === "not_found" && (
        <section className="card">
          <Localized id="listing-not-found" vars={{ listed: listing.name_as_listed ?? "" }}>
            <p />
          </Localized>
          <Remove />
        </section>
      )}
      {listing && inForm && (
        <>
          {(listing.status === "none" || listing.status === "withdrawn") && (
            <Localized id="listing-intro">
              <p />
            </Localized>
          )}
          {listing.status === "not_found" && (
            <Localized id="listing-not-found" vars={{ listed: listing.name_as_listed ?? "" }}>
              <p />
            </Localized>
          )}
          {/* A new answer from the server (sent, removed) starts the form from its values. */}
          <Form
            key={`${listing.status}:${listing.requested_at ?? ""}`}
            listing={listing}
            onSaved={closeForm}
          />
          {listing.status === "not_found" && <Remove />}
        </>
      )}
    </main>
  );
}

function Status({
  listing,
  locale,
  onEdit,
}: {
  listing: Listing;
  locale: Locale;
  onEdit: (() => void) | null;
}) {
  const { l10n } = useLocalization();
  const listed = listing.name_as_listed ?? "";
  return (
    <section className="card">
      {listing.status === "listed" && listing.checked_on ? (
        <>
          <p>
            {l10n.getString("listing-mark", {
              listed,
              when: checkedMonth(listing.checked_on, locale),
            })}
          </p>
          {listing.declared_level && (
            <p>
              {l10n.getString("listing-level", {
                level: l10n.getString("listing-level-name", { level: listing.declared_level }),
              })}
            </p>
          )}
        </>
      ) : (
        <p>{l10n.getString("listing-pending", { listed })}</p>
      )}
      <div className="link-person">
        {onEdit && (
          <Localized id="listing-edit">
            <button type="button" className="link" onClick={onEdit} />
          </Localized>
        )}
        <Remove />
      </div>
    </section>
  );
}

/** One native confirm, then the line and the details go. No one is told. */
function Remove() {
  const { l10n } = useLocalization();
  const remove = useRemoveListing();
  const ask = async () => {
    const ok = await confirmDestructive(
      plain(l10n.getString("listing-remove-ask")),
      plain(l10n.getString("links-remove-yes")),
      plain(l10n.getString("delete-cancel")),
    );
    if (!ok) return;
    haptics.impact("light");
    remove.mutate(undefined, {
      onError: () => {
        haptics.notify("error");
      },
    });
  };
  return (
    <>
      <Localized id="links-remove">
        <button
          type="button"
          className="link danger"
          disabled={remove.isPending}
          onClick={() => void ask()}
        />
      </Localized>
      {remove.isError && (
        <Localized id="settings-save-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
    </>
  );
}

function Form({ listing, onSaved }: { listing: Listing; onSaved: () => void }) {
  const { l10n } = useLocalization();
  const save = useSaveListing();
  const [name, setName] = useState(listing.name_as_listed ?? "");
  const [region, setRegion] = useState(listing.region ?? "");
  const [level, setLevel] = useState<ListingLevel | "">(listing.declared_level ?? "");
  const [note, setNote] = useState(listing.note ?? "");
  const [blank, setBlank] = useState({ name: false, region: false });

  const edit = settled(listing);
  // A new request waits a day after the last one; an edit of a waiting or shown one doesn't.
  const mustWait = !edit && !listing.can_send;
  const code = save.error instanceof ApiError ? save.error.code : null;
  const refused = code === "listing_wait";
  const invalid = code === "invalid_listing"; // the server doesn't say which field
  const label = l10n.getString(edit ? "listing-save" : "listing-send");

  const submit = async () => {
    if (mustWait || save.isPending) return;
    const cleanName = name.trim();
    const cleanRegion = region.trim();
    const missing = { name: !cleanName, region: !cleanRegion };
    setBlank(missing);
    if (missing.name || missing.region) return;
    // The level is the teacher's own words; a new name or region has to be looked up again.
    const recheck =
      listing.status === "listed" &&
      (cleanName !== listing.name_as_listed || cleanRegion !== listing.region);
    if (recheck) {
      const ok = await confirmAction(
        plain(l10n.getString("listing-edit-ask")),
        plain(l10n.getString("listing-send")),
        plain(l10n.getString("delete-cancel")),
      );
      if (!ok) return;
    }
    haptics.impact("light");
    try {
      await save.mutateAsync({
        name_as_listed: cleanName,
        region: cleanRegion,
        declared_level: level || null,
        note: note.trim() || null,
      });
    } catch {
      haptics.notify("error"); // the typed text stays, to send later
      return;
    }
    haptics.notify("success");
    onSaved();
  };

  // Telegram's main button keeps one listener; it always reaches the newest values.
  const latest = useRef(submit);
  useEffect(() => {
    latest.current = submit;
  });
  const press = useCallback(() => {
    void latest.current();
  }, []);
  useMainButton(label, press, save.isPending, !mustWait);

  return (
    <form
      className="listing-form"
      onSubmit={(e: SyntheticEvent) => {
        e.preventDefault();
        void submit();
      }}
    >
      <label className="label">
        <Localized id="listing-field-name">
          <span />
        </Localized>
        <input
          type="text"
          value={name}
          maxLength={NAME_MAX}
          aria-invalid={blank.name || invalid}
          aria-describedby="listing-shown"
          onChange={(e) => {
            setName(e.target.value);
          }}
        />
      </label>
      <Localized id="listing-shown-hint">
        <p id="listing-shown" className="hint small" />
      </Localized>
      {(blank.name || invalid) && (
        <Localized id="listing-name-invalid">
          <p className="hint small" role="alert" />
        </Localized>
      )}
      <label className="label">
        <Localized id="listing-field-region">
          <span />
        </Localized>
        <input
          type="text"
          value={region}
          maxLength={REGION_MAX}
          aria-invalid={blank.region || invalid}
          onChange={(e) => {
            setRegion(e.target.value);
          }}
        />
      </label>
      {(blank.region || invalid) && (
        <Localized id="listing-region-invalid">
          <p className="hint small" role="alert" />
        </Localized>
      )}
      <label className="label">
        <Localized id="listing-field-level">
          <span />
        </Localized>
        <select
          value={level}
          onChange={(e) => {
            setLevel(e.target.value as ListingLevel | "");
          }}
        >
          <option value="">{l10n.getString("listing-level-none")}</option>
          {LEVELS.map((value) => (
            <option key={value} value={value}>
              {l10n.getString("listing-level-name", { level: value })}
            </option>
          ))}
        </select>
      </label>
      <label className="label">
        <Localized id="listing-field-note">
          <span />
        </Localized>
        <textarea
          value={note}
          rows={3}
          maxLength={NOTE_MAX}
          aria-describedby="listing-note-hint"
          onChange={(e) => {
            setNote(e.target.value);
          }}
        />
      </label>
      <Localized id="listing-note-hint">
        <p id="listing-note-hint" className="hint small" />
      </Localized>
      {(mustWait || refused) && (
        <Localized id="listing-wait">
          <p className="hint" role={refused ? "alert" : undefined} />
        </Localized>
      )}
      {save.isError && !refused && !invalid && (
        <Localized id="settings-save-failed">
          <p className="hint" role="alert" />
        </Localized>
      )}
      {!mainButtonAvailable() && (
        <button type="submit" className="row-button" disabled={mustWait || save.isPending}>
          {label}
        </button>
      )}
    </form>
  );
}
