// UI-05: the guides never type a button label or a command by hand. They quote the product's own
// Fluent messages, so a renamed button changes the guide and a removed one fails the build.
import { FluentBundle, FluentResource } from "@fluent/bundle";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

/** Where each product keeps its `.ftl` files, by source name. */
export const SOURCES = {
  bot: join(REPO, "backend/src/tristhana/infrastructure/i18n/locales"),
  app: join(REPO, "miniapp/src/locales"),
};
export const LOCALES = ["en", "ru"];
const WEBHOOK_TOOL = join(REPO, "tools/telegram/set_webhook.py");

export class LabelError extends Error {}

/**
 * @param {string} dir a locales directory holding `<locale>/*.ftl`
 * @param {string} locale
 */
function loadBundle(dir, locale) {
  // useIsolating adds invisible bidi marks around variables; plain text reads better in a guide.
  const bundle = new FluentBundle(locale, { useIsolating: false });
  const folder = join(dir, locale);
  for (const file of readdirSync(folder).sort()) {
    if (!file.endsWith(".ftl")) continue;
    const errors = bundle.addResource(new FluentResource(readFileSync(join(folder, file), "utf8")));
    if (errors.length) throw new LabelError(`${join(folder, file)}: ${errors[0].message}`);
  }
  return bundle;
}

/**
 * @param {Record<string, string>} [sources] source name → locales directory (tests pass their own)
 */
export function createLabels(sources = SOURCES) {
  /** @type {Map<string, FluentBundle>} */
  const bundles = new Map();
  const bundle = (/** @type {string} */ source, /** @type {string} */ locale) => {
    const id = `${source}/${locale}`;
    let found = bundles.get(id);
    if (!found) bundles.set(id, (found = loadBundle(sources[source], locale)));
    return found;
  };

  /**
   * The message `key` in `locale`, formatted with `args`.
   * @param {string} locale
   * @param {string} key
   * @param {Record<string, string>} [args] numeric strings become numbers, so plurals work
   * @param {string} [from] "bot" or "app"; needed only when both have the key with different text
   */
  function label(locale, key, args = {}, from) {
    if (!LOCALES.includes(locale)) throw new LabelError(`unknown locale "${locale}"`);
    if (from !== undefined && !(from in sources)) {
      throw new LabelError(`"${key}": from must be one of ${Object.keys(sources).join(", ")}`);
    }
    const values = Object.fromEntries(
      Object.entries(args).map(([name, value]) => [
        name,
        /^-?\d+(\.\d+)?$/.test(value) ? Number(value) : value,
      ]),
    );
    const names = from ? [from] : Object.keys(sources);
    const texts = new Map();
    for (const name of names) {
      const message = bundle(name, locale).getMessage(key);
      if (!message?.value) continue;
      /** @type {Error[]} */
      const errors = [];
      const text = bundle(name, locale).formatPattern(message.value, values, errors);
      if (errors.length) {
        throw new LabelError(`"${key}" (${name}, ${locale}): ${errors[0].message}`);
      }
      texts.set(name, text);
    }
    if (texts.size === 0) {
      throw new LabelError(`no message "${key}" in ${names.join(" or ")} (${locale})`);
    }
    const distinct = new Set(texts.values());
    if (distinct.size > 1) {
      throw new LabelError(
        `"${key}" differs between ${[...texts.keys()].join(" and ")} (${locale}): add {from=bot} or {from=app}`,
      );
    }
    const text = [...distinct][0];
    if (text.includes("\n")) {
      throw new LabelError(`"${key}" (${locale}) is a multi-line message, not a label`);
    }
    return text;
  }

  return { label };
}

/** The commands the bot's menu shows, read from the tool that registers them. */
export function menuCommands(file = WEBHOOK_TOOL) {
  const match = /^COMMANDS = \(([^)]*)\)/m.exec(readFileSync(file, "utf8"));
  if (!match) throw new LabelError(`no COMMANDS tuple in ${file}`);
  return [...match[1].matchAll(/"([a-z_]+)"/g)].map((found) => found[1]);
}

/** `ru` for files under a `/ru/` content folder, otherwise `en` (the root locale). */
export function localeOfPath(/** @type {string} */ path) {
  return /[\\/]docs[\\/]ru[\\/]/.test(path) ? "ru" : "en";
}
