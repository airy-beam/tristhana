# ADR-0044: A displayed time always names its place; the UTC offset shows only outside the viewer's own zone
- Status: accepted (owner, 2026-11-16, with `docs/specs/UI-06-simple-journey.md`)
- Amends ADR-0005 ("Every displayed time carries a zone label") and the display rule in the notes' `06 Time Zones.md`. Storage rules of ADR-0005 are untouched.
- Date: 2026-11-16
## Context
ADR-0005 and `CLAUDE.md` require every displayed time to read `07:00 Almaty (UTC+5)`. The UI-06 audit found that the offset is noise for the people the product is about to launch to: on their own reminder time, their own practice start time and their own schedule it repeats a fact they never need, in notation most of them do not read. The offset earns its place only when a time belongs to somewhere else (an online class in Berlin, a shala in another country).

Today the label is built in one place per side: `infrastructure/i18n/fluent.py::format_time_label` from a `TimeArg(day, at, zone, place)` (bot, ICS descriptions), and `zoneLabel` in `miniapp/src/screens/practiceText.ts` (Mini App). Neither knows who is looking.
## Decision
- **The place always shows.** A clock time is never shown bare: `07:00 Almaty`. The city is the home city when it names the zone (ADR-0029), otherwise the zone's own city.
- **The offset shows only for another zone.** `(UTC+5)` is appended when the time's IANA zone is not the viewer's own zone: `17:30 Berlin (UTC+1)` for a viewer in Almaty.
- **"Own zone" is the same IANA name** as `account.timezone`, not an equal offset. Almaty and Tashkent share a clock today but are different zones, so the offset shows; Moscow and Kazan are one zone, so it does not. Names are compared, so the answer never flips on a daylight-saving date.
- **Unknown viewer zone: the offset shows.** Nothing can be called "your own" yet.
- **`UTC` stays `07:00 UTC`.**
- **One pure function decides.** `domain/time_label.py`: `offset_shown(zone, viewer_zone) -> bool` and `offset_text(zone, day, at) -> str` (`UTC+5`, `UTC+5:30`), `zoneinfo` only. `TimeArg` gains `viewer: str | None = None`; the Fluent formatter calls the domain function and keeps only the city-name lookup (Babel). The Mini App mirrors it in one TypeScript function, tested against the same table of cases.
- **`viewer=None` means "show the offset"**, which is today's output. A call site that has not been migrated therefore errs toward more information, never less.
- **Zone descriptions keep the offset.** Where the text says what a zone is, instead of labelling a time, the offset is the information: the Settings city row for an unlisted city, the reply after a shared location, the travel prompt, the day row that marks the viewer's own daylight-saving change, the `⚠` shift line.
- **Texts read later or elsewhere keep the full label.** ICS event descriptions are read in a calendar app at another time and maybe in another place, so they always carry the offset. Exports are unchanged.
- **Rollout by surface:** the bot in UI-06 stage 1 (every `TimeArg` and `zone_label` call passes the viewer's zone); the Mini App with the screen each stage rebuilds (stage 2 Today, stage 3 Practice and Settings, stage 4 Shala); ICS never.
## Consequences
- `CLAUDE.md` ("Time"), `06 Time Zones.md` (principle 5 and "Display rules") and the ADR list in `04 Architecture.md` need the new wording when this is accepted; ADR-0005 gets an "Amended by ADR-0044" line.
- Tests that pin `(UTC+5)` on a person's own time change (bot: practice summary, reminder and moon status lines, My schedule and attendance headers, shala card for a same-zone member). Second labels for another zone keep their offset.
- During stages 2–4 the bot and parts of the Mini App show the same own-zone time differently. Accepted: each screen is consistent in itself.
- A traveller whose profile zone is stale sees their old zone's times with no offset. The travel prompt (ADR-0021) and the city name remain the signal.
- Two people comparing screenshots no longer see an offset on times each of them reads as their own.
## Alternatives considered
- **Compare offsets, not zone names:** hides the offset for same-clock neighbours, but flips on daylight-saving dates and makes `07:00 Tashkent` ambiguous for an Almaty viewer.
- **Drop the offset everywhere and show it on tap:** simplest to read, but a bot message has no tap-to-reveal, and an online class in another zone needs it at a glance.
- **"Your time" in place of a city for own-zone times:** friendly, but loses the city, which is what tells a traveller their profile zone is stale.
- **Keep the rule:** correct and uniform, and the noise the owner asked to remove.
