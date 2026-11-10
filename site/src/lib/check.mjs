// UI-05 guide-check: finds guide pages that drifted from the product or from their twin in the
// other language. Pure functions over a docs folder, so tests can point them at a fixture.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { parse } from "yaml";
import { LabelError } from "./labels.mjs";

const DIRECTIVE = /:(ftl|cmd)\[([^\]]*)\](?:\{([^}]*)\})?/g;
const FEATURE_ID = /^[A-Z]{2}-\d{2}$/;

/** @typedef {{ slug: string, locale: "en" | "ru", file: string, front: Record<string, any>, body: string }} Page */
/** @typedef {{ name: "ftl" | "cmd", key: string, args: Record<string, string> }} Directive */

/** All `.md`/`.mdx` files under `dir`, as paths relative to it. */
function walk(/** @type {string} */ dir, /** @type {string} */ base = dir) {
  /** @type {string[]} */
  const found = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) found.push(...walk(path, base));
    else if (/\.mdx?$/.test(entry.name)) found.push(relative(base, path));
  }
  return found.sort();
}

/** @returns {Page[]} */
export function readPages(/** @type {string} */ docsDir) {
  return walk(docsDir).map((file) => {
    const text = readFileSync(join(docsDir, file), "utf8");
    const match = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(text);
    const parts = file.split(sep);
    const ru = parts[0] === "ru";
    const slug = (ru ? parts.slice(1) : parts).join("/").replace(/\.mdx?$/, "");
    return {
      slug,
      locale: ru ? "ru" : "en",
      file,
      front: match ? (parse(match[1]) ?? {}) : {},
      body: match ? match[2] : text,
    };
  });
}

/** @returns {Directive[]} */
export function directivesIn(/** @type {string} */ body) {
  return [...body.matchAll(DIRECTIVE)].map(([, name, key, attrs = ""]) => ({
    name: /** @type {"ftl" | "cmd"} */ (name),
    key: key.trim(),
    args: Object.fromEntries(
      [...attrs.matchAll(/([\w-]+)=(?:"([^"]*)"|(\S+))/g)].map(([, k, quoted, bare]) => [
        k,
        quoted ?? bare,
      ]),
    ),
  }));
}

const headings = (/** @type {string} */ body) => (body.match(/^#{2,4} /gm) ?? []).length;
const images = (/** @type {string} */ body) =>
  [...body.matchAll(/shots\/(?:en|ru)\/([\w.-]+)/g)].map((m) => m[1]).sort();
const same = (/** @type {unknown} */ a, /** @type {unknown} */ b) =>
  JSON.stringify(a) === JSON.stringify(b);

/**
 * @param {{ docsDir: string, label: (locale: string, key: string, args?: Record<string, string>, from?: string) => string, commands: string[] }} input
 * @returns {string[]} one line per problem; empty when the guides are in order
 */
export function checkGuide({ docsDir, label, commands }) {
  /** @type {string[]} */
  const problems = [];
  const pages = readPages(docsDir);
  const bySlug = new Map();
  for (const page of pages) {
    bySlug.set(page.slug, { ...bySlug.get(page.slug), [page.locale]: page });
  }

  const documented = new Set();
  for (const page of pages) {
    const features = page.front.features;
    if (!Array.isArray(features) || features.length === 0) {
      problems.push(`${page.file}: no "features" in the front matter`);
    } else {
      for (const id of features) {
        if (!FEATURE_ID.test(String(id)))
          problems.push(`${page.file}: "${id}" is not a feature ID`);
      }
    }
    if (!page.front.title) problems.push(`${page.file}: no title`);
    if (!page.front.description) problems.push(`${page.file}: no description`);

    for (const directive of directivesIn(page.body)) {
      if (directive.name === "cmd") {
        if (commands.includes(directive.key)) documented.add(directive.key);
        else problems.push(`${page.file}: :cmd[${directive.key}] is not in the bot's command menu`);
        continue;
      }
      const { from, ...args } = directive.args;
      try {
        label(page.locale, directive.key, args, from);
      } catch (error) {
        if (!(error instanceof LabelError)) throw error;
        problems.push(`${page.file}: ${error.message}`);
      }
    }
  }

  for (const [slug, pair] of bySlug) {
    if (!pair.en) problems.push(`${pair.ru.file}: no English page for "${slug}"`);
    if (!pair.ru) problems.push(`${pair.en.file}: no Russian page for "${slug}"`);
    if (!pair.en || !pair.ru) continue;
    const differs = (/** @type {string} */ what) =>
      problems.push(`${pair.ru.file}: ${what} differ from ${pair.en.file}`);
    if (!same(pair.en.front.features, pair.ru.front.features)) differs("features");
    if (headings(pair.en.body) !== headings(pair.ru.body)) differs("the number of headings");
    if (!same(images(pair.en.body), images(pair.ru.body))) differs("the screenshots");
    const keys = (/** @type {Page} */ page) =>
      directivesIn(page.body)
        .map((d) => `${d.name}:${d.key}`)
        .sort();
    if (!same(keys(pair.en), keys(pair.ru))) differs("the quoted labels and commands");
  }

  for (const command of commands) {
    if (!documented.has(command)) problems.push(`/${command} is in the bot's menu but in no guide`);
  }
  return problems;
}

/**
 * Feature ID → the page slugs that document it, both sorted. `guide-update <ID>` starts here.
 * @returns {Record<string, string[]>}
 */
export function guideMap(/** @type {string} */ docsDir) {
  /** @type {Record<string, Set<string>>} */
  const map = {};
  for (const page of readPages(docsDir)) {
    if (page.locale !== "en" || !Array.isArray(page.front.features)) continue;
    for (const id of page.front.features) (map[id] ??= new Set()).add(page.slug);
  }
  return Object.fromEntries(
    Object.keys(map)
      .sort()
      .map((id) => [id, [...map[id]].sort()]),
  );
}

export function readMap(/** @type {string} */ file) {
  return existsSync(file) ? (parse(readFileSync(file, "utf8")) ?? {}) : {};
}
