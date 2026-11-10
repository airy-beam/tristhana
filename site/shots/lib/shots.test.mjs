import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";
import { checkGuide } from "../../src/lib/check.mjs";
import { botHtml } from "./bot-html.mjs";
import { CAST, dayBefore, demoDay, todayIn } from "./cast.mjs";
import { DemoError, createClient } from "./client.mjs";
import { parseManifest, select } from "./manifest.mjs";
import { seedCast } from "./seed.mjs";

describe("manifest", () => {
  const ok = "shots:\n  - {name: a-b, kind: bot, as: student, say: /log, features: [PR-01]}\n";

  it("reads a valid list", () => {
    expect(parseManifest(ok)).toEqual([
      { name: "a-b", kind: "bot", as: "student", say: "/log", features: ["PR-01"] },
    ]);
  });

  it.each([
    ["no list", "shots: 1", /no `shots` list/],
    ["a bad name", "shots: [{name: A b}]", /lower-case/],
    ["a duplicate", ok + ok.split("\n")[1] + "\n", /listed twice/],
    ["an unknown key", ok.replace("say:", "sya: x, say:"), /unknown key "sya"/],
    ["a bad kind", ok.replace("bot", "web"), /kind is app or bot/],
    ["a bad role", ok.replace("student", "admin"), /as is one of/],
    ["no features", ok.replace("[PR-01]", "[]"), /needs features/],
    ["a bot shot without say", ok.replace("say: /log, ", ""), /needs say/],
    ["an app shot that says", ok.replace("bot", "app"), /say and tap are for bot/],
    [
      "a bot shot that clicks",
      ok.replace("say:", "click: [x], say:"),
      /click and full are for app/,
    ],
  ])("refuses %s", (_name, text, message) => {
    expect(() => parseManifest(text)).toThrow(message);
  });

  it("selects by name or feature, and refuses an unknown value", () => {
    const shots = parseManifest(
      "shots:\n  - {name: a, kind: app, as: student, features: [PR-01]}\n  - {name: b, kind: app, as: teacher, features: [ST-06, PR-01]}\n",
    );
    expect(select(shots, [])).toHaveLength(2);
    expect(select(shots, ["ST-06"]).map((s) => s.name)).toEqual(["b"]);
    expect(select(shots, ["PR-01"]).map((s) => s.name)).toEqual(["a", "b"]);
    expect(select(shots, ["a"]).map((s) => s.name)).toEqual(["a"]);
    expect(() => select(shots, ["a", "ZZ-99"])).toThrow(/ZZ-99/);
  });
});

describe("botHtml", () => {
  it("draws the text, the buttons row by row and what the person said", () => {
    const html = botHtml(
      {
        method: "sendMessage",
        text: "Hi\n/log it",
        reply_markup: { inline_keyboard: [[{ text: "A" }, { text: "B" }], [{ text: "C" }]] },
      },
      { said: "/start", lang: "ru" },
    );
    expect(html).toContain('<html lang="ru">');
    expect(html).toContain('<div class="said">/start</div>');
    expect(html).toContain('Hi\n<span class="link">/log</span> it');
    expect(html.match(/class="row"/g)).toHaveLength(2);
    expect(html.match(/class="button"/g)).toHaveLength(3);
  });

  it("escapes markup, keeping only Telegram's simple tags", () => {
    const html = botHtml({
      method: "sendMessage",
      text: '<b>Bold</b> <script>x</script> <a href="https://e.x/?a=1">link</a>',
      reply_markup: { inline_keyboard: [[{ text: "<i>" }]] },
    });
    expect(html).toContain("<b>Bold</b>");
    expect(html).toContain("&lt;script&gt;x&lt;/script&gt;");
    expect(html).toContain('<span class="link">link</span>');
    expect(html).not.toContain("https://e.x");
    expect(html).toContain('<span class="button">&lt;i&gt;</span>');
  });

  it("draws a message with no buttons", () => {
    expect(botHtml({ method: "sendMessage", text: "Hi" })).not.toContain('keyboard"');
  });
});

