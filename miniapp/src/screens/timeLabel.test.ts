import { ZONE_ALIASES, offsetShown, offsetText, timeLabel, zoneCity, zoneLabel } from "./timeLabel";

// ADR-0044: a displayed time always names its place; the UTC offset shows only outside the
// viewer's own IANA zone. The cases of `backend/tests/domain/test_time_label.py`, one for one.

const DAY = "2026-11-16";
const AT = "07:00";

describe("offsetShown", () => {
  it("no offset in the viewer's own zone", () => {
    expect(offsetShown("Asia/Almaty", "Asia/Almaty")).toBe(false);
  });

  it("another zone shows the offset", () => {
    expect(offsetShown("Europe/Berlin", "Asia/Almaty")).toBe(true);
  });

  it("another zone with the same offset still shows it", () => {
    // Names are compared, not clocks: Almaty and Tashkent are both UTC+5 today.
    expect(offsetText("Asia/Almaty", DAY, AT)).toBe(offsetText("Asia/Tashkent", DAY, AT));
    expect(offsetShown("Asia/Tashkent", "Asia/Almaty")).toBe(true);
  });

  it.each([null, undefined])("an unknown viewer zone (%s) shows the offset", (viewer) => {
    expect(offsetShown("Asia/Almaty", viewer)).toBe(true);
  });

  it.each([null, "UTC", "Asia/Almaty"])("UTC never gets an offset (viewer %s)", (viewer) => {
    // `07:00 UTC` already says it.
    expect(offsetShown("UTC", viewer)).toBe(false);
  });

  it("a UTC viewer sees the offset of a place", () => {
    expect(offsetShown("Asia/Almaty", "UTC")).toBe(true);
  });
});

describe("offsetText", () => {
  it.each([
    ["Asia/Almaty", DAY, "UTC+5"],
    ["Asia/Kolkata", DAY, "UTC+5:30"], // a half-hour zone
    ["Asia/Kathmandu", DAY, "UTC+5:45"],
    ["America/New_York", "2026-01-15", "UTC-5"],
    ["America/St_Johns", "2026-01-15", "UTC-3:30"],
    ["Europe/London", "2026-01-15", "UTC+0"],
    ["Europe/Berlin", "2026-03-28", "UTC+1"], // the day before the change
    ["Europe/Berlin", "2026-03-29", "UTC+2"], // 07:00 on the daylight-saving date
    ["Europe/Berlin", "2026-10-25", "UTC+1"],
  ])("the offset is the one on that date: %s on %s is %s", (zone, day, text) => {
    expect(offsetText(zone, day, AT)).toBe(text);
  });

  it("the offset is the one at that time on a change night", () => {
    const change = "2026-03-29"; // Berlin: 02:00 → 03:00

    expect(offsetText("Europe/Berlin", change, "01:30")).toBe("UTC+1");
    expect(offsetText("Europe/Berlin", change, "03:30")).toBe("UTC+2");
  });

  it("the same on the night the clocks go back", () => {
    const change = "2026-10-25"; // Berlin: 03:00 → 02:00

    expect(offsetText("Europe/Berlin", change, "01:30")).toBe("UTC+2");
    expect(offsetText("Europe/Berlin", change, "03:30")).toBe("UTC+1");
  });

  it("an hour that repeats or never happens takes the earlier offset, as zoneinfo does", () => {
    expect(offsetText("Europe/Berlin", "2026-03-29", "02:30")).toBe("UTC+1"); // skipped
    expect(offsetText("Europe/Berlin", "2026-10-25", "02:30")).toBe("UTC+2"); // repeated
  });

  it("west of UTC and far east of it, on a change night too", () => {
    // New York: 02:00 → 03:00 on 8 March 2026. Kiritimati: UTC+14, the far end.
    expect(offsetText("America/New_York", "2026-03-08", "01:30")).toBe("UTC-5");
    expect(offsetText("America/New_York", "2026-03-08", "03:30")).toBe("UTC-4");
    expect(offsetText("Pacific/Kiritimati", DAY, "00:30")).toBe("UTC+14");
  });

  it("reads a time with seconds as the same wall clock", () => {
    expect(offsetText("Europe/Berlin", "2026-03-29", "03:30:00")).toBe("UTC+2");
  });

  it.each(["2026-03-28", "2026-03-29", "2026-07-01"])(
    "the answer never flips on a daylight-saving date (%s)",
    (day) => {
      // Berlin and Paris always share a clock: still different zones. The rule takes no date.
      expect(offsetShown("Europe/Berlin", "Europe/Berlin")).toBe(false);
      expect(offsetShown("Europe/Paris", "Europe/Berlin")).toBe(true);
      expect(offsetText("Europe/Paris", day, AT)).toBe(offsetText("Europe/Berlin", day, AT));
    },
  );
});

// One zone, two names: what Chrome and Android's WebView still report (CLDR's ids), and IANA's
// own name (the seeded cities, Firefox). The same table as in `test_time_label.py`.
const ALIASES: [alias: string, name: string][] = [
  ["Africa/Asmera", "Africa/Asmara"],
  ["America/Buenos_Aires", "America/Argentina/Buenos_Aires"],
  ["America/Catamarca", "America/Argentina/Catamarca"],
  ["America/Cordoba", "America/Argentina/Cordoba"],
  ["America/Jujuy", "America/Argentina/Jujuy"],
  ["America/Mendoza", "America/Argentina/Mendoza"],
  ["America/Coral_Harbour", "America/Atikokan"],
  ["America/Godthab", "America/Nuuk"],
  ["America/Indianapolis", "America/Indiana/Indianapolis"],
  ["America/Louisville", "America/Kentucky/Louisville"],
  ["Asia/Calcutta", "Asia/Kolkata"],
  ["Asia/Katmandu", "Asia/Kathmandu"],
  ["Asia/Rangoon", "Asia/Yangon"],
  ["Asia/Saigon", "Asia/Ho_Chi_Minh"],
  ["Atlantic/Faeroe", "Atlantic/Faroe"],
  ["Europe/Kiev", "Europe/Kyiv"],
  ["Pacific/Enderbury", "Pacific/Kanton"],
  ["Pacific/Ponape", "Pacific/Pohnpei"],
  ["Pacific/Truk", "Pacific/Chuuk"],
];

