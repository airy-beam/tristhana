import { FluentBundle, FluentResource } from "@fluent/bundle";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";
import { checkGuide, directivesIn, guideMap, stalePages } from "./check.mjs";
import { guideDirectives } from "./directives.mjs";
import {
  LOCALES,
  LabelError,
  SOURCES,
  createLabels,
  hiddenCommands,
  localeOfPath,
  menuCommands,
} from "./labels.mjs";

/** @type {string} */
let root;
const write = (/** @type {string} */ path, /** @type {string} */ text) => {
  const file = join(root, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text);
  return file;
};
const page = (/** @type {string} */ body, features = "[PR-01]") =>
  `---\ntitle: T\ndescription: D\nfeatures: ${features}\n---\n\n${body}\n`;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "guide-"));
  write("bot/en/bot.ftl", "open = Open the app\nshared = Same\nclash = Bot text\n");
  write("bot/ru/bot.ftl", "open = Открыть приложение\nshared = Одно\nclash = Текст бота\n");
  write(
    "app/en/app.ftl",
    "shared = Same\nclash = App text\ndays = { $n ->\n    [one] { $n } day\n   *[other] { $n } days\n  }\n" +
      "long =\n    line one\n    line two\n",
  );
  write(
    "app/ru/app.ftl",
    "shared = Одно\nclash = Текст приложения\ndays = { $n ->\n    [one] { $n } день\n    [few] { $n } дня\n   *[many] { $n } дней\n  }\n",
  );
});

const labels = () => createLabels({ bot: join(root, "bot"), app: join(root, "app") });

describe("label", () => {
  it("quotes the message in the page's language", () => {
    expect(labels().label("en", "open")).toBe("Open the app");
    expect(labels().label("ru", "open")).toBe("Открыть приложение");
  });

  it("formats arguments, with Russian plurals", () => {
    expect(labels().label("en", "days", { n: "1" })).toBe("1 day");
    expect(labels().label("ru", "days", { n: "3" })).toBe("3 дня");
    expect(labels().label("ru", "days", { n: "5" })).toBe("5 дней");
  });

  it("accepts a key both products share with the same text", () => {
    expect(labels().label("en", "shared")).toBe("Same");
  });

  it("asks for `from` when the bot and the app disagree", () => {
    expect(() => labels().label("en", "clash")).toThrow(/from=bot/);
    expect(labels().label("en", "clash", {}, "app")).toBe("App text");
    expect(labels().label("ru", "clash", {}, "bot")).toBe("Текст бота");
  });

  it.each([
    ["an unknown key", () => labels().label("en", "nope"), /no message "nope"/],
    ["a missing argument", () => labels().label("en", "days"), /"days"/],
    ["a multi-line message", () => labels().label("en", "long"), /multi-line/],
    ["an unknown source", () => labels().label("en", "open", {}, "web"), /from must be/],
    ["an unknown locale", () => labels().label("de", "open"), /unknown locale/],
  ])("refuses %s", (_name, call, message) => {
    expect(call).toThrow(LabelError);
    expect(call).toThrow(message);
  });
});

describe("ariaLabel", () => {
  it("gives the accessible name of an icon-only control, or null without one", () => {
    write("app/en/icons.ftl", "gear = ⚙️\n    .aria-label = Settings\n");
    write("app/ru/icons.ftl", "gear = ⚙️\n    .aria-label = Настройки\n");
    expect(labels().label("en", "gear")).toBe("⚙️");
    expect(labels().ariaLabel("en", "gear")).toBe("Settings");
    expect(labels().ariaLabel("ru", "gear", "app")).toBe("Настройки");
    expect(labels().ariaLabel("en", "open")).toBeNull();
    expect(labels().ariaLabel("en", "gear", "bot")).toBeNull();
    expect(() => labels().ariaLabel("de", "gear")).toThrow(/unknown locale/);
  });
});