describe("the demo cast", () => {
  it("has the same roles in both languages, with distinct made-up ids", () => {
    expect(Object.keys(CAST.en)).toEqual(Object.keys(CAST.ru));
    const ids = [...Object.values(CAST.en), ...Object.values(CAST.ru)].map((user) => user.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const user of Object.values(CAST.ru)) expect(user.lang).toBe("ru");
  });

  it("counts days back across a month and a year", () => {
    expect(dayBefore("2026-03-01", 1)).toBe("2026-02-28");
    expect(dayBefore("2026-01-01", 1)).toBe("2025-12-31");
    expect(dayBefore("2026-11-11", 0)).toBe("2026-11-11");
  });

  it("takes today from the demo city, not from the machine", () => {
    const lateUtc = new Date("2026-11-10T20:30:00Z"); // already the 11th in Almaty (UTC+5)
    expect(todayIn("Asia/Almaty", lateUtc)).toBe("2026-11-11");
    expect(todayIn("UTC", lateUtc)).toBe("2026-11-10");
  });

  it("rests on Saturdays and moon days, and practises otherwise", () => {
    expect(demoDay("2026-11-07", 4)).toEqual({ status: "rest" }); // a Saturday
    expect(demoDay("2026-11-10", 1, new Set(["2026-11-10"]))).toEqual({ status: "moon" });
    expect(demoDay("2026-11-10", 1)).toMatchObject({
      status: "practiced",
      practice: { context: "mysore", duration_min: 90, length: { series: ["primary"] } },
    });
    expect(demoDay("2026-11-08", 3).practice?.context).toBe("self"); // a Sunday
    expect(demoDay("2026-11-06", 5).practice?.context).toBe("led"); // a Friday
  });

  it("practised half Primary earlier on", () => {
    expect(demoDay("2026-09-01", 71).practice?.length).toEqual({
      series: ["primary"],
      end: "navasana",
    });
  });

  it("is the same on every run", () => {
    expect(demoDay("2026-10-01", 41)).toEqual(demoDay("2026-10-01", 41));
  });
});

/** A fake backend: records calls and answers from `routes`. */
function fakeFetch(/** @type {Record<string, (init: any) => unknown>} */ routes) {
  /** @type {{ url: string, init: any }[]} */
  const calls = [];
  const fetchFn = async (/** @type {any} */ url, /** @type {any} */ init = {}) => {
    calls.push({ url: String(url), init });
    const path = new URL(String(url)).pathname;
    const route = routes[`${init.method ?? "GET"} ${path}`] ?? routes[path];
    if (!route) return new Response("nope", { status: 404 });
    const body = route(init);
    return body === null
      ? new Response(null, { status: 204 })
      : new Response(typeof body === "string" ? body : JSON.stringify(body), { status: 200 });
  };
  return { fetchFn: /** @type {typeof fetch} */ (/** @type {unknown} */ (fetchFn)), calls };
}