describe("zone aliases", () => {
  it.each(ALIASES)("two names of one zone are the viewer's own zone: %s, %s", (alias, name) => {
    // A person in Mysuru whose phone says `Asia/Calcutta` reads `07:00 Mysuru`, no offset.
    expect(offsetShown(name, alias)).toBe(false);
    expect(offsetShown(alias, name)).toBe(false);
    expect(offsetShown(alias, alias)).toBe(false);
  });

  it("the alias table is exactly this one", () => {
    // The twin's test holds the same list: a name added on one side fails on the other.
    expect(ZONE_ALIASES).toEqual(Object.fromEntries(ALIASES));
    const names = new Set(Object.values(ZONE_ALIASES));
    expect(Object.keys(ZONE_ALIASES).filter((alias) => names.has(alias))).toEqual([]); // no chains
  });

  it.each([ALIASES[10], ALIASES[15]] as [string, string][])(
    "both names keep the same clock: %s, %s",
    (alias, name) => {
      expect(offsetText(alias, DAY, AT)).toBe(offsetText(name, DAY, AT));
    },
  );

  it("an alias is still another zone for everyone else", () => {
    // Kolkata and Colombo share a clock: still two zones, under either name.
    expect(offsetShown("Asia/Calcutta", "Asia/Colombo")).toBe(true);
    expect(offsetShown("Asia/Colombo", "Asia/Calcutta")).toBe(true);
    expect(offsetShown("Europe/Kiev", "Europe/Berlin")).toBe(true);
    expect(offsetShown("Asia/Calcutta", null)).toBe(true);
  });

  it("the label of a time in my own zone has no offset under either name", () => {
    expect(timeLabel(AT, "Asia/Kolkata", DAY, { place: "Mysuru", viewer: "Asia/Calcutta" })).toBe(
      "07:00 Mysuru",
    );
    expect(zoneLabel("Europe/Kyiv", DAY, { viewer: "Europe/Kiev" })).toBe("Kyiv");
  });
});

describe("zoneLabel", () => {
  it.each([
    ["Asia/Almaty", "Almaty (UTC+5)"],
    ["Asia/Kolkata", "Kolkata (UTC+5:30)"],
    ["America/New_York", "New York (UTC-4)"],
    ["UTC", "UTC"],
  ])("without a viewer the offset shows: %s -> %s", (zone, label) => {
    expect(zoneLabel(zone, "2026-10-19")).toBe(label);
  });

  it("only the place in the viewer's own zone", () => {
    expect(zoneLabel("Asia/Almaty", DAY, { viewer: "Asia/Almaty" })).toBe("Almaty");
    expect(zoneLabel("Asia/Tashkent", DAY, { viewer: "Asia/Almaty" })).toBe("Tashkent (UTC+5)");
    expect(zoneLabel("Asia/Almaty", DAY, { viewer: null })).toBe("Almaty (UTC+5)");
  });

  it("London in winter is UTC+0, not a bare UTC", () => {
    expect(zoneLabel("Europe/London", "2026-01-15")).toBe("London (UTC+0)");
  });

  it("names the home city when it is given (MD-04)", () => {
    const place = "Astana";

    expect(zoneLabel("Asia/Almaty", DAY, { at: "06:30", place })).toBe("Astana (UTC+5)");
    expect(zoneLabel("Asia/Almaty", DAY, { place, viewer: "Asia/Almaty" })).toBe("Astana");
  });

  it("the offset is the one at the labelled time", () => {
    expect(zoneLabel("Europe/Berlin", "2026-03-29", { at: "01:30" })).toBe("Berlin (UTC+1)");
    expect(zoneLabel("Europe/Berlin", "2026-03-29", { at: "03:30" })).toBe("Berlin (UTC+2)");
  });
});

describe("timeLabel", () => {
  it("a time always names its place", () => {
    expect(timeLabel(AT, "Asia/Almaty", DAY, { viewer: "Asia/Almaty" })).toBe("07:00 Almaty");
    expect(timeLabel("17:30", "Europe/Berlin", DAY, { viewer: "Asia/Almaty" })).toBe(
      "17:30 Berlin (UTC+1)",
    );
    expect(timeLabel(AT, "Asia/Almaty", DAY)).toBe("07:00 Almaty (UTC+5)");
  });

  it("UTC stays `07:00 UTC`", () => {
    expect(timeLabel(AT, "UTC", DAY)).toBe("07:00 UTC");
    expect(timeLabel(AT, "UTC", DAY, { viewer: "Asia/Almaty" })).toBe("07:00 UTC");
  });
});

describe("zoneCity", () => {
  it("is the last part of the IANA name, with spaces", () => {
    expect(zoneCity("America/Argentina/Buenos_Aires")).toBe("Buenos Aires");
    expect(zoneCity("UTC")).toBe("UTC");
  });
});
