# ST-10: moon day card (a share card for the coming moon day)

- Status: **accepted** (owner: "All as recommended", 2026-11-21) · Date: 2026-11-21 · Size M, Phase 3
- Requirements: **ST-10** (new): a share card for the coming moon day, built on **ST-07** (share cards, ADR-0040). Reuses **MD-01** (stored calendar), **MD-02** (effective moon location), **MD-05** (SYC override), **UI-06** (Today).
- Related ADRs: 0006 and 0009 (moon module), 0040 (share cards), 0044 (time labels). New: **ADR-0052** (sunrise computed for a single day when a card is made).

## 1. Scope
**In:** a fifth card kind, `moon`, in story and square formats. A person can share it from **3 days before** a moon day **through the day itself**, using the moon days of the city they follow (their own, their teacher's or their shala's: the MD-02 resolver, the same one Today uses). It opens from the Mini App's Today moon row and from the Moon screen, with the same share sheet as ST-07: Story | Square, Share to story, Save image, Send to my chat.
**Out:** tithi start and end times (they are not calculated anywhere, and finding them needs a new search); illumination percentage and zodiac or nakshatra; real orbital angles (on a moon day the drawing would look the same); a bot entry point (ST-07 Q207: the bot has no share entry yet); a card for a moon day outside the window.

## 2. The card
Same brand palette, header (mark + "Tristhana") and footer ("Tristhana · @tristhana_bot") as the ST-07 cards. No emoji glyphs: everything is drawn. **Card text never addresses the reader** and **never says "today" or "in N days"**: it states the date, so it stays true whenever it is seen.

