# BotFather texts (UI-05)

What people see before they press Start, and on the bot's profile. The owner sets them with
one command; nothing is applied automatically.

The texts live in the bot's own string files, next to the command menu: `bot-description`
and `bot-about` in `backend/src/tristhana/infrastructure/i18n/locales/{en,ru}/bot.ftl`.
English is the default; people whose Telegram is in Russian see the Russian ones.

| Text | Where people see it | Limit |
|---|---|---|
| `bot-description` | The empty chat, above the Start button | 512 characters |
| `bot-about` | The bot's profile, and when the bot is shared | 120 characters |

## Setting them

```sh
python3 tools/telegram/set_webhook.py --texts
```

It reads the bot token from Secret Manager with your gcloud login, sets the four texts and
touches nothing else (the webhook and the menus stay as they are). A full run of the script
without flags sets them too. @BotFather's own `/setdescription` and `/setabouttext` set one
text for every language, so they can't do the Russian ones; a text set there is replaced by
the next run of the script.

To change a text, edit both `bot.ftl` files and run the command again. A test keeps them
within the limits.

A picture above the description (640×360) is set in @BotFather with `/setdescriptionpic`.

## Pictures

The guide's screenshots are made by `cd site && npm run shots` and live in
`site/src/assets/shots/<lang>/`. For a store-style set of three, in this order:

1. `app-home.webp`: today's question, practice or rest.
2. `app-my-practice.webp`: the year, the month and practices in a row.
3. `bot-moon.webp`: the next moon days for a city.

They are phone-shaped (390 wide). The description picture is 640×360, so it needs its own
layout; `docs/brand/render.sh` makes one from a source in `docs/brand/src/` (not made yet).

## Rules for these texts

- The same tone as the product: friendly, plain, no "streak", "missed" or "skipped".
- 🌸 is not named here: it is a private topic and these texts are public.
- Privacy lines say only what the code does today.
- When the guide moves to its own domain (Q270), change the address in all four texts. The Russian about text has 10 characters to spare.
- Check on a phone that Telegram makes the bare address tappable; if not, add `https://` (8 characters, still within every limit).
