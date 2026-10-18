// NF-09 budget: initial JS (entry + modulepreloads) <= 150 KB gzip, CSS <= 10 KB gzip.
// Lazy chunks (ECharts later) don't count. No dependencies: node:zlib only.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const DIST = new URL("../dist/", import.meta.url).pathname;
const BUDGET = { js: 150 * 1024, css: 10 * 1024 };

const html = readFileSync(join(DIST, "index.html"), "utf8");
const refs = (pattern) => [...html.matchAll(pattern)].map((m) => m[1]);
const initial = {
  js: [
    ...refs(/<script[^>]+src="\/([^"]+\.js)"/g),
    ...refs(/<link[^>]+rel="modulepreload"[^>]+href="\/([^"]+)"/g),
  ],
  css: refs(/<link[^>]+rel="stylesheet"[^>]+href="\/([^"]+)"/g),
};

if (initial.js.length === 0) {
  console.log("FAIL no entry script found in dist/index.html (check the regexes / base path)");
  process.exit(1);
}

let failed = false;
for (const [kind, files] of Object.entries(initial)) {
  const size = files.reduce((sum, f) => sum + gzipSync(readFileSync(join(DIST, f))).length, 0);
  const ok = size <= BUDGET[kind];
  failed ||= !ok;
  console.log(
    `${ok ? "ok  " : "FAIL"} initial ${kind}: ${(size / 1024).toFixed(1)} KB gzip ` +
      `(budget ${BUDGET[kind] / 1024} KB, ${files.length} file(s))`,
  );
}
process.exit(failed ? 1 : 0);
