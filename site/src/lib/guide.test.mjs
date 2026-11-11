import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";
import { checkGuide, directivesIn, guideMap, stalePages } from "./check.mjs";
import { guideDirectives } from "./directives.mjs";
import { LabelError, createLabels, localeOfPath, menuCommands } from "./labels.mjs";

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

describe("the real product files", () => {
  it("resolve a bot label in both languages", () => {
    const real = createLabels();
    expect(real.label("en", "start-open-app")).toBe("Open the app");
    expect(real.label("ru", "start-open-app")).not.toBe("Open the app");
  });

  it("list the bot's menu commands, without /admin", () => {
    expect(menuCommands()).toContain("log");
    expect(menuCommands()).not.toContain("admin");
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
