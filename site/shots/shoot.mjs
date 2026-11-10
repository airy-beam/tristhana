#!/usr/bin/env node
// UI-05: `npm run shots` makes every guide screenshot in both languages.
//   npm run shots                      all of them
//   npm run shots -- --only PR-01      by feature ID or by shot name (several allowed)
// Needs: the local Postgres container, uv, and Google Chrome. Starts and stops its own demo
// backend and Mini App dev server (shots/lib/stack.mjs); your dev instance is not touched.
import { mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import sharp from "sharp";
import { createLabels, LOCALES } from "../src/lib/labels.mjs";
import { botHtml } from "./lib/bot-html.mjs";
import { CAST, CITY } from "./lib/cast.mjs";
import { createClient } from "./lib/client.mjs";
import { readManifest, select } from "./lib/manifest.mjs";
import { seedCast } from "./lib/seed.mjs";
import { API, APP, DEMO, startStack } from "./lib/stack.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(here, "../src/assets/shots");
const PHONE = { width: 390, height: 844 };

const args = process.argv.slice(2);
const only = args.flatMap((arg, i) => (args[i - 1] === "--only" ? arg.split(",") : []));
const shots = select(readManifest(join(here, "manifest.yaml")), only);
const labels = createLabels();

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
  for (const locale of LOCALES)
    await seedCast(client, /** @type {"en" | "ru"} */ (locale), { log: console.log });

  for (const locale of /** @type {("en" | "ru")[]} */ (LOCALES)) {
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
          reply = await client.tap(user, reply, labels.label(locale, key, {}, "bot"));
        }
        await page.setContent(
          botHtml(reply, { said: shot.tap ? undefined : shot.say, lang: locale }),
        );
        png = await page.locator("body").screenshot();
      } else {
        const query = new URLSearchParams({ lang: locale, user: String(user.id), name: user.name });
        await page.goto(`${APP}/?${query}`, { waitUntil: "networkidle" });
        for (const key of shot.click ?? []) {
          await page
            .getByText(labels.label(locale, key, {}, "app"), { exact: true })
            .first()
            .click();
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
