#!/usr/bin/env node
// UI-05: the built site must load nothing from other sites (no fonts, scripts, images or
// styles), and stay inside its page-weight budget. Plain links (<a href>) are fine.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const dist = resolve(dirname(fileURLToPath(import.meta.url)), "../dist");
const LANDING_BUDGET_KB = 150;

/** @returns {string[]} */
function walk(/** @type {string} */ dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? walk(join(dir, entry.name)) : [join(dir, entry.name)],
  );
}

const problems = [];
const html = walk(dist).filter((file) => file.endsWith(".html"));
for (const file of html) {
  const text = readFileSync(file, "utf8");
  for (const [, tag, url] of text.matchAll(
    /<(script|link|img|source|iframe|video|audio)\b[^>]*?\s(?:src|href|srcset)="(https?:\/\/[^"]+)"/g,
  )) {
    // <link rel="canonical|alternate|sitemap"> point at this site itself.
    if (tag === "link" && url.startsWith("https://tristhana-guide.web.app")) continue;
    problems.push(`${file}: <${tag}> loads ${url}`);
  }
  if (/@import\s+url\(["']?https?:/.test(text)) problems.push(`${file}: remote @import`);
}

/** Gzipped size of a page plus the scripts and styles it references. */
function weight(/** @type {string} */ page) {
  const text = readFileSync(page, "utf8");
  const assets = [...text.matchAll(/(?:src|href)="(\/[^"]+\.(?:js|css|svg))"/g)].map((m) => m[1]);
  const files = [page, ...new Set(assets)].map((path) => (path === page ? page : join(dist, path)));
  return files.reduce(
    (sum, file) =>
      sum + (statSync(file, { throwIfNoEntry: false }) ? gzipSync(readFileSync(file)).length : 0),
    0,
  );
}

for (const page of ["index.html", "ru/index.html"]) {
  const kb = weight(join(dist, page)) / 1024;
  console.log(`${page}: ${kb.toFixed(1)} KB gzip (budget ${LANDING_BUDGET_KB})`);
  if (kb > LANDING_BUDGET_KB) problems.push(`${page}: ${kb.toFixed(1)} KB is over the budget`);
}

for (const problem of problems) console.error(`✗ ${problem}`);
if (problems.length) process.exit(1);
console.log(`${html.length} pages, no outside requests.`);
