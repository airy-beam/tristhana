# ADR-0049: A consent given in the Mini App: the bot's texts under the same keys, and the request names the consent it showed
- Status: accepted (owner, 2026-11-18, with `docs/specs/UI-06-stage-4b-shala-tab.md`; QB as recommended)
- Amends ADR-0031 ("today there is one path, the bot's confirm; the Mini App and API have no accept route") and ID-07 §2 / ID-04 Q12 ("the consent text lives in one place, the bot") for teacher requests only. Builds on ADR-0045 (layered consent) and ADR-0046 (teacher requests).
- Date: 2026-11-18
## Context
UI-06 stage 4 part B lets a student of a shala ask their teacher from the Mini App (ID-07 §10, Q321). Until now every consent in the product was shown and confirmed in the bot: the invite (`t1:a`), the shala join (`h1:a`), the staff link (`h1:b`) and the request (`h1:ta`). Two rules rest on that. ADR-0031: a flag such as `quiet_note_agreed` is set only by the confirm of a text that names what it grants, and a change of promises gets a new callback letter, because a button stays tappable in a chat. ADR-0045: the short screen and the full text are one consent, kept in step by an item table tested on `bot.ftl`.

An API route has no callback letter, and the server cannot see which text a client drew. The two request texts also name a bot place ("any time in /teachers"), which is wrong in the app and has been a hidden command since UI-06 stage 1.
## Decision
- **The app shows the bot's messages, not its own.** The keys of the question and both consent layers (`request-ask`, `request-ask-one`, `request-yes`, `request-consent-short`, `request-until-yes`, `request-know-them`, `request-consent`, `consent-details`, `consent-short-back`) are copied under the same keys into a lazy app file (`locales/{en,ru}/ask.ftl`). A test keeps every copied message byte-equal to the bot's, per locale and with each variable value (the stage 3 "words in step" pattern). So ADR-0045's item table, which runs on `bot.ftl`, holds for the app as well, and there is still one consent record.
- **The texts name no surface** (QB): "any time in /teachers" becomes "any time" in both request texts and both languages. The promises do not change (remove any time, no one is told), so this is ADR-0045's "presentation only": no new column, no new letter. `invite-consent` and the other bot-only consents stay unchanged on purpose.
- **The request names the consent it showed.** `POST /api/v1/me/teacher-requests` carries `consent`, a closed enum whose one value today is `"request-1"`. The value names a set of promises, not a wording: the server maps it to what the tap grants (`quiet_note_agreed = true` for `request-1`), in the domain, next to the bot's `h1:ta`, which names the same value. The client never sends a flag.
- **A change of promises is a new value**, the API's twin of a new callback letter (ADR-0031): the texts change in both products in one pull request, the new value grants the new set, and an old value stays accepted with its old grants for as long as an old bundle may send it. An unknown value is 422.
- **Only requests move.** Accepting a personal invite (`t_`), joining a shala (`h_`) and accepting a staff link (`hs_`) still land in the bot; the invite code still never reaches the API.
## Consequences
- One text, two surfaces: any edit to a request consent fails a test until both files agree, so the app cannot drift from the record.
- The app's copies cost the first chunk nothing: `ask.ftl` loads with the lazy picker.
- The route asks the teacher's note to be sent inside the request (direct, silent, up to 3 s), as the bot's tap does; that tap is slower than other writes.
- A forged client can send `request-1` without showing the text. So can a forged Telegram client tap `h1:ta` without reading it; the protection was always the honest client plus the teacher's own yes, not the transport.
- Removing "/teachers" changes the request texts' byte-for-byte tests and the item table's last-but-one entry; the invite consent keeps its wording until stage 5.
## Alternatives considered
- **A boolean `quiet_note_agreed` in the body:** simplest, but the client then grants itself a flag, and a later consent change has nowhere to say which text was shown.
- **App-only keys with the app's own place names** ("on the Shala tab"): reads best in each product, but two consent records to keep in step, and the item table would have to run on both files.
- **Copy the bot's texts verbatim, "/teachers" included:** no bot change, but the app would point at a command it cannot open, and the bot at a command its menu no longer lists.
- **No ask route; a button that opens the bot's question (`t.me/<bot>?start=…`):** the consent stays bot-only, but it leaves the app for a chat in the middle of the one action this stage adds, and needs a new start payload.
