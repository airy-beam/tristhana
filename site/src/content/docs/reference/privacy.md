---
title: "Privacy in plain words"
description: "What Tristhana stores, who can see it, and what is encrypted."
features: [WH-04, ST-09]
---

What Tristhana stores, who can see it, and what is encrypted.

## What Tristhana stores

- What you log: days, practices, check-ins, diary notes, your asanas.
- Your Telegram name and language, and the name you choose in the settings.
- Your settings: city and time zone, day off, reminders.
- Your lists: teachers, students and shalas, and your attendance marks.

A location you send to the bot is used once to find your time zone and isn't stored.

## What is encrypted

Diary notes and 🌸 days are stored encrypted. In the database a 🌸 day looks like any other rest day, and neither can be read without the application's key. For a rest over several days (sick, traveling or 🌸) the reason is encrypted too.

Other things you log, such as a single sick or travel day, a moon day and check-ins, are stored without this extra encryption. Nobody else in Tristhana can see them.

## Who sees what

|                                   | You | Your teacher | Shala team |
| --------------------------------- | --- | ------------ | ---------- |
| Your name                         | ✓   | ✓            | ✓          |
| Practice or rest, practice length | ✓   | ✓            | –          |
| Your last asana                   | ✓   | ✓            | –          |
| The reason for a rest             | ✓   | –            | –          |
| Check-ins and diary notes         | ✓   | –            | –          |
| Badges, counts and statistics     | ✓   | –            | –          |
| Marks for classes you came to     | ✓   | –            | ✓          |

- A teacher sees your practice and rest only from the day you add them. Earlier days stay with you.
- If nothing shows for about three weeks, your teacher sees one short line saying just that, with no reason.
- A teacher on your list can mark a new asana for you. You get a message and can undo it.
- Students of a teacher or a shala never see each other.
- A teacher sees all rest as the same thing, whatever the reason.
- There are no leaderboards and no public profiles.

If you teach or work at a shala: your students see the moon city you chose, everyone in a shala sees the team's names and roles, and a request for the SYC directory line is read by the person who checks it.

## Links and cards you share

- Your calendar subscription is a private link. Anyone who has it sees your class schedule, with shala and teacher names, and your moon days, but not your name or your log. You can replace it at any time.
- A share card shows only what is on the picture. You choose whether to send it to anyone.

## This site

This guide uses no cookies and no analytics, and it loads nothing from other sites.

## Leaving

You can download everything you logged as one file, and you can delete your account. Deleting is immediate and can't be undone. Copies in backups disappear within 30 days. See [Your data](../../students/your-data/).

## Open source

The code is public, so anyone can check how this works: [GitHub](https://github.com/airy-beam/tristhana).