describe("client", () => {
  const maya = CAST.en.student;
  const sign = { "/dev/telegram-init-data": () => ({ init_data: "signed" }) };

  it("signs in once per person and sends the initData with every call", async () => {
    const { fetchFn, calls } = fakeFetch({ ...sign, "PUT /api/v1/me/day-off": () => null });
    const client = createClient({ api: "http://x", secret: "s", fetch: fetchFn });
    await client.call(maya, "PUT", "/me/day-off", { day_off: [6] });
    await client.call(maya, "PUT", "/me/day-off", { day_off: [6] });
    expect(calls.filter((c) => c.url.includes("/dev/"))).toHaveLength(1);
    expect(calls[0].url).toContain("user_id=9001");
    expect(calls[0].url).toContain("first_name=Maya");
    expect(calls[1].init.headers.Authorization).toBe("tma signed");
    expect(JSON.parse(calls[1].init.body)).toEqual({ day_off: [6] });
  });

  it("fails loudly on an error answer and when dev sign-in is off", async () => {
    const off = createClient({ api: "http://x", secret: "s", fetch: fakeFetch({}).fetchFn });
    await expect(off.call(maya, "GET", "/me")).rejects.toThrow(/dev sign-in is off \(404\)/);
    const on = createClient({ api: "http://x", secret: "s", fetch: fakeFetch(sign).fetchFn });
    await expect(on.call(maya, "GET", "/me")).rejects.toThrow(DemoError);
  });

  it("sends a command as a Telegram message with the secret header", async () => {
    const { fetchFn, calls } = fakeFetch({
      "POST /telegram/webhook": () => ({ method: "sendMessage", text: "Namaste" }),
    });
    const client = createClient({ api: "http://x", secret: "s3", fetch: fetchFn });
    expect((await client.say(maya, "/start t_abc")).text).toBe("Namaste");
    const sent = JSON.parse(calls[0].init.body);
    expect(calls[0].init.headers["X-Telegram-Bot-Api-Secret-Token"]).toBe("s3");
    expect(sent.message.text).toBe("/start t_abc");
    expect(sent.message.entities).toEqual([{ type: "bot_command", offset: 0, length: 6 }]);
    expect(sent.message.from).toMatchObject({ id: 9001, language_code: "en" });
  });

  it("taps a button by its label, and says which buttons exist when it is missing", async () => {
    const { fetchFn, calls } = fakeFetch({
      "POST /telegram/webhook": () => ({ method: "editMessageText", text: "Saved" }),
    });
    const client = createClient({ api: "http://x", secret: "s", fetch: fetchFn });
    const reply = {
      method: "sendMessage",
      text: "?",
      reply_markup: {
        inline_keyboard: [
          [
            { text: "🧘 Practiced", callback_data: "d1:p" },
            { text: "Open", url: "u" },
          ],
        ],
      },
    };
    await client.tap(maya, reply, "Practiced");
    expect(JSON.parse(calls[0].init.body).callback_query.data).toBe("d1:p");
    expect(() => client.tap(maya, reply, "Rest")).toThrow(
      /no button "Rest" among: 🧘 Practiced · Open/,
    );
    expect(() => client.tap(maya, reply, "Open")).toThrow(DemoError); // a link, not a tap
  });

  it("fails when the bot gives no reply", async () => {
    const { fetchFn } = fakeFetch({ "POST /telegram/webhook": () => "" });
    const client = createClient({ api: "http://x", secret: "s", fetch: fetchFn });
    await expect(client.say(maya, "hello")).rejects.toThrow(/no reply/);
  });
});

