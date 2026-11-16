import { launchNav, navigate, type Nav } from "./nav";

// UI-06 stage 2 (spec §2, ADR-0047): three tabs and one stack, in a pure reducer.

const SHALA = "00000000-0000-0000-0000-0000000000c1";
const root = (tab: Nav["tab"]): Nav => ({ tab, stack: [], start: null });

describe("launchNav: where a bot button's ?open=… lands (the values are a contract)", () => {
  test.each(["", "?", "?open=", "?open=somewhere-new", "?open=new-shala%20", "?shala=x", "%%%"])(
    "nothing, unknown or malformed opens Today: %j",
    (search) => {
      expect(launchNav(search)).toEqual(root("today"));
    },
  );

  test("practice opens the Practice root, with nothing to go back to", () => {
    expect(launchNav("?open=practice")).toEqual(root("practice"));
  });

  test("new-shala opens the Shala root with the create form", () => {
    expect(launchNav("?open=new-shala")).toEqual({ tab: "shala", stack: [], start: "create" });
  });

  test("announce opens the composer over the Shala tab, for that shala", () => {
    expect(launchNav(`?open=announce&shala=${SHALA}`)).toEqual({
      tab: "shala",
      stack: [{ name: "announce", shala: SHALA }],
      start: null,
    });
  });

  test.each(["?open=announce", "?open=announce&shala=", "?open=announce&shala=1%20OR%201"])(
    "announce without a real shala id composes with none: %s",
    (search) => {
      expect(launchNav(search).stack).toEqual([{ name: "announce", shala: null }]);
    },
  );

  test("listing opens the directory line over the Shala tab", () => {
    expect(launchNav("?open=listing")).toEqual({
      tab: "shala",
      stack: [{ name: "listing" }],
      start: null,
    });
  });
});

describe("navigate", () => {
  test("push puts a screen on top, pop takes one off", () => {
    const pushed = navigate(root("practice"), { type: "push", screen: { name: "asanas" } });

    expect(pushed).toEqual({ tab: "practice", stack: [{ name: "asanas" }], start: null });
    expect(navigate(pushed, { type: "pop" })).toEqual(root("practice"));
  });

  test("pop on a root changes nothing", () => {
    const nav = root("today");

    expect(navigate(nav, { type: "pop" })).toBe(nav);
  });

  test("a tab switch clears the stack", () => {
    const deep: Nav = {
      tab: "shala",
      stack: [{ name: "students" }, { name: "settings" }],
      start: null,
    };

    expect(navigate(deep, { type: "tab", tab: "today" })).toEqual(root("today"));
  });

  test("the active tab, already on its root, stays the same state", () => {
    const nav = root("practice");

    expect(navigate(nav, { type: "tab", tab: "practice" })).toBe(nav);
  });

  test("a tab switch can carry a start for the Shala root", () => {
    expect(navigate(root("today"), { type: "tab", tab: "shala", start: "invite" })).toEqual({
      tab: "shala",
      stack: [],
      start: "invite",
    });
    expect(navigate(root("today"), { type: "tab", tab: "shala", start: `shala:${SHALA}` })).toEqual(
      { tab: "shala", stack: [], start: `shala:${SHALA}` },
    );
  });

  test("a start is used once: leaving the root drops it", () => {
    const started: Nav = { tab: "shala", stack: [], start: "create" };

    expect(navigate(started, { type: "push", screen: { name: "students" } }).start).toBeNull();
    expect(navigate(started, { type: "tab", tab: "today" }).start).toBeNull();
    const back = navigate(navigate(started, { type: "settings" }), { type: "pop" });
    expect(back).toEqual(root("shala"));
  });

  test("Settings opens over whatever is shown, and Back returns there", () => {
    const over: Nav = { tab: "shala", stack: [{ name: "students" }], start: null };

    const open = navigate(over, { type: "settings" });

    expect(open.stack).toEqual([{ name: "students" }, { name: "settings" }]);
    expect(navigate(open, { type: "pop" })).toEqual(over);
  });

  test("Settings is never pushed twice", () => {
    const open = navigate(root("today"), { type: "settings" });

    expect(navigate(open, { type: "settings" })).toBe(open);
    expect(navigate(open, { type: "settings" }).stack).toHaveLength(1);
  });

  test("Settings can open at a section", () => {
    expect(navigate(root("practice"), { type: "settings", focus: "day-off" }).stack).toEqual([
      { name: "settings", focus: "day-off" },
    ]);
    expect(navigate(root("today"), { type: "settings", focus: "remind" }).stack).toEqual([
      { name: "settings", focus: "remind" },
    ]);
  });
});
