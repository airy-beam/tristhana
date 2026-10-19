# Brand assets

Palette and motif from the notes (`10 Naming & Branding`): deep indigo, saffron/ochre, off-white paper; three dots for breath · bandha · drishti under a crescent moon.

- `avatar.svg` / `avatar-640.png`: the bot avatar. Set it in @BotFather with `/setuserpic` (send the PNG as a photo).
- `src/`: HTML sources of the promo images (Instagram stories 1080×1920, group card 1280×960), sharing `style.css`. Rendered copies live in the notes (`attachments/tristhana_*.png`).
- `render.sh SRC OUT WIDTH HEIGHT`: renders a source with headless Chrome, e.g.
  `./render.sh src/story_beta_ru.html ~/Documents/pumpkin_notes/attachments/tristhana_story_beta_ru.png 1080 1920`.

Stories keep text out of the top and bottom ~250 px (Instagram's own UI). Fonts: Lato and Noto Serif Display (both with Cyrillic), installed locally.