describe("the real product files", () => {
  it("name the Mini App's gear, which has no visible words (UI-06)", () => {
    const real = createLabels();
    expect(real.ariaLabel("en", "settings-open", "app")).toBe("Settings");
    expect(real.ariaLabel("ru", "settings-open", "app")).toBeTruthy();
  });

  it("resolve a bot label in both languages", () => {
    const real = createLabels();
    expect(real.label("en", "start-open-app")).toBe("Open the app");
    expect(real.label("ru", "start-open-app")).not.toBe("Open the app");
  });

  it("list the bot's five menu commands, and the hidden ones apart (UI-06)", () => {
    expect(menuCommands()).toEqual(["start", "schedule", "moon", "settings", "help"]);
    expect(hiddenCommands()).toContain("log");
    expect(hiddenCommands()).toContain("menu");
    expect([...menuCommands(), ...hiddenCommands()]).not.toContain("admin");
  });

  it("read each tuple by its own name, and say which one a file lacks", () => {
    const tool = write("tool.py", 'COMMANDS = ("start", "help")\nHIDDEN_COMMANDS = ("log",)\n');
    expect(menuCommands(tool)).toEqual(["start", "help"]);
    expect(hiddenCommands(tool)).toEqual(["log"]);
    const old = write("old.py", 'COMMANDS = ("start",)\n');
    expect(() => hiddenCommands(old)).toThrow(/no HIDDEN_COMMANDS tuple/);
  });

  it("let a guide quote a menu command or a hidden one, never /admin", () => {
    const en = guideDirectives()({ fileURL: pathToFileURL("/s/docs/a.md") });
    const cmd = (/** @type {string} */ value) => ({
      name: "cmd",
      children: [{ type: "text", value }],
    });
    expect(en.textDirective(cmd("moon"))).toEqual({ type: "inlineCode", value: "/moon" });
    expect(en.textDirective(cmd("log"))).toEqual({ type: "inlineCode", value: "/log" });
    expect(() => en.textDirective(cmd("admin"))).toThrow(/a\.md: :cmd\[admin\]/);
  });
});

// UI-06 stage 3: the Mini App's Settings opens on the bot's five rows, in the bot's words. The
// app carries its own copy of these messages (`settings.ftl`), so nothing but this test keeps
// the two files saying the same thing. Each key is read from both products, with every value it
// can take, in both languages.
describe("words in step: the Settings rows read the same in the app and the bot", () => {
  const WEEKDAYS = ["1", "2", "3", "4", "5", "6", "7"];
  const COUNTS = ["1", "2", "3", "5", "21"];
  /** @type {[string, Record<string, string>[]][]} */
  const SHARED = [
    ["settings-language-line", [{ language: "English" }]],
    ["settings-city-line", [{ zone: "Almaty" }]],
    ["settings-city-unset-line", [{ zone: "Almaty (UTC+5)" }]],
    ["settings-city-unlisted-line", [{ zone: "Almaty (UTC+5)" }]],
    ["settings-city-no-zone-line", [{}]],
    ["settings-day-off-line", WEEKDAYS.map((d) => ({ d }))],
    ["settings-days-off-line", WEEKDAYS.flatMap((d) => WEEKDAYS.map((e) => ({ d, e })))],
    ["settings-day-off-none-line", [{}]],
    ["settings-day-off-unset-line", [{}]],
    ["settings-reminders-button", [{}]],
    ["settings-more-button", [{}]],
    ["settings-reminders-title", [{}]],
    ["settings-more-title", [{}]],
    ["settings-quiet-line", COUNTS.map((n) => ({ start: "22:00", end: "07:00", n }))],
    ["settings-quiet-off-line", COUNTS.map((n) => ({ n }))],
  ];

  it("covers the fifteen shared keys", () => {
    expect(new Set(SHARED.map(([key]) => key)).size).toBe(15);
  });

  it.each(SHARED)("%s", (key, cases) => {
    const real = createLabels();
    for (const locale of ["en", "ru"]) {
      for (const args of cases) {
        const bot = real.label(locale, key, args, "bot");
        expect(real.label(locale, key, args, "app"), `${key} (${locale})`).toBe(bot);
        expect(bot).not.toBe("");
      }
    }
  });
});

