// UI-05: reads and validates shots/manifest.yaml.
import { readFileSync } from "node:fs";
import { parse } from "yaml";

/** @typedef {{ name: string, kind: "app" | "bot", as: "student" | "teacher" | "newcomer", features: string[], say?: string, tap?: string[], click?: string[], full?: boolean }} Shot */

const KEYS = new Set(["name", "kind", "as", "features", "say", "tap", "click", "full"]);
const ROLES = ["student", "teacher", "newcomer"];

/** @returns {Shot[]} */
export function parseManifest(/** @type {string} */ text) {
  const shots = parse(text)?.shots;
  if (!Array.isArray(shots)) throw new Error("manifest: no `shots` list");
  const names = new Set();
  for (const shot of shots) {
    const where = `manifest: shot "${shot?.name}"`;
    if (typeof shot?.name !== "string" || !/^[a-z0-9-]+$/.test(shot.name)) {
      throw new Error(`${where}: name must be lower-case letters, digits and dashes`);
    }
    if (names.has(shot.name)) throw new Error(`${where}: listed twice`);
    names.add(shot.name);
    for (const key of Object.keys(shot)) {
      if (!KEYS.has(key)) throw new Error(`${where}: unknown key "${key}"`);
    }
    if (shot.kind !== "app" && shot.kind !== "bot") throw new Error(`${where}: kind is app or bot`);
    if (!ROLES.includes(shot.as)) throw new Error(`${where}: as is one of ${ROLES.join(", ")}`);
    if (!Array.isArray(shot.features) || shot.features.length === 0) {
      throw new Error(`${where}: needs features`);
    }
    if (shot.kind === "bot" && typeof shot.say !== "string") {
      throw new Error(`${where}: a bot shot needs say`);
    }
    if (shot.kind === "bot" && (shot.click || shot.full)) {
      throw new Error(`${where}: click and full are for app shots`);
    }
    if (shot.kind === "app" && (shot.say || shot.tap)) {
      throw new Error(`${where}: say and tap are for bot shots`);
    }
  }
  return shots;
}

export function readManifest(/** @type {string} */ file) {
  return parseManifest(readFileSync(file, "utf8"));
}

/** The shots whose name or one of whose features is in `only`; all of them when it is empty. */
export function select(/** @type {Shot[]} */ shots, /** @type {string[]} */ only) {
  if (only.length === 0) return shots;
  const picked = shots.filter(
    (shot) => only.includes(shot.name) || shot.features.some((id) => only.includes(id)),
  );
  const unknown = only.filter(
    (value) => !shots.some((shot) => shot.name === value || shot.features.includes(value)),
  );
  if (unknown.length) throw new Error(`no shot is named or tagged: ${unknown.join(", ")}`);
  return picked;
}