describe("seedCast", () => {
  it("sets the city, logs 91 days around moon days and links the teacher through the bot", async () => {
    /** @type {string[]} */
    const done = [];
    const client = {
      call: async (
        /** @type {any} */ user,
        /** @type {string} */ method,
        /** @type {string} */ path,
        /** @type {any} */ body,
      ) => {
        done.push(
          `${user.name} ${method} ${path.split("?")[0]}${body?.status ? ` ${body.status}` : ""}`,
        );
        if (path.startsWith("/me/moon-days")) return { days: [{ date: "2026-11-10" }] };
        if (path === "/me/invite") return { url: "https://t.me/tristhana_bot?start=t_abc123" };
        if (path === "/me/links") return { teachers: [{}] };
        return null;
      },
      say: async (/** @type {any} */ user, /** @type {string} */ text) => {
        done.push(`${user.name} says ${text}`);
        return { method: "sendMessage", text: "Confirm?" };
      },
      tap: async (
        /** @type {any} */ user,
        /** @type {any} */ _reply,
        /** @type {string} */ label,
      ) => {
        done.push(`${user.name} taps ${label}`);
        return { method: "editMessageText" };
      },
    };
    await seedCast(/** @type {any} */ (client), "en", { today: "2026-11-11" });
    expect(done.slice(0, 5)).toEqual([
      "Maya POST /me/device-timezone",
      "Maya PATCH /me",
      "Arjun POST /me/device-timezone",
      "Arjun PATCH /me",
      "Maya PUT /me/day-off",
    ]);
    expect(done.filter((line) => /PUT \/me\/days\/[\d-]+ /.test(line))).toHaveLength(91);
    expect(done).toContain("Maya PUT /me/days/2026-11-10 moon");
    expect(done).toContain("Maya PUT /me/days/2026-11-11 practiced");
    expect(done).toContain("Maya PUT /me/days/2026-11-11/practices/1");
    expect(done.slice(-3)).toEqual([
      "Maya says /start t_abc123",
      "Maya taps ✅",
      "Maya GET /me/links",
    ]);
  });

  const stub = (/** @type {{ date: string }[]} */ days) => ({
    call: async (/** @type {any} */ _u, /** @type {string} */ _m, /** @type {string} */ path) => {
      if (path.startsWith("/me/moon-days")) return { days };
      if (path === "/me/invite") return { url: "https://t.me/x?start=t_a" };
      if (path === "/me/links") return { teachers: [] };
      return null;
    },
    say: async () => ({ method: "sendMessage" }),
    tap: async () => ({ method: "editMessageText" }),
  });
  const seed = (/** @type {{ date: string }[]} */ days) =>
    seedCast(/** @type {any} */ (stub(days)), "ru", { today: "2026-11-11" });

  it("stops when the link was not made", async () => {
    await expect(seed([{ date: "2026-11-10" }])).rejects.toThrow(/teacher link was not made/);
  });

  it("stops when the demo world has no moon days (the first tick did not run)", async () => {
    await expect(seed([])).rejects.toThrow(/no moon days/);
  });
});

describe("checkGuide with screenshots", () => {
  function site(/** @type {Record<string, string>} */ files) {
    const root = mkdtempSync(join(tmpdir(), "guide-shots-"));
    for (const [path, text] of Object.entries(files)) {
      mkdirSync(dirname(join(root, path)), { recursive: true });
      writeFileSync(join(root, path), text);
    }
    return root;
  }
  const page = (/** @type {string} */ body) =>
    `---\ntitle: T\ndescription: D\nfeatures: [PR-01]\n---\n\n${body}\n`;
  const run = (/** @type {string} */ root, /** @type {string[]} */ names) =>
    checkGuide({
      docsDir: join(root, "docs"),
      label: () => "x",
      commands: [],
      shots: { names, dir: join(root, "shots") },
    });

  it("passes when every shot is listed, used and present in both languages", () => {
    const root = site({
      "docs/a.md": page("![](../shots/en/home.webp)"),
      "docs/ru/a.md": page("![](../../shots/ru/home.webp)"),
      "shots/en/home.webp": "",
      "shots/ru/home.webp": "",
    });
    expect(run(root, ["home"])).toEqual([]);
  });

  it("reports an unlisted shot, a wrong-language shot, an unused one and a missing file", () => {
    const root = site({
      "docs/a.md": page("![](../shots/en/home.webp) ![](../shots/en/old.webp)"),
      "docs/ru/a.md": page("![](../../shots/en/home.webp) ![](../../shots/ru/old.webp)"),
      "shots/en/home.webp": "",
    });
    const problems = run(root, ["home", "spare"]);
    expect(problems).toContainEqual(expect.stringMatching(/a\.md: screenshot "old" is not in/));
    expect(problems).toContainEqual(
      expect.stringMatching(/ru\/a\.md: shows the en screenshot "home"/),
    );
    expect(problems).toContainEqual('screenshot "spare" is in the manifest but on no page');
    expect(problems).toContainEqual(expect.stringMatching(/ru\/home\.webp is missing/));
  });
});
