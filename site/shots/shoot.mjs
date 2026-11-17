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
 * A control with no visible words (the Mini App's gear, "⚙️") is found by its accessible
 * name, the message's `.aria-label`.
 * @returns {{ text: string, exact: boolean, name?: string } | { index: number }}
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
  const name = labels.ariaLabel(locale, step, from) ?? undefined;
  return { text: labels.label(locale, step, {}, from), exact: true, name };
}

/**
 * What a bot shot's person sends. `=invite` is the start code of the demo teacher's invite
 * link, which exists only once the cast is seeded: `/start =invite` is someone opening it.
 * @param {ReturnType<typeof createClient>} client
 * @param {string} say
 * @param {"en" | "ru"} locale
 */
async function message(client, say, locale) {
  if (!say.includes("=invite")) return say;
  const invite = /** @type {{ url: string }} */ (
    await client.call(CAST[locale].teacher, "POST", "/me/invite", {})
  );
  const code = /[?&]start=([\w-]+)/.exec(invite.url)?.[1];
  if (!code) throw new Error(`no start code in the invite link ${invite.url}`);
  return say.replace("=invite", code);
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

  const health = /** @type {{ version: string, commit: string }} */ (
    await (await fetch(`${API}/api/v1/health`)).json()
  );
  const serverLine = Object.fromEntries(
    locales.map((locale) => [
      locale,
      labels.label(
        locale,
        "home-server-status",
        { version: health.version, commit: health.commit.slice(0, 7) },
        "app",
      ),
    ]),
  );

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
        const say = /** @type {string} */ (shot.say);
        let reply = await client.say(user, await message(client, say, locale));
        for (const key of shot.tap ?? []) {
          const to = target(key, locale, "bot");
          reply = await client.tap(user, reply, "index" in to ? to.index : to.text);
        }
        await page.setContent(
          // A typed command is drawn above the reply; a tapped path or an opened link is not.
          botHtml(reply, { said: shot.tap || say.includes("=") ? undefined : say, lang: locale }),
        );
        png = await page.locator("body").screenshot();
      } else {
        const query = new URLSearchParams({ lang: locale, user: String(user.id), name: user.name });
        await page.goto(`${APP}/?${query}`, { waitUntil: "networkidle" });
        for (const key of shot.click ?? []) {
          const to = target(key, locale, "app");
          if ("index" in to) throw new Error(`${shot.name}: "#n" steps are for bot shots`);
          const control = to.name
            ? page.getByRole("button", { name: to.name, exact: true })
            : page.getByText(to.text, { exact: to.exact });
          await control.first().click();
          await page.waitForLoadState("networkidle");
        }
        // Let fonts, lazy chunks and entry animations settle.
        await page.waitForTimeout(400);
        // The dev build always shows the server's version on Today; people see it only after
        // a long press, so it does not belong in a guide picture.
        // (Fluent wraps the variables in invisible marks in the app, so compare without them.)
        await page.getByRole("status").evaluateAll((lines, wanted) => {
          for (const line of lines) {
            if (line.textContent?.replace(/[\u2066-\u2069]/g, "") !== wanted) continue;
            // Hidden, not removed: the node stays React's.
            /** @type {HTMLElement} */ (line).style.display = "none";
          }
        }, serverLine[locale]);
        if (shot.full === true) {
          // The whole page, as one tall phone: a plain full-page capture would leave the
          // fixed tab bar where the first screen ends, across the middle of the picture.
          const height = await page.evaluate(() => document.documentElement.scrollHeight);
          await page.setViewportSize({
            width: PHONE.width,
            height: Math.max(height, PHONE.height),
          });
          await page.waitForTimeout(200);
        }
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
