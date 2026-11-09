import { FluentResource } from "@fluent/bundle";

import { bundleFor } from "./bundles";
import { LOCALES, type Locale } from "./negotiate";

const added = new Set<Record<Locale, string>>();

/** Copy that loads with a lazy screen (GM-02 `badges.ftl`), added once to every locale's cached
 * bundle, so the initial bundle doesn't carry it. Call at the lazy module's top level: it runs
 * before the screen renders, and `Localized` reads the bundles live. */
export function addMessages(sources: Record<Locale, string>): void {
  if (added.has(sources)) return;
  added.add(sources);
  for (const locale of LOCALES) {
    const errors = bundleFor(locale).addResource(new FluentResource(sources[locale]));
    if (errors.length) throw new Error(`${locale}: ${errors.map(String).join("; ")}`);
  }
}
