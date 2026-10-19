import type { City } from "../../api/client";
import { zoneLabel } from "../practiceText";

/** The phone's zone, or null when it says nothing about a place (UTC, unknown). */
export function deviceZone(): string | null {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return !zone || zone === "UTC" || zone === "Etc/UTC" ? null : zone;
}

const today = () => new Date().toISOString().slice(0, 10);

/** "UTC+5" for a zone today. */
export function offsetOf(zone: string): string {
  return /\(([^)]*)\)$/.exec(zoneLabel(zone, today()))?.[1] ?? "UTC";
}

/** "Almaty (UTC+5)". */
export const labelOf = (zone: string) => zoneLabel(zone, today());

/** One city per zone, in list order (Moscow stands for Kazan and Sochi). */
export function zoneCities(cities: City[]): City[] {
  const seen = new Set<string>();
  return cities.filter((c) => (seen.has(c.timezone) ? false : (seen.add(c.timezone), true)));
}

/** A city name for a zone when one of the listed cities uses it, else the zone's label. */
export function placeOf(zone: string, cities: City[] | undefined, ru: boolean): string {
  const city = cities?.find((c) => c.timezone === zone);
  if (city) return ru ? city.name_ru : city.name_en;
  return (zone.split("/").pop() ?? zone).replace(/_/g, " ");
}

/** "Keep Almaty" is remembered per device zone, so the prompt returns only after a move. */
export function keptFor(device: string): boolean {
  try {
    return localStorage.getItem("tz.keep") === device;
  } catch {
    return false;
  }
}

export function keep(device: string): void {
  try {
    localStorage.setItem("tz.keep", device);
  } catch {
    // Blocked storage: the prompt simply shows again next time.
  }
}