// UI-06 stage 4B, ADR-0049: a student asks a teacher from the Mini App, and the consent they give
// there is the bot's text. The app carries copies of the bot's messages under the same keys: the
// question, both consent layers and the result lines (`ask.ftl`), and the request lines of both
// sides (`requests.ftl`). Each copy must be the bot's message, byte for byte, so there is one
// consent record (ADR-0045's item table runs on `bot.ftl`). Consent texts are several lines, so
// this reads the bundles itself rather than through `label`, which takes one-line labels only.
describe("words in step: the request and consent messages are the bot's (ADR-0049)", () => {
  const NAMES = [{ name: "Anna" }, { name: "Лена Петрова-Водкина" }];
  const ME = [{ me: " (Ash)" }, { me: "" }];
  const COUNTS = ["1", "2", "3", "5", "21"].map((count) => ({ count }));
  const NONE = [{}];
  /** @type {Record<string, [string, Record<string, string>[]][]>} */
  const COPIED = {
    "ask.ftl": [
      ["request-ask", NONE],
      ["request-ask-one", NAMES],
      ["request-yes", NONE],
      ["request-consent-short", ME],
      ["request-until-yes", NONE],
      ["request-know-them", NONE],
      ["request-consent", ME],
      ["consent-details", NONE],
      ["consent-short-back", NONE],
      ["invite-decline", NONE],
      ["request-asked", NAMES],
      ["request-waiting", NAMES],
      ["request-recent", NAMES],
      ["request-too-many", NONE],
      ["request-full", NONE],
      ["invite-already", NAMES],
    ],
    "requests.ftl": [
      ["request-open", NONE],
      ["request-nobody", NONE],
      ["request-withdrawn", NONE],
      ["request-waiting-line", NAMES],
      ["request-withdraw", NAMES],
      ["request-withdraw-ask", NAMES],
      ["request-withdraw-yes", NONE],
      ["request-waiting-open", COUNTS],
      ["request-list-empty", NONE],
      ["request-list-hint", NONE],
      ["request-yes-mine", NONE],
      ["request-not-mine", NONE],
      ["request-declined", NAMES],
      ["request-undo", NONE],
      ["request-gone", NONE],
      ["request-list-full", NONE],
      ["request-all", COUNTS],
      ["request-all-ask", COUNTS],
      ["request-all-yes", NONE],
      ["request-all-done", COUNTS],
      ["link-student-joined", NAMES],
    ],
  };
  /** The app's own messages in `requests.ftl`: the bot has no such line. `request-withdraw-short`
   * is the app's Withdraw beside a line that already names the teacher; the bot's button keeps
   * `request-withdraw`, with the name. */
  const APP_ONLY = ["request-load-failed", "request-withdraw-short"];

  /** Each message of a raw `.ftl` source, as written (its id line and indented lines). */
  const sources = (/** @type {string} */ text) => {
    /** @type {Record<string, string>} */
    const out = {};
    let current = "";
    for (const line of text.split("\n")) {
      const start = /^([a-z][a-z0-9-]*)\s*=/.exec(line);
      if (start) out[(current = start[1])] = line;
      else if (current && /^\s/.test(line)) out[current] += `\n${line}`;
      else current = "";
    }
    return out;
  };
  const read = (/** @type {string} */ path) => readFileSync(path, "utf8");
  const bot = (/** @type {string} */ locale) => read(join(SOURCES.bot, locale, "bot.ftl"));
  const app = (/** @type {string} */ locale, /** @type {string} */ file) =>
    read(join(SOURCES.app, locale, file));
  const format = (
    /** @type {string} */ text,
    /** @type {string} */ locale,
    /** @type {string} */ key,
    /** @type {Record<string, string>} */ args,
  ) => {
    const bundle = new FluentBundle(locale, { useIsolating: false });
    bundle.addResource(new FluentResource(text));
    const message = bundle.getMessage(key);
    if (!message?.value) throw new Error(`no "${key}" (${locale})`);
    /** @type {Error[]} */
    const errors = [];
    const values = Object.fromEntries(
      Object.entries(args).map(([n, v]) => [n, /^\d+$/.test(v) ? Number(v) : v]),
    );
    const out = bundle.formatPattern(message.value, values, errors);
    if (errors.length) throw new Error(`"${key}" (${locale}): ${errors[0].message}`);
    return out;
  };

  it.each(Object.keys(COPIED))("%s copies every message it has, and only those", (file) => {
    for (const locale of LOCALES) {
      const ids = Object.keys(sources(app(locale, file))).filter((id) => !APP_ONLY.includes(id));
      expect(ids.sort(), `${file} (${locale})`).toEqual(COPIED[file].map(([k]) => k).sort());
    }
  });

  /** @type {[string, string, Record<string, string>[]][]} */
  const EACH = Object.entries(COPIED).flatMap(([file, keys]) =>
    keys.map(([k, c]) => /** @type {[string, string, Record<string, string>[]]} */ ([file, k, c])),
  );
  it.each(EACH)("%s: %s", (file, key, cases) => {
    for (const locale of LOCALES) {
      const theirs = sources(bot(locale))[key];
      const ours = sources(app(locale, file))[key];
      expect(ours, `${key} (${locale}) as written`).toBe(theirs);
      for (const args of cases) {
        const said = format(bot(locale), locale, key, args);
        expect(format(app(locale, file), locale, key, args), `${key} (${locale})`).toBe(said);
        expect(said).not.toBe("");
      }
    }
  });
});

