// UI-06 stage 5, ADR-0050: one word per thing, in the bot, the Mini App and the guides, in English
// and in Russian. `docs/glossary.yaml` names the words; these tests read it.
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { FluentResource } from "@fluent/bundle";
import { beforeEach, describe, expect, it } from "vitest";
import { LOCALES, SOURCES } from "./labels.mjs";
import {
  DOCS,
  keyIn,
  pageText,
  productUnits,
  readGlossary,
  readable,
  rulesOf,
  sameKeyDifferences,
  wordRegex,
  wordsInGuides,
  wordsInProducts,
} from "./words.mjs";

/** @type {string} */
let root;
const write = (/** @type {string} */ path, /** @type {string} */ text) => {
  const file = join(root, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text);
  return file;
};
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "words-"));
});

const matches = (/** @type {string} */ source, /** @type {string} */ text) =>
  [...text.matchAll(wordRegex(source))].map((m) => m[0]);
const pattern = (/** @type {string} */ ftl) => {
  const [entry] = new FluentResource(ftl).body;
  return entry.value;
};

describe("wordRegex", () => {
  it("matches whole words in any case, in Latin and Cyrillic", () => {
    expect(matches("diar(?:y|ies)", "Saved to your Diary. Diaries.")).toEqual(["Diary", "Diaries"]);
    expect(matches("diar(?:y|ies)", "diaryx, mydiary")).toEqual([]);
    expect(matches("дневник\\p{L}*", "Заметка удалена из дневника.")).toEqual(["дневника"]);
  });

  it("takes «класс» alone, never after a hyphen", () => {
    const klass = "(?<!-)класс(?:а|у|ом|е|ы|ов|ам|ами|ах)?";
    expect(matches(klass, "Лед-класс и майсор-класс")).toEqual([]);
    expect(matches(klass, "Класс в 7:00, на класс")).toEqual(["Класс", "класс"]);
    expect(matches(klass, "классный")).toEqual([]);
  });

  it("takes «серия» only in a run phrase", () => {
    const glossary = readGlossary();
    /** @type {string[]} */
    const banned = glossary.banned.ru;
    const said = (/** @type {string} */ text) =>
      banned.some((source) => wordRegex(source).test(text));
    expect(said("Первая серия целиком")).toBe(false);
    expect(said("7 практик подряд")).toBe(false);
    expect(said("серия дней")).toBe(true);
    expect(said("Не прерви серию")).toBe(true);
    expect(said("7 дней подряд")).toBe(true);
    expect(said("напоминания его пропускают")).toBe(false);
    expect(said("без пропусков")).toBe(true);
  });
});

describe("readable", () => {
  it("gives every variant, with variables removed and spaces collapsed", () => {
    const days = pattern(
      "x = 🌿 { $n ->\n    [one] { $n } практика\n   *[many] { $n } практик\n  } подряд\n",
    );
    expect(readable(days)).toEqual(["🌿 практика подряд", "🌿 практик подряд"]);
    expect(readable(pattern("x = серия из { $n } дней\n"))).toEqual(["серия из дней"]);
    expect(readable(pattern('x = a{""}b { other } c\n'))).toEqual(["ab c"]);
    expect(readable(null)).toEqual([]);
  });

  it("past the limit, reads each variant on its own, never one run into the next", () => {
    // 3 × 3 × 3 × 3 × 3 × 3 = 729 combinations: the sixth select is read variant by variant.
    const select = (/** @type {string} */ v) =>
      `{ $${v} ->\n    [a] ${v}1\n    [b] ${v}2\n   *[c] ${v}3 stop\n  }`;
    const vars = ["p", "q", "r", "s", "t", "u"];
    const texts = readable(pattern(`x = ${vars.map(select).join(" ")} end\n`));
    expect(texts).toContain("u1");
    expect(texts).toContain("u3 stop");
    expect(texts).toContain("p1 q1 r1 s1 t1 end");
    expect(texts.some((t) => /u1 u2|u2 u3/.test(t))).toBe(false);
    expect(texts.some((t) => /stop u/.test(t))).toBe(false);
  });
});

describe("keyIn", () => {
  it("takes exact keys and prefixes", () => {
    expect(keyIn("checkin-clear", ["checkin-*"])).toBe(true);
    expect(keyIn("checkin-clear", ["checkin"])).toBe(false);
    expect(keyIn("diary-clear", ["diary-clear", "x"])).toBe(true);
  });
});

