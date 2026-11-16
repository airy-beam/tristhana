# ADR-0047: Mini App navigation is three tabs and one stack; a screen shows Back or the tabs, never both
- Status: proposed (with `docs/specs/UI-06-stage-2-app-shell.md`; the owner decides Q332 there)
- Builds on ADR-0013 (generated client) and the Back-layer list in `miniapp/src/telegram/index.ts`. Replaces the single `view` state in `App.tsx`.
- Date: 2026-11-16
## Context
The Mini App is a hub: `App.tsx` holds one `view` value out of twelve, Home is a list of doors, and every screen takes an `onBack` chosen by whoever opened it (`students` and `links-students` are the same screen with two ways back). The owner approved three bottom tabs (Today, Practice, Shala) and a gear (UI-06, Q300, Q304). Stages 3 and 4 rebuild the Practice and Shala tabs on whatever stage 2 lays down, and `?open=` values in bot messages already sent must keep landing somewhere sensible.

Three facts constrain the design. Telegram offers one header button, Close or Back, and Android's hardware back follows it. Screens keep their own inner layers (a shala card over the lists, Badges over Stats, the day editor, an unsaved note) through `useBackButton`, so the shell cannot know how deep a screen is. The first chunk is at 147.6 of 150 KB gzip.
## Decision
- **State is `{ tab, stack, start }` in a pure reducer** (`shell/nav.ts`). No router library; the address is never changed, because Telegram owns it. `start` is a one-time intent for a root (the create-shala form open, the invite open).
- **One thing is mounted:** the top of the stack, else the tab's root. A tab switch clears the stack; returning to a tab shows its root. A hidden, still-mounted screen would keep its Back layer and its queries alive.
- **Back or tabs, never both.** The tab bar is drawn only while no Back layer is mounted (`useBackShown()`, counted also where Telegram's button is unavailable). Roots have tabs and Telegram's Close; every pushed screen, inner layer, form and unsaved note has Back and no tabs.
- **Roots never register a Back layer.** A launch link that lands on a tab root has no Back; one that lands on a pushed screen goes back to that tab's root.
- **Settings is a pushed screen with one route:** the gear on the roots and Telegram's ⋯ item call the same function.
- **Today is in the first chunk; the other tabs and every pushed screen are lazy**, inside one error boundary that keeps the tab bar on screen when a chunk fails to load.
- **While a text field has focus the bar is hidden by CSS**, so it never sits on the keyboard on either platform.
## Consequences
- A screen no longer chooses where Back goes: it pops. `onBack` props stay for the screens' own inner layers.
- Leaving a tab drops its inner state (the month chosen on Stats, an open shala card). Cached queries make the return immediate; a stage that needs more keeps that state in the reducer.
- The tab bar disappears while a day editor or an unsaved note is open on a root. Accepted: it protects the text and follows the one rule.
- New `?open=` values map to a tab plus an optional pushed screen in one place (`launchNav`); unknown values open Today.
- `telegram/index.ts` must track layers where Telegram's Back is unavailable; tests that mock the module add `useBackShown`.
## Alternatives considered
- **Tab bar always visible:** familiar from native apps, but it stacks on Telegram's main button and the keyboard on every form, lets a tab tap discard an unsaved note, and needs per-tab stacks to be worth it.
- **Keep every tab mounted and hide the inactive ones:** keeps scroll and inner state, but hidden screens keep their Back layers and refetch in the background.
- **A router library with URLs:** deep links for free, at several KB in a first chunk with 2.4 KB to spare, and Telegram's webview gives the address bar no use.
- **Back on the Practice and Shala roots leading to Today** (the Android convention): puts a Back arrow on a root on iOS, where a person would no longer know which level they are on.