describe("localeOfPath", () => {
  it("is ru only under the ru content folder", () => {
    expect(localeOfPath("/x/src/content/docs/ru/start/a.md")).toBe("ru");
    expect(localeOfPath("/x/src/content/docs/start/ru.md")).toBe("en");
  });
});

describe("guideDirectives", () => {
  const visitor = (/** @type {string} */ path) =>
    guideDirectives({ labels: labels(), commands: ["log"] })({ fileURL: pathToFileURL(path) });
  const ftl = (/** @type {string} */ key, attributes = {}) => ({
    name: "ftl",
    attributes,
    children: [{ type: "text", value: key }],
  });

  it("turns :ftl into the bold label of the page's language", () => {
    expect(visitor("/s/docs/ru/a.md").textDirective(ftl("open"))).toEqual({
      type: "strong",
      children: [{ type: "text", value: "Открыть приложение" }],
    });
  });

  it("passes arguments and `from`", () => {
    const en = visitor("/s/docs/a.md");
    expect(en.textDirective(ftl("days", { n: "2" })).children[0].value).toBe("2 days");
    expect(en.textDirective(ftl("clash", { from: "bot" })).children[0].value).toBe("Bot text");
  });

  it("turns :cmd into the command as code", () => {
    const node = { name: "cmd", children: [{ type: "text", value: "log" }] };
    expect(visitor("/s/docs/a.md").textDirective(node)).toEqual({
      type: "inlineCode",
      value: "/log",
    });
  });

  it("fails with the file name on an unknown key or command", () => {
    const en = visitor("/s/docs/a.md");
    expect(() => en.textDirective(ftl("nope"))).toThrow(/a\.md: no message "nope"/);
    const admin = { name: "cmd", children: [{ type: "text", value: "admin" }] };
    expect(() => en.textDirective(admin)).toThrow(/a\.md: :cmd\[admin\]/);
  });

  it("leaves other directives alone", () => {
    expect(visitor("/s/docs/a.md").textDirective({ name: "badge", children: [] })).toBeUndefined();
  });
});

