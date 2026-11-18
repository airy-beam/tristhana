// UI-06 stage 2 (ADR-0047): the Mini App's navigation is three tabs and one stack. Pure: no
// router and no address changes (Telegram owns the address).

export type Tab = "today" | "practice" | "shala";
export const TABS: readonly Tab[] = ["today", "practice", "shala"];

/** The Settings page to open straight away: Day off, Reminders (UI-06 stage 3). */
export type SettingsFocus = "day-off" | "remind";

/** A screen pushed over a tab. Telegram's Back pops it. */
export type Screen =
  | { name: "settings"; focus?: SettingsFocus }
  | { name: "asanas" }
  | { name: "moon" }
  | { name: "schedule" }
  | { name: "students" }
  /** The message form for all my students (the bot's My students); a shala's is on its card. */
  | { name: "announce" }
  | { name: "listing" };

/** What one shala's card is opened for: the class form, its student invite, the message form
 * over it (the bot's "📣 Announce" from that shala), or its edit form (UI-06 stage 6). */
export type ShalaOpen = "class" | "join" | "announce" | "edit";

/** A one-time intent for the Shala root: the create form open and focused, the invite open, or
 * one shala's card open (`shala:<id>`), also for one thing on it (`class:<id>`, `join:<id>`,
 * `announce:<id>`, `edit:<id>`). */
export type Start = "create" | "invite" | `${"shala" | ShalaOpen}:${string}`;

export interface Nav {
  tab: Tab;
  /** What is shown is the last item; empty means the tab's root. */
  stack: readonly Screen[];
  start: Start | null;
}

export type NavAction =
  | { type: "tab"; tab: Tab; start?: Start }
  | { type: "push"; screen: Screen }
  | { type: "pop" }
  /** The gear and Telegram's ⋯ item: one route, never pushed twice. */
  | { type: "settings"; focus?: SettingsFocus };

export function navigate(nav: Nav, action: NavAction): Nav {
  switch (action.type) {
    case "tab": {
      const start = action.start ?? null;
      if (action.tab === nav.tab && nav.stack.length === 0 && start === nav.start) return nav;
      return { tab: action.tab, stack: [], start };
    }
    case "push":
      return { tab: nav.tab, stack: [...nav.stack, action.screen], start: null };
    case "pop":
      return nav.stack.length === 0 ? nav : { ...nav, stack: nav.stack.slice(0, -1) };
    case "settings": {
      if (nav.stack.at(-1)?.name === "settings") return nav;
      const screen: Screen = action.focus
        ? { name: "settings", focus: action.focus }
        : { name: "settings" };
      return { tab: nav.tab, stack: [...nav.stack, screen], start: null };
    }
  }
}

const UUID = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

/** The Shala root with one shala's card open for `open` (or plainly), when `shala=` is a real
 * id; else the Shala root. A shala the person has left shows the card's "couldn't load", and
 * Back finds the root. */
function card(query: URLSearchParams, open: "shala" | ShalaOpen): Nav {
  const shala = query.get("shala");
  return {
    tab: "shala",
    stack: [],
    start: shala && UUID.test(shala) ? `${open}:${shala}` : null,
  };
}

/** Where a bot button's `?open=…` lands, read once at launch. The values are a contract (old
 * messages keep their URLs); one the app doesn't know opens Today. The bot builds them with
 * `screens.app_url` and lists them in `APP_OPEN` (`screens.py`); a test pins that list against
 * this switch's `case` labels. */
export function launchNav(search: string): Nav {
  const query = new URLSearchParams(search);
  switch (query.get("open")) {
    case "practice":
      return { tab: "practice", stack: [], start: null };
    case "new-shala":
      return { tab: "shala", stack: [], start: "create" };
    case "announce": {
      // From a shala (QF): its card, with the message form over it; Back finds the card.
      const shala = query.get("shala");
      if (shala && UUID.test(shala)) return { tab: "shala", stack: [], start: `announce:${shala}` };
      return { tab: "shala", stack: [{ name: "announce" }], start: null };
    }
    case "listing":
      return { tab: "shala", stack: [{ name: "listing" }], start: null };
    case "settings": // the bot's "⚙️ More in the app" (UI-06 stage 3)
      return { tab: "today", stack: [{ name: "settings" }], start: null };
    // UI-06 stage 6 (spec §2): the bot's shala card, its week and My schedule.
    case "shala": // "🗓 Add or change classes", "🗓 Full week in the app", "🏛 Open in the app"
      return card(query, "shala");
    case "class": // "➕ Add a class", Today's step
      return card(query, "class");
    case "edit-shala": // "✏️ Edit the shala"
      return card(query, "edit");
    case "schedule": // My schedule's "🗓 Full week in the app": Back finds the Shala root
      return { tab: "shala", stack: [{ name: "schedule" }], start: null };
    default:
      return { tab: "today", stack: [], start: null };
  }
}
