# Tristhana 🧘

*Breath · Bandha · Drishti*. A practice companion for the Ashtanga yoga community: Telegram bot + Mini App.

- Product notes: `~/Documents/pumpkin_notes/02_projects/tristhana_bot/00 Index.md`
- Contributor/agent guide: [CLAUDE.md](CLAUDE.md)
- Decisions: [docs/adr](docs/adr)

Status: **Phase 0: Foundations** (see roadmap note).

## License
[GNU AGPL-3.0](LICENSE). The moon-day module uses [Swiss Ephemeris](https://www.astro.com/swisseph/) via `pyswisseph` under the AGPL (see [ADR-0009](docs/adr/0009-swiss-ephemeris-agpl.md)). If you run a modified version as a network service, the AGPL requires you to offer its source to your users.

A location shared with the bot is turned into a time zone offline with [tzfpy](https://github.com/ringsaturn/tzfpy) (MIT). Its time zone boundary data comes from [timezone-boundary-builder](https://github.com/evansiroky/timezone-boundary-builder), © OpenStreetMap contributors, available under the [ODbL](https://opendatacommons.org/licenses/odbl/) (see [ADR-0029](docs/adr/0029-home-city-drives-zone.md)).
