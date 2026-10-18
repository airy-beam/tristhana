import { FluentBundle, FluentResource, type FluentVariable } from "@fluent/bundle";

import enApp from "../locales/en/app.ftl?raw";
import ruApp from "../locales/ru/app.ftl?raw";
import type { Locale } from "./negotiate";

// Both locales are bundled while small (< 10 KB each); split per locale when they grow.
const SOURCES: Record<Locale, string> = { en: enApp, ru: ruApp };
const cache = new Map<Locale, FluentBundle>();

export function bundleFor(locale: Locale): FluentBundle {
  let bundle = cache.get(locale);
  if (!bundle) {
    bundle = new FluentBundle(locale);
    const errors = bundle.addResource(new FluentResource(SOURCES[locale]));
    if (errors.length) throw new Error(`${locale}: ${errors.map(String).join("; ")}`);
    cache.set(locale, bundle);
  }
  return bundle;
}

export function messageIds(locale: Locale): Set<string> {
  return new Set(Object.keys(messageVariables(locale)));
}

/** `$variable` names used by each message (for the en/ru parity test). */
export function messageVariables(locale: Locale): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  for (const message of new FluentResource(SOURCES[locale]).body) {
    const vars = new Set<string>();
    collectVariables(message.value, vars);
    result[message.id] = [...vars].sort();
  }
  return result;
}

function collectVariables(node: unknown, into: Set<string>): void {
  if (Array.isArray(node)) {
    for (const child of node) collectVariables(child, into);
  } else if (node !== null && typeof node === "object") {
    const record = node as Record<string, unknown>;
    if (record.type === "var" && typeof record.name === "string") into.add(record.name);
    for (const value of Object.values(record)) collectVariables(value, into);
  }
}

/** Fluent silently drops unparsable entries; count `id =` lines to catch them. */
export function definedIdCount(locale: Locale): number {
  return [...SOURCES[locale].matchAll(/^[a-z][a-z0-9-]*\s*=/gm)].length;
}

/** Formats outside React (tests, non-component code). Isolation marks stripped for asserts. */
export function format(
  bundle: FluentBundle,
  id: string,
  args?: Record<string, FluentVariable>,
): string {
  const message = bundle.getMessage(id);
  if (!message?.value) throw new Error(`missing message ${id}`);
  const errors: Error[] = [];
  const text = bundle.formatPattern(message.value, args, errors);
  if (errors.length) throw new Error(errors.map(String).join("; "));
  return text.replace(/[⁨⁩]/g, "");
}