describe("wordsInProducts", () => {
  const glossary = {
    concepts: [
      {
        concept: "Note",
        retired: { en: ["diary"], ru: ["дневник\\p{L}*"] },
        except: [{ key: "kept", reason: "r" }],
      },
      {
        concept: "Link",
        retired: { en: [{ word: "share", in: ["invite-*"] }] },
        except: [{ key: "invite-app", source: "app", reason: "r" }],
      },
      {
        concept: "Commands",
        retired: { en: [{ word: "/moon", guides: false }] },
      },
    ],
    banned: { en: ["streaks?"], ru: [] },
  };
  const scan = () => {
    write(
      "bot/en/bot.ftl",
      "# a diary comment\ndiary-saved = Saved to your diary.\nkept = My diary\n" +
        "status-skipped = { $k ->\n    [streak] Fine\n   *[other] Your streak\n  }\n" +
        "invite-share = 📤 Share\nshare-open = Share\nmoon = Open /moon.\n" +
        "invite-app = Share\n",
    );
    write("bot/ru/bot.ftl", "diary-saved = Сохранено в дневнике.\n");
    write("app/en/app.ftl", "note = 📓 Note\n    .aria-label = Diary\ninvite-app = Share\n");
    write("app/ru/app.ftl", "note = 📓 Заметка\n");
    const units = productUnits({ bot: join(root, "bot"), app: join(root, "app") });
    return wordsInProducts(rulesOf(glossary), units);
  };

  it("names file, key and word; reads values, attributes and every variant", () => {
    expect(scan()).toEqual([
      { file: "app/en/app.ftl", key: "note.aria-label", word: "diary" },
      { file: "bot/en/bot.ftl", key: "diary-saved", word: "diary" },
      { file: "bot/en/bot.ftl", key: "invite-app", word: "share" },
      { file: "bot/en/bot.ftl", key: "invite-share", word: "share" },
      { file: "bot/en/bot.ftl", key: "moon", word: "/moon" },
      { file: "bot/en/bot.ftl", key: "status-skipped", word: "streak" },
      { file: "bot/ru/bot.ftl", key: "diary-saved", word: "дневнике" },
    ]);
  });

  it("never reads ids, comments or variant keys; keeps `in` to its keys and `except` to its source", () => {
    const found = scan().map((o) => `${o.file} ${o.key}`);
    expect(found).not.toContain("bot/en/bot.ftl kept");
    expect(found).not.toContain("bot/en/bot.ftl share-open");
    expect(found).not.toContain("app/en/app.ftl invite-app");
  });
});

describe("pageText and wordsInGuides", () => {
  it("reads titles, descriptions and prose, not directives, code or link targets", () => {
    const text = pageText({
      front: {
        title: "Check-in",
        description: "D",
        hero: { tagline: "T", actions: [{ text: "A" }] },
      },
      body:
        "import { Card } from 'x';\n:ftl[diary-title]{from=app} and :cmd[moon] `diary`\n" +
        "```\ndiary\n```\n[the diary page](../diary-and-more/) ![alt](../shots/diary.webp)\n" +
        '<LinkCard title="Hello" href="/diary/" />\n<!-- diary -->\nhttps://x.app/diary\n',
    });
    expect(text).toContain("Check-in");
    expect(text).toContain("the diary page");
    expect(text).toContain("Hello");
    expect(text.match(/diary/g)).toEqual(["diary"]);
  });

  it("scans each page in its own language, with the rules that apply to guides", () => {
    write("docs/a.md", "---\ntitle: My diary\ndescription: D\n---\nOpen /moon. Share.\n");
    write("docs/ru/a.md", "---\ntitle: Дневник\ndescription: Д\n---\nМой diary.\n");
    const rules = rulesOf({
      concepts: [
        { concept: "Note", retired: { en: ["diary"], ru: ["дневник\\p{L}*"] } },
        { concept: "Cmd", retired: { en: [{ word: "/moon", guides: false }] } },
        { concept: "Link", retired: { en: [{ word: "share", in: ["invite-*"] }] } },
      ],
    });
    expect(wordsInGuides(rules, join(root, "docs"))).toEqual([
      { file: "guides/a.md", word: "diary" },
      { file: "guides/ru/a.md", word: "дневник" },
    ]);
  });
});

describe("sameKeyDifferences", () => {
  it("finds a shared key that reads differently for some value, per language", () => {
    write("bot/en/bot.ftl", "same = Same { $name }\ndays = { $n } days\nclash = Bot\n");
    write(
      "app/en/app.ftl",
      "same = Same { $name }\ndays = { $n ->\n    [one] { $n } day\n   *[other] { $n } days\n  }\n" +
        "clash = App\nonly = App only\n",
    );
    write("bot/ru/bot.ftl", "same = Одно\n");
    write("app/ru/app.ftl", "same = Одно\n");
    expect(sameKeyDifferences({ bot: join(root, "bot"), app: join(root, "app") })).toEqual([
      { key: "clash", locale: "en", args: {}, bot: "Bot", app: "App" },
      { key: "days", locale: "en", args: { n: 1 }, bot: "1 days", app: "1 day" },
    ]);
  });
});

