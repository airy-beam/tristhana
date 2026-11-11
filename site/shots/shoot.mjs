#!/usr/bin/env node
// UI-05: `npm run shots` makes every guide screenshot in both languages.
//   npm run shots                      all of them
//   npm run shots -- --only PR-01      by feature ID or by shot name (several allowed)
//   npm run shots -- --lang ru         one language only (its people are the only ones seeded)
// Needs: the local Postgres container, uv, and Google Chrome. Starts and stops its own demo
// backend and Mini App dev server (shots/lib/stack.mjs); your dev instance is not touched.
import { mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import sharp from "sharp";
import { createLabels, LOCALES } from "../src/lib/labels.mjs";
import { botHtml } from "./lib/bot-html.mjs";
import { CAST, CITY, SHALA } from "./lib/cast.mjs";
import { createClient } from "./lib/client.mjs";
import { readManifest, select } from "./lib/manifest.mjs";
import { seedCast } from "./lib/seed.mjs";
import { API, APP, DEMO, startStack } from "./lib/stack.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(here, "../src/assets/shots");
const PHONE = { width: 390, height: 844 };

const args = process.argv.slice(2);
const only = args.flatMap((arg, i) => (args[i - 1] === "--only" ? arg.split(",") : []));
const lang = args.flatMap((arg, i) => (args[i - 1] === "--lang" ? arg.split(",") : []));
const unknownLang = lang.filter((value) => !LOCALES.includes(value));
if (unknownLang.length) throw new Error(`--lang is one of ${LOCALES.join(", ")}`);
const locales = /** @type {("en" | "ru")[]} */ (lang.length ? lang : LOCALES);
const shots = select(readManifest(join(here, "manifest.yaml")), only);
const labels = createLabels();

/**
 * What a manifest step points at: `=student`, `=teacher` or `=shala` is that name in the demo
 * cast, `#2` is the second button of a bot message, anything else is a Fluent key.
 * @param {string} step
 * @param {"en" | "ru"} locale
 * @param {"bot" | "app"} from
 * @returns {{ text: string, exact: boolean } | { index: number }}
 */
function target(step, locale, from) {
  if (/^#\d+$/.test(step)) return { index: Number(step.slice(1)) };
  if (step.startsWith("=")) {
    const who = step.slice(1);
    const text =
      who === "shala" ? SHALA[locale] : CAST[locale][/** @type {"student"} */ (who)]?.name;
    if (!text) throw new Error(`no "${who}" in the demo cast`);
    return { text, exact: false };
  }
  return { text: labels.label(locale, step, {}, from), exact: true };
}

/** PNG bytes → a WebP file, small enough for a phone on a slow network. */
async function save(/** @type {Buffer} */ png, /** @type {string} */ file) {
  mkdirSync(dirname(file), { recursive: true });
  const info = await sharp(png).webp({ quality: 78, effort: 6 }).toFile(file);
  return Math.round(info.size / 1024);
}

const stop = await startStack();
const browser = await chromium.launch({ channel: "chrome" });
try {
  const client = createClient({ api: API, secret: DEMO.secret });
  for (const locale of locales) await seedCast(client, locale, { log: console.log });

  for (const locale of locales) {
    const context = await browser.newContext({
      viewport: PHONE,
      deviceScaleFactor: 2,
      locale: locale === "ru" ? "ru-RU" : "en-US",
      timezoneId: CITY.zone,
      colorScheme: "light",
    });
    for (const shot of shots) {
      const user = CAST[locale][shot.as];
      const page = await context.newPage();
      /** @type {Buffer} */
      let png;
      if (shot.kind === "bot") {
        let reply = await client.say(user, /** @type {string} */ (shot.say));
        for (const key of shot.tap ?? []) {
          const to = target(key, locale, "bot");
          reply = await client.tap(user, reply, "index" in to ? to.index : to.text);
        }
        await page.setContent(
          botHtml(reply, { said: shot.tap ? undefined : shot.say, lang: locale }),
        );
        png = await page.locator("body").screenshot();
      } else {
        const query = new URLSearchParams({ lang: locale, user: String(user.id), name: user.name });
        await page.goto(`${APP}/?${query}`, { waitUntil: "networkidle" });
        for (const key of shot.click ?? []) {
          const to = target(key, locale, "app");
          if ("index" in to) throw new Error(`${shot.name}: "#n" steps are for bot shots`);
          await page.getByText(to.text, { exact: to.exact }).first().click();
          await page.waitForLoadState("networkidle");
        }
        // Let fonts, lazy chunks and entry animations settle.
        await page.waitForTimeout(400);
        png = await page.screenshot({ fullPage: shot.full === true });
      }
      await page.close();
      const kb = await save(png, join(outDir, locale, `${shot.name}.webp`));
      console.log(`${locale}/${shot.name}.webp  ${kb} KB`);
    }
    await context.close();
  }
} finally {
  await browser.close();
  stop();
}
