import type { City } from "../api/client";
import type { Locale } from "../i18n/negotiate";

/** A city's name in the person's language; its slug until the list has loaded. */
export const cityName = (city: City | undefined, slug: string, locale: Locale) =>
  city ? (locale === "ru" ? city.name_ru : city.name_en) : slug;