// The real files. Today's offenders wait in `pending` (slice 1); slices 2–4 work through them, and
// each entry that no longer matches must go, so the list only shrinks.
describe("one word per thing (ADR-0050)", () => {
  const glossary = readGlossary();
  const rules = rulesOf(glossary);
  const units = productUnits();
  const pending = glossary.pending ?? {};
  const show = (/** @type {{ file: string, key?: string, word: string }} */ o) =>
    `${o.file}${o.key ? ` ${o.key}` : ""}: "${o.word}"`;
  const waiting = new Set((pending.words ?? []).map(show));

  it("describes every concept, with a reason for every exception", () => {
    for (const concept of glossary.concepts) {
      for (const field of ["concept", "en", "ru", "where"]) {
        expect(concept[field], `${concept.concept}: ${field}`).toBeTruthy();
      }
    }
    const keys = new Set(units.map((u) => u.key.split(".")[0]));
    const excepts = [
      ...glossary.concepts.flatMap((/** @type {any} */ c) => c.except ?? []),
      ...(glossary.banned.except ?? []),
    ];
    for (const e of excepts) {
      expect(e.reason, JSON.stringify(e)).toBeTruthy();
      if (e.source !== undefined) {
        expect(["bot", "app"], `except: source "${e.source}"`).toContain(e.source);
      }
      if (e.key) expect(keys.has(e.key), `except: no message "${e.key}"`).toBe(true);
      if (e.page) {
        const path = join(DOCS, e.page.replace(/^guides\//, ""));
        expect(existsSync(path), `except: no page ${e.page}`).toBe(true);
      }
    }
    for (const rule of rules) {
      for (const key of rule.in ?? []) {
        if (key.endsWith("*")) continue;
        expect(keys.has(key), `${rule.concept}: "in" names no message "${key}"`).toBe(true);
      }
    }
  });

  it("no retired or banned word in the bot or the Mini App, outside pending", () => {
    const found = wordsInProducts(rules, units).map(show);
    expect(found.filter((o) => !waiting.has(o))).toEqual([]);
  });

  it("no retired or banned word in the guides, outside pending", () => {
    const found = wordsInGuides(rules).map(show);
    expect(found.filter((o) => !waiting.has(o))).toEqual([]);
  });

  it("pending lists only words still there: remove an entry once it is fixed", () => {
    const found = new Set([...wordsInProducts(rules, units), ...wordsInGuides(rules)].map(show));
    expect([...waiting].filter((o) => !found.has(o))).toEqual([]);
  });

  it("a key both products define reads the same, unless the glossary says why", () => {
    const allowed = glossary["same-key-different-text"] ?? [];
    for (const entry of allowed) expect(entry.reason, entry.key).toBeTruthy();
    const ok = (/** @type {string} */ key, /** @type {string} */ locale) =>
      allowed.some(
        (/** @type {any} */ e) =>
          e.key === key.split(".")[0] && (e.locale === undefined || e.locale === locale),
      );
    const later = new Set(
      (pending["same-key"] ?? []).map((/** @type {any} */ e) => `${e.key} (${e.locale})`),
    );
    const differ = sameKeyDifferences();
    const found = differ.filter((d) => !ok(d.key, d.locale)).map((d) => `${d.key} (${d.locale})`);
    const shown = differ.map(
      (d) => `${d.key} (${d.locale}) ${JSON.stringify(d.args)}: bot "${d.bot}" · app "${d.app}"`,
    );
    expect(
      found.filter((k) => !later.has(k)),
      shown.join("\n"),
    ).toEqual([]);
    // Each allowance and each pending entry must still be needed, in each language it covers:
    // an allowance for both languages whose texts now agree in one must name the other.
    expect([...later].filter((k) => !found.includes(k))).toEqual([]);
    const differing = new Set(differ.map((d) => `${d.key.split(".")[0]} (${d.locale})`));
    expect(
      allowed.flatMap((/** @type {any} */ e) =>
        (e.locale === undefined ? LOCALES : [e.locale])
          .map((/** @type {string} */ locale) => `${e.key} (${locale})`)
          .filter((/** @type {string} */ k) => !differing.has(k)),
      ),
    ).toEqual([]);
    for (const e of allowed) {
      if (e.locale !== undefined) expect(LOCALES, `${e.key}: locale`).toContain(e.locale);
    }
  });

  it("reads both products in both languages", () => {
    for (const source of Object.keys(SOURCES)) {
      for (const locale of LOCALES) {
        expect(units.some((u) => u.source === source && u.locale === locale)).toBe(true);
      }
    }
  });
});
