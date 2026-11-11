# BotFather texts (UI-05)

What people see before they press Start, and on the bot's profile. The owner sets them in
@BotFather; nothing here is applied automatically.

| Where | BotFather command | Limit |
|---|---|---|
| The empty chat, above the Start button | `/setdescription` | 512 characters |
| The bot's profile, and when the bot is shared | `/setabouttext` | 120 characters |
| A picture above the description | `/setdescriptionpic` | 640×360 |

BotFather sets one text for every language. To show Russian to people whose Telegram is in
Russian, set the English text as the default and the Russian one for `ru` with the Bot API
methods `setMyDescription` and `setMyShortDescription` (`language_code: "ru"`).

## Description

English (316 characters):

```
Tristhana is a companion for your Ashtanga practice.

🧘 Log practice or rest in one tap
🌙 Moon days for your city, with reminders
📊 Your year, your month, your asanas
👥 Teachers and shalas: schedule, attendance, announcements

Your log is yours. A teacher sees only what you agree to.

Guide: tristhana-guide.web.app
```

Russian (326 characters):

```
Тристхана — спутник твоей практики аштанги.

🧘 Отмечай практику или отдых одним нажатием
🌙 Лунные дни для твоего города, с напоминаниями
📊 Твой год, твой месяц, твои асаны
👥 Учителя и шалы: расписание, посещения, объявления

Журнал — твой. Учитель видит только то, на что ты соглашаешься.

Справка: tristhana-guide.web.app/ru/
```

## About

English (108 characters):

```
Your Ashtanga companion: a log for practice and rest, moon days, your asanas. Guide: tristhana-guide.web.app
```

Russian (110 characters):

```
Твой спутник в аштанге: журнал практики и отдыха, лунные дни, твои асаны. Справка: tristhana-guide.web.app/ru/
```

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
