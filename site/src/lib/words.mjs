// UI-06 stage 5, ADR-0050: one word per thing. `docs/glossary.yaml` names the words; these pure
// functions find the texts that still use a retired or banned word, and the keys the bot and the
// Mini App both define with different text. Tests point them at fixtures or at the real files.
import { FluentBundle, FluentResource } from "@fluent/bundle";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { readPages } from "./check.mjs";
import { LOCALES, SOURCES } from "./labels.mjs";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
export const GLOSSARY = join(REPO, "docs/glossary.yaml");
export const DOCS = join(REPO, "site/src/content/docs");

/** @typedef {{ key?: string, source?: string, page?: string, reason?: string }} Except */
/** @typedef {{ concept: string, locale: string, word: string, re: RegExp, in: string[] | null, guides: boolean, except: Except[] }} Rule */
/** @typedef {{ file: string, key?: string, word: string }} Offender */
/** @typedef {{ source: string, locale: string, file: string, key: string, texts: string[] }} Unit */

export function readGlossary(/** @type {string} */ file = GLOSSARY) {
  return parse(readFileSync(file, "utf8"));
}

/** A glossary expression as a whole-word, case-insensitive, Unicode regex. */
export function wordRegex(/** @type {string} */ source) {
  return new RegExp(`(?<![\\p{L}\\p{N}])(?:${source})(?![\\p{L}\\p{N}])`, "giu");
}

/**
 * Every retired and banned word of the glossary, one rule per word and language.
 * @param {any} glossary
 * @returns {Rule[]}
 */
export function rulesOf(glossary) {
  /** @type {Rule[]} */
  const rules = [];
  const add = (
    /** @type {string} */ concept,
    /** @type {Record<string, any[]> | undefined} */ words,
    /** @type {Except[]} */ except,
  ) => {
    for (const locale of LOCALES) {
      for (const entry of words?.[locale] ?? []) {
        const spec = typeof entry === "string" ? { word: entry } : entry;
        rules.push({
          concept,
          locale,
          word: spec.word,
          re: wordRegex(spec.word),
          in: spec.in ?? null,
          guides: spec.in ? false : spec.guides !== false,
          except,
        });
      }
    }
  };
  for (const concept of glossary.concepts ?? []) {
    add(concept.concept, concept.retired, concept.except ?? []);
  }
  add("banned", glossary.banned, glossary.banned?.except ?? []);
  return rules;
}

/** Does `key` fall under a list of keys, where `prefix-*` covers a prefix? */
export function keyIn(/** @type {string} */ key, /** @type {string[]} */ keys) {
  return keys.some((k) => (k.endsWith("*") ? key.startsWith(k.slice(0, -1)) : key === k));
}

/** Above this many combinations a select's variants are read each on its own. */
const COMBINATIONS = 256;

/**
 * What a person can read in a Fluent pattern: one text per combination of select variants
 * (every variant, not only the default), with variables and references removed. Whitespace is
 * collapsed so a phrase split by a removed variable still reads as one. Past `COMBINATIONS`, a
 * select's variants become texts of their own and the line around them reads a gap there:
 * never one variant run into the next, which would make phrases no one reads.
 * @param {import("@fluent/bundle").FluentResource["body"][number]["value"]} pattern
 * @returns {string[]}
 */
export function readable(pattern) {
  /** @type {string[]} */
  const alone = [];
  /** @returns {string[]} */
  const walk = (/** @type {any} */ p) => {
    if (p === null || p === undefined) return [];
    if (typeof p === "string") return [p];
    let out = [""];
    for (const element of p) {
      /** @type {string[]} */
      let parts;
      if (typeof element === "string") parts = [element];
      else if (element.type === "select")
        parts = element.variants.flatMap((/** @type {any} */ v) => walk(v.value));
      else if (element.type === "str") parts = [element.value];
      else parts = [" "]; // a variable, a number, another message: not words of this one
      if (out.length * parts.length > COMBINATIONS) {
        alone.push(...parts);
        parts = [" "];
      }
      out = out.flatMap((before) => parts.map((part) => before + part));
    }
    return out;
  };
  const texts = [...walk(pattern), ...alone].map((text) => text.replace(/\s+/g, " ").trim());
  return [...new Set(texts)].filter(Boolean);
}

/**
 * Every message of every `.ftl` file of each product and language, as readable texts. A message's
 * attributes are units of their own (`key.attr`).
 * @param {Record<string, string>} [sources] product → locales directory
 * @returns {Unit[]}
 */
