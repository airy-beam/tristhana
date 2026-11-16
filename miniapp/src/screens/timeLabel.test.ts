import { offsetShown, offsetText, timeLabel, zoneCity, zoneLabel } from "./timeLabel";

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
