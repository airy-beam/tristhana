// UI-06 stage 2 (ADR-0047): the Mini App's navigation is three tabs and one stack. Pure: no
// router and no address changes (Telegram owns the address).

export type Tab = "today" | "practice" | "shala";
export const TABS: readonly Tab[] = ["today", "practice", "shala"];

export type SettingsFocus = "day-off" | "remind";

/** A screen pushed over a tab. Telegram's Back pops it. */
export type Screen =
  | { name: "settings"; focus?: SettingsFocus }
  | { name: "asanas" }
  | { name: "moon" }
  | { name: "schedule" }
  | { name: "students" }
  | { name: "announce"; shala: string | null }
  | { name: "listing" };

/** What one shala's card is opened for: the class form in its schedule, or its student invite. */
export type ShalaOpen = "class" | "join";

/** A one-time intent for the Shala root: the create form open and focused, the invite card
 * open, or one shala's card open (`shala:<id>`), also for one thing on it (`class:<id>`,
 * `join:<id>`). */
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

/** Where a bot button's `?open=…` lands, read once at launch. The values are a contract (old
 * messages keep their URLs); one the app doesn't know opens Today. */
export function launchNav(search: string): Nav {
  const query = new URLSearchParams(search);
  switch (query.get("open")) {
    case "practice":
      return { tab: "practice", stack: [], start: null };
    case "new-shala":
      return { tab: "shala", stack: [], start: "create" };
    case "announce": {
      const shala = query.get("shala");
      return {
        tab: "shala",
        stack: [{ name: "announce", shala: shala && UUID.test(shala) ? shala : null }],
        start: null,
      };
    }
    case "listing":
      return { tab: "shala", stack: [{ name: "listing" }], start: null };
    default:
      return { tab: "today", stack: [], start: null };
  }
}