export function productUnits(sources = SOURCES) {
  /** @type {Unit[]} */
  const units = [];
  for (const [source, dir] of Object.entries(sources)) {
    for (const locale of LOCALES) {
      for (const name of readdirSync(join(dir, locale)).sort()) {
        if (!name.endsWith(".ftl")) continue;
        const resource = new FluentResource(readFileSync(join(dir, locale, name), "utf8"));
        const file = `${source}/${locale}/${name}`;
        for (const entry of resource.body) {
          const parts = [[entry.id, entry.value], ...Object.entries(entry.attributes)];
          for (const [part, pattern] of parts) {
            const key = part === entry.id ? entry.id : `${entry.id}.${part}`;
            units.push({ source, locale, file, key, texts: readable(pattern) });
          }
        }
      }
    }
  }
  return units;
}

const DIRECTIVE = /:(?:ftl|cmd)\[[^\]]*\](?:\{[^}]*\})?/g;

/**
 * What a person reads on a guide page: the title, the description, the hero's words and the
 * prose, without :ftl[…] and :cmd[…] (the product's own words, checked at their source), code,
 * link targets, image paths, imports and comments. Components keep their title, description and
 * alt text.
 * @param {{ front: Record<string, any>, body: string }} page
 */
export function pageText({ front, body }) {
  const hero = front.hero ?? {};
  const head = [
    front.title,
    front.description,
    hero.tagline,
    hero.image?.alt,
    ...(hero.actions ?? []).map((/** @type {any} */ a) => a.text),
  ];
  const prose = body
    .replace(/^(`{3,}|~{3,})[^\n]*\n[\s\S]*?^\1[^\n]*$/gm, " ")
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/^import .*$/gm, " ")
    .replace(DIRECTIVE, " ")
    .replace(/`[^`\n]*`/g, " ")
    .replace(/\]\([^)]*\)/g, "] ")
    .replace(/<[^>]*>/g, (tag) =>
      [...tag.matchAll(/\b(?:title|description|alt)="([^"]*)"/g)].map((m) => m[1]).join(" · "),
    )
    .replace(/https?:\/\/\S+/g, " ");
  return [...head.filter(Boolean), prose].join("\n").replace(/\s+/g, " ");
}

const excepted = (
  /** @type {Rule} */ rule,
  /** @type {{ key?: string, source?: string, page?: string }} */ where,
) =>
  rule.except.some((e) =>
    e.page
      ? e.page === where.page
      : e.key !== undefined &&
        e.key === where.key &&
        (e.source === undefined || e.source === where.source),
  );

/** One offender per file, key and word found (lower case), sorted. */
const unique = (/** @type {Offender[]} */ found) => {
  const seen = new Map();
  for (const o of found) seen.set(`${o.file}\u0000${o.key ?? ""}\u0000${o.word}`, o);
  return [...seen.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([, o]) => o);
};

/**
 * Messages that say a retired or banned word of their language.
 * @param {Rule[]} rules
 * @param {Unit[]} units
 * @returns {Offender[]}
 */
export function wordsInProducts(rules, units) {
  /** @type {Offender[]} */
  const found = [];
  for (const unit of units) {
    const id = unit.key.split(".")[0];
    for (const rule of rules) {
      if (rule.locale !== unit.locale) continue;
      if (rule.in && !keyIn(id, rule.in)) continue;
      if (excepted(rule, { key: id, source: unit.source })) continue;
      for (const text of unit.texts) {
        for (const [match] of text.matchAll(rule.re)) {
          found.push({ file: unit.file, key: unit.key, word: match.toLowerCase() });
        }
      }
    }
  }
  return unique(found);
}

/**
 * Guide pages that say a retired or banned word of their language (rules scoped to message keys
 * and rules marked `guides: false` do not apply).
 * @param {Rule[]} rules
 * @param {string} [docsDir]
 * @returns {Offender[]}
 */
export function wordsInGuides(rules, docsDir = DOCS) {
  /** @type {Offender[]} */
  const found = [];
  for (const page of readPages(docsDir)) {
    const file = `guides/${page.file.split("\\").join("/")}`;
    const text = pageText(page);
    for (const rule of rules) {
      if (rule.locale !== page.locale || !rule.guides || excepted(rule, { page: file })) continue;
      for (const [match] of text.matchAll(rule.re)) {
        found.push({ file, word: match.toLowerCase() });
      }
    }
  }
  return unique(found);
}

