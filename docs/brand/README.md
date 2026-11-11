# Brand assets

Palette and motif from the notes (`10 Naming & Branding`): deep indigo, saffron/ochre, off-white paper; three dots for asana · breath · drishti under a crescent moon.

- `botfather.md`: the bot's description and about texts in English and Russian (UI-05); the owner sets them in @BotFather.
- `launch.md`: the public launch post texts in Russian and English; the owner posts them by hand. Their stories: `src/story_launch_*.html` (what it does) and `src/story_launch_about_*.html` (free, open source, private, not for profit).
- `description-640x360.png`: the picture above the bot's description, made from `src/description_pic.html`. Set it in @BotFather with `/setdescriptionpic`.
- `avatar.svg` / `avatar-640.png`: the bot avatar. Set it in @BotFather with `/setuserpic` (send the PNG as a photo).
- `src/`: HTML sources of the promo images (Instagram stories 1080×1920, group card 1280×960), sharing `style.css`. Rendered copies live in the notes (`attachments/tristhana_bot/tristhana_*.png`).
- `render.sh SRC OUT WIDTH HEIGHT`: renders a source with headless Chrome, e.g.
  `./render.sh src/story_beta_ru.html ~/Documents/pumpkin_notes/attachments/tristhana_bot/tristhana_story_beta_ru.png 1080 1920`.

Stories keep text out of the top and bottom ~250 px (Instagram's own UI). Layout variants in `style.css`: `roomy` for short stories, `compact` for ones with numbers, `tight` for six list items plus a call to action (the launch stories). Fonts: Lato and Noto Serif Display (both with Cyrillic), installed locally.
