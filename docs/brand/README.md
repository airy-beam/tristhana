# Brand assets

Palette and motif from the notes (`10 Naming & Branding`): deep indigo, saffron/ochre, off-white paper; three dots for asana · breath · drishti under a crescent moon.

- `botfather.md`: the bot's description and about texts in English and Russian (UI-05); the owner sets them in @BotFather.
- `launch.md`: the public launch post texts in Russian and English; the owner posts them by hand. Their stories: `src/story_launch_*.html` (what it does) and `src/story_launch_about_*.html` (free, open source, private, not for profit).
- `src/carousel_launch_gen.py`: the Instagram carousel for the launch (a feed post, 20 slides of 1080×1350 in each language, with the guide's screenshots); its captions are in `launch.md`. `python3 src/carousel_launch_gen.py ~/Documents/pumpkin_notes/attachments/tristhana_bot/carousel` renders all 40 PNGs. `src/promo_shots/` holds two screens shot for promo with the 🌸 button hidden (how to re-shoot them is in the script's header).
- `description-640x360.png`: the picture above the bot's description, made from `src/description_pic.html`. Set it in @BotFather with `/setdescriptionpic`.
- `avatar.svg` / `avatar-640.png`: the bot avatar. Set it in @BotFather with `/setuserpic` (send the PNG as a photo).
- `src/`: HTML sources of the promo images (Instagram stories 1080×1920, group card 1280×960), sharing `style.css`. Rendered copies live in the notes, in subfolders of `attachments/tristhana_bot/`: `launch/` (public launch stories and a copy of the description picture), `carousel/`, `beta/` (beta invitation and group stories), `phases/` (progress stories); `teasers/` and `series/` have no sources here.
- `render.sh SRC OUT WIDTH HEIGHT`: renders a source with headless Chrome, e.g.
  `./render.sh src/story_beta_ru.html ~/Documents/pumpkin_notes/attachments/tristhana_bot/beta/tristhana_story_beta_ru.png 1080 1920`.

Stories keep text out of the top and bottom ~250 px (Instagram's own UI). Layout variants in `style.css`: `roomy` for short stories, `compact` for ones with numbers, `tight` for six list items plus a call to action (the launch stories). Fonts: Lato and Noto Serif Display (both with Cyrillic), installed locally.