| Element | Content |
|---|---|
| Stars | A sparse starfield, deterministic per date and city (seeded random), so the same card renders to the same bytes |
| Kicker | "Moon day" / «Лунный день» (saffron pill, like "New asana") |
| Moon | Large and drawn. **Full moon:** a glowing off-white disc with a soft halo and faint maria. **New moon:** a dark disc with a thin saffron rim (a stylised drawing: a new moon can't really be seen) |
| Headline | "Full moon" / «Полнолуние», or "New moon" / «Новолуние» |
| Subline | "Purnima" / «Пурнима» (or "Amavasya" / «Амавасья»), then the IAST `pūrṇimā` / `amāvasyā` smaller, as metadata. Kshaya days add "Kshaya" to the name |
| Date | The full date with weekday: "Tuesday, 24 November 2026" / «Вторник, 24 ноября 2026» (Babel) |
| Sunrise and place | "Sunrise 06:25 Mysuru" / «Восход солнца 06:25 Майсур», to the nearest minute («солнца», so it can't read as moonrise). The local sunrise at the followed city. The line is left out if sunrise can't be computed |
| Diagram | Sun, Earth and Moon on one line, in the right order: at full moon the Earth sits between the Sun and the Moon; at new moon the Moon sits between them. Earth and Moon are lit on the Sun side, and the Moon's orbit is drawn dotted. Labels: Sun · Earth · Moon. A simplified drawing, not to scale |
| Notes (small) | "A traditional rest day in Ashtanga" (first: the square shows only this one); "Moon days follow the tithi at local sunrise" (why the city is shown); on kshaya days "The tithi begins and ends between two sunrises", which describes the tithi only and never claims which day tradition observes (open question 10: SYC once differed by a day) |
| Next | "Next: New moon · 8 December" / «Далее: новолуние · 8 декабря» (from the stored calendar; left out when the calendar has no later day within 35 days) |

Story 1080×1920 puts the moon high, the text centred under it, the diagram as a band near the bottom, then the notes; all text stays out of the top and bottom 250 px. Square 1080×1080 puts the moon on the left and the text on the right, with the diagram as a thin band at the bottom; it has no room for the notes or the next moon day.

**City on a card:** ST-07 keeps the city off cards (Q202). The moon card is the one exception, because moon days differ by place and the card would be wrong without it. It shows only a city from the curated list of 34, never a teacher or shala name or where the choice came from.

**Time label (ADR-0044):** the sunrise names its place ("06:25 Mysuru") and adds no UTC offset, even though whoever sees the card has an unknown zone. Sunrise is a fact about that place, not an appointment to be in time for. This is a flagged exception.

**MD-05:** where SYC's official dates replace the calculated ones, the date may not be the day the calculation assigns. The card never prints an exact full or new moon time; the sunrise shown is simply the sunrise on that date in that city, which is always true.

## 3. Flows (Mini App only)
- **Today:** while the next moon day is 0–3 days away, the moon row ("Next moon day · …") gets a small "Share" button beside it. Tapping the row still opens the Moon screen. The row and the button are separate controls (no nested buttons).
- **Moon screen:** the same "Share" button next to the first moon day in its list, again only within the window.
- **Share sheet:** unchanged (ST-07). The story caption for this kind is `share-story-caption-moon` "Moon day · @tristhana_bot" / «Лунный день · @tristhana_bot». The bot's caption under "Send to my chat" stays the general one.
- The window is counted from the server's today (`moon.today`), as the moon row already is.

## 4. Domain, use cases, ports
- **`domain/share_cards.py`:** `MoonCard(date, phase: MoonPhase, kshaya, city: City, sunrise: time | None, next: MoonDay | None)`, plus `MOON_CARD_LEAD = 3` and `moon_card(today, day, city, sunrise, following) -> MoonCard | None`: None when `day` is outside `today … today + 3`. `is_empty` is False.
- **`application/share_cards.py`:** `MoonSubject(date)`. Steps: the account's local today, then `moon_follow_of(account, cities)` for the effective city, then **one statement** for `moon.days(city.slug, today, today + 35)`. The date must be one of those days and inside the window, otherwise `CardNotFound` (404). Then `MoonCalculator.sunrise(city.location, date)`, converted to the city's wall clock (None on any `MoonError`: the card is drawn without that line). `CreateShareCard` gains `cities`, `moon` (calendar repo) and `sunrise` (the port below). `_kind` is "moon"; the file name is `tristhana-moon-2026-12-05-story.png`.
- **Port `SunriseCalculator.sunrise(location, day) -> datetime | None`** (a UTC instant; its own port beside `MoonCalculator`, which `GeneratorMoonCalculator` also implements). The adapter runs it in a worker thread through `tristhana.moon.sunrise_at` (new public wrapper around `_ephemeris.sunrise_jd`, under the ephemeris lock). **No new algorithm**: it is the same function the calendar uses (ADR-0052).
- **Renderer:** `text.py` resolves the strings (city name in the locale, Babel full date, time `HH:mm`). `draw.py` gets `draw_moon` (starfield, moon disc, diagram, text). It still imports no moon code and only draws what the card holds.

## 5. API
`POST /api/v1/me/share-cards` takes one more union member, `{kind: "moon", date: "2026-12-05"}`, and returns 404 `not_found` when the date isn't one of the caller's moon days within the window. Everything else (201 shape, 429, 503, `/send`, `/share/v1/`) is unchanged. Regenerate the TS client.

## 6. Migration `00xx_share_card_moon`
Replace the `share_card_kind_check` CHECK to allow `'moon'` (expand-only; the downgrade deletes moon rows, then restores the old check).

## 7. Cross-cutting checks
- **Time:** the window uses the account's local today (provisional zone allowed, as on Today). Sunrise is an instant shown in the **city's** zone, labelled with the city's name. The date is a plain local date.
- **Privacy:** owner only. The card shows the followed city, never a teacher or shala name and never its source. It holds no practice data at all.
- **i18n:** `card.ftl` en/ru, with the reader-free grep test extended to the new keys. City names come from `cities.yaml` (en/ru). The IAST names need `ā ū ṇ ṣ`, so the coverage test checks them. "tithi" and "kshaya" reach users here for the first time: both go into `docs/glossary.yaml` (`expert: true`).
- **Responsiveness:** one statement for the calendar, plus a sunrise computation of a few ms in a thread (swisseph is imported lazily on the first card, like Pillow), plus the render. Target < 400 ms p50 warm server time, as for ST-07. Mini App: Today gains only a button (the sheet stays a lazy chunk).

## 8. Test plan
- **Domain:** window edges (−1, 0, 3, 4 days); kshaya and phase are carried; `is_empty` is False.
- **Use case (fakes):** own city, FOLLOW_TEACHER and the default city all give that city's days; a non-moon date → `CardNotFound`; out of window → `CardNotFound`; a sunrise failure → a card without sunrise; the next moon day is picked; the rate limit still applies.
- **moon:** `sunrise_at` matches `sunrise_jd` for Mysuru on a known date (minute precision); a polar date → None.
- **Renderer:** exact size, PNG signature, deterministic bytes, under 400 KB, for full (Mysuru 24 Nov 2026), new (Moscow 8 Dec 2026) and kshaya (Mysuru 4 Dec 2025, a real Kshaya Purnima) in both formats, with and without sunrise and next; the font covers the new strings and IAST; reference PNGs reviewed by eye.
- **i18n:** en/ru parity; the grep list.
- **API:** the union in OpenAPI; moon 201; 404 for a non-moon date; migration up/down/up and `alembic check`.
- **Mini App:** the Share button on the moon row only at 0–3 days away; none at 4; the row tap still opens the Moon screen; the Moon screen's button; the caption per kind; `TZ=UTC`; bundle check.

## 9. Decisions (owner: "All as recommended", 2026-11-21)
- The window is 3 days before through the day itself.
- Mini App only: the Today moon row and the Moon screen.
- Content: phase, Sanskrit name + IAST, date, sunrise and city, a simplified Sun–Earth–Moon diagram, the next moon day, a rest-day line; no tithi times.
- The city is shown on this card (an exception to Q202).
- Sunrise is computed for one day when the card is made (ADR-0052).

## 10. Build notes (2026-11-21)
- Review blocker fixed: the starfield first kept clear of text with a filter over the whole image, which took ~3.5 s per card and held the GIL. Each star now checks only its own 31 px neighbourhood (and keeps out of the Moon's orbit); a card renders in ~0.1–0.2 s. A renderer test guards the time.
- Sunrise is rounded to the nearest minute (Mysuru on 24 Nov 2026: 06:24:50 → 06:25).
- Mini App: the share sheet has its own caption and privacy note for this card (`share-story-caption-moon`, `share-privacy-note-moon`). The Share button on Today stands beside the moon row (`.lrow-share`), never inside it.