/** @param {Record<string, string>} sources @param {string} locale */
function bundlesOf(sources, locale) {
  /** @type {Record<string, FluentBundle>} */
  const out = {};
  for (const [source, dir] of Object.entries(sources)) {
    const bundle = new FluentBundle(locale, { useIsolating: false });
    for (const name of readdirSync(join(dir, locale)).sort()) {
      if (name.endsWith(".ftl")) {
        bundle.addResource(new FluentResource(readFileSync(join(dir, locale, name), "utf8")));
      }
    }
    out[source] = bundle;
  }
  return out;
}

/**
 * The variables a pattern reads (following message references), each with the values worth
 * trying: every select key it meets, plural-sized numbers and a name.
 * @param {FluentBundle[]} bundles
 * @param {any} pattern
 * @param {Map<string, Set<string | number>>} [vars]
 */
function variablesOf(bundles, pattern, vars = new Map(), depth = 0) {
  const note = (/** @type {string} */ name) => {
    if (!vars.has(name)) vars.set(name, new Set([1, 2, 5, 21, "Anna"]));
    return /** @type {Set<string | number>} */ (vars.get(name));
  };
  const expression = (/** @type {any} */ e) => {
    if (e.type === "var") note(e.name);
    else if (e.type === "select") {
      expression(e.selector);
      for (const variant of e.variants) {
        if (e.selector.type === "var") note(e.selector.name).add(variant.key.value);
        variablesOf(bundles, variant.value, vars, depth);
      }
    } else if (e.type === "func" || e.type === "term") {
      for (const arg of e.args) expression(arg.type === "narg" ? arg.value : arg);
    } else if (e.type === "mesg" && depth < 5) {
      for (const bundle of bundles) {
        const message = bundle.getMessage(e.name);
        const target = e.attr ? message?.attributes[e.attr] : message?.value;
        if (target) variablesOf(bundles, target, vars, depth + 1);
      }
    }
  };
  if (Array.isArray(pattern)) {
    for (const element of pattern) if (typeof element !== "string") expression(element);
  }
  return vars;
}

/** Argument sets: every combination when there are few, else one variable at a time. */
function samples(/** @type {Map<string, Set<string | number>>} */ vars) {
  const names = [...vars.keys()];
  const values = names.map((name) => [.../** @type {Set<string | number>} */ (vars.get(name))]);
  const total = values.reduce((n, v) => n * v.length, 1);
  /** @type {Record<string, string | number>[]} */
  let sets = [{}];
  if (total <= 512) {
    names.forEach((name, i) => {
      sets = sets.flatMap((set) => values[i].map((value) => ({ ...set, [name]: value })));
    });
    return sets;
  }
  const base = Object.fromEntries(names.map((name, i) => [name, values[i][0]]));
  return names.flatMap((name, i) => values[i].map((value) => ({ ...base, [name]: value })));
}

/**
 * Keys the bot and the Mini App both define (values and attributes) that render differently
 * for some sample of their variables, per language. Each comes with the first difference found.
 * @param {Record<string, string>} [sources] needs exactly `bot` and `app`
 * @returns {{ key: string, locale: string, args: Record<string, string | number>, bot: string, app: string }[]}
 */
export function sameKeyDifferences(sources = SOURCES) {
  /** @type {{ key: string, locale: string, args: Record<string, string | number>, bot: string, app: string }[]} */
  const out = [];
  for (const locale of LOCALES) {
    const { bot, app } = bundlesOf(sources, locale);
    const ids = new Set();
    for (const name of readdirSync(join(sources.bot, locale))) {
      if (!name.endsWith(".ftl")) continue;
      const text = readFileSync(join(sources.bot, locale, name), "utf8");
      for (const entry of new FluentResource(text).body) ids.add(entry.id);
    }
    for (const id of [...ids].sort()) {
      if (!app.hasMessage(id) || !bot.hasMessage(id)) continue;
      const mine = /** @type {import("@fluent/bundle").Message} */ (bot.getMessage(id));
      const theirs = /** @type {import("@fluent/bundle").Message} */ (app.getMessage(id));
      /** @type {[string, any, any][]} */
      const parts = [[id, mine.value, theirs.value]];
      for (const attr of Object.keys(mine.attributes)) {
        if (attr in theirs.attributes) {
          parts.push([`${id}.${attr}`, mine.attributes[attr], theirs.attributes[attr]]);
        }
      }
      for (const [key, a, b] of parts) {
        if (a === null || b === null) continue;
        const vars = variablesOf([bot, app], a);
        variablesOf([bot, app], b, vars);
        for (const args of samples(vars)) {
          const said = bot.formatPattern(a, args, []);
          const shown = app.formatPattern(b, args, []);
          if (said !== shown) {
            out.push({ key, locale, args, bot: said, app: shown });
            break;
          }
        }
      }
    }
  }
  return out;
}