describe("checkGuide", () => {
  const run = () =>
    checkGuide({ docsDir: join(root, "docs"), label: labels().label, commands: ["log"] });
  const pair = (/** @type {string} */ en, /** @type {string} */ ru) => {
    write("docs/a/one.md", en);
    write("docs/ru/a/one.md", ru);
  };

  it("passes a matching pair that documents every command", () => {
    pair(page("## H\n:cmd[log] :ftl[open]"), page("## З\n:cmd[log] :ftl[open]"));
    expect(run()).toEqual([]);
  });

  it("reports a page with no twin, in either direction", () => {
    write("docs/a/one.md", page(":cmd[log]"));
    write("docs/ru/a/two.md", page(":cmd[log]"));
    expect(run()).toEqual([
      expect.stringMatching(/a\/one\.md: no Russian page/),
      expect.stringMatching(/two\.md: no English page/),
    ]);
  });

  it("reports twins that drifted apart", () => {
    pair(
      page("## H\n## H2\n:cmd[log] :ftl[open]\n![](../shots/en/home.webp)", "[PR-01, PR-02]"),
      page("## З\n:cmd[log]\n![](../shots/ru/log.webp)"),
    );
    expect(run()).toEqual([
      expect.stringMatching(/features differ/),
      expect.stringMatching(/number of headings differ/),
      expect.stringMatching(/screenshots differ/),
      expect.stringMatching(/quoted labels and commands differ/),
    ]);
  });

  it("reports unknown labels and commands with the file", () => {
    pair(page(":cmd[log] :cmd[admin] :ftl[nope]"), page(":cmd[log] :cmd[admin] :ftl[nope]"));
    const problems = run();
    expect(problems).toContainEqual(expect.stringMatching(/a\/one\.md: :cmd\[admin\]/));
    expect(problems).toContainEqual(expect.stringMatching(/ru\/a\/one\.md: no message "nope"/));
  });

  it("reports a menu command no page mentions", () => {
    pair(page("text"), page("текст"));
    expect(run()).toEqual(["/log is in the bot's menu but in no guide"]);
  });

  it("lets a page quote a hidden command, and asks no page to document it", () => {
    const hidden = () =>
      checkGuide({
        docsDir: join(root, "docs"),
        label: labels().label,
        commands: ["log"],
        hidden: ["menu"],
      });
    pair(page(":cmd[log] :cmd[menu]"), page(":cmd[log] :cmd[menu]"));
    expect(hidden()).toEqual([]);
    pair(page(":cmd[log]"), page(":cmd[log]"));
    expect(hidden()).toEqual([]);
    pair(page(":cmd[log] :cmd[admin]"), page(":cmd[log] :cmd[admin]"));
    expect(hidden()).toEqual([
      expect.stringMatching(/a\/one\.md: :cmd\[admin\] is not one of the bot's commands/),
      expect.stringMatching(/ru\/a\/one\.md: :cmd\[admin\]/),
    ]);
  });

  it("reports missing or malformed front matter", () => {
    pair(
      "---\ntitle: T\n---\n:cmd[log]\n",
      "---\ndescription: D\nfeatures: [oops]\n---\n:cmd[log]\n",
    );
    const problems = run();
    expect(problems).toContainEqual(expect.stringMatching(/one\.md: no "features"/));
    expect(problems).toContainEqual(expect.stringMatching(/one\.md: no description/));
    expect(problems).toContainEqual(expect.stringMatching(/"oops" is not a feature ID/));
    expect(problems).toContainEqual(expect.stringMatching(/ru\/a\/one\.md: no title/));
  });
});

describe("directivesIn", () => {
  it("reads keys and quoted or bare arguments", () => {
    expect(directivesIn(':ftl[day]{rel=today from="app"} and :cmd[log]')).toEqual([
      { name: "ftl", key: "day", args: { rel: "today", from: "app" } },
      { name: "cmd", key: "log", args: {} },
    ]);
  });
});

describe("guideMap", () => {
  it("maps each feature to its English page slugs", () => {
    write("docs/a/one.md", page("x", "[PR-02, PR-01]"));
    write("docs/b.mdx", page("x", "[PR-01]"));
    write("docs/ru/a/one.md", page("x", "[ZZ-99]"));
    expect(guideMap(join(root, "docs"))).toEqual({ "PR-01": ["a/one", "b"], "PR-02": ["a/one"] });
  });
});

describe("stalePages", () => {
  const map = {
    "PR-01": ["students/log-practice"],
    "SC-05": ["staff/attendance", "students/my-shala"],
  };
  const times = (
    /** @type {Record<string, number>} */ pages,
    /** @type {Record<string, number>} */ specs,
  ) => ({
    pageTime: (/** @type {string} */ slug) => pages[slug] ?? null,
    specTime: (/** @type {string} */ id) => specs[id] ?? null,
  });

  it("names the pages whose feature spec changed after the page did", () => {
    const pages = { "students/log-practice": 50, "staff/attendance": 10, "students/my-shala": 30 };
    expect(stalePages(map, times(pages, { "PR-01": 40, "SC-05": 20 }))).toEqual([
      { slug: "staff/attendance", features: ["SC-05"] },
    ]);
  });

  it("says nothing about a feature without a spec or a page git has not seen", () => {
    expect(stalePages(map, times({ "staff/attendance": 10 }, { "PR-01": 99 }))).toEqual([]);
    expect(stalePages(map, times({}, { "SC-05": 99 }))).toEqual([]);
  });
});
