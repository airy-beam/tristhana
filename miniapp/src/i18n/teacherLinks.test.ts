import { bundleFor, format, messageIds } from "./bundles";
import { LOCALES } from "./negotiate";

// ID-04 (spec §2): the copy the Mini App needs, in both languages. The wording of the shared
// keys is pinned for the bot in backend/tests/infrastructure/test_i18n_teacher_links.py.

const KEYS = [
  "links-title",
  "links-empty",
  "links-no-students",
  "links-primary-hint",
  "links-main-chosen",
  "links-main-auto",
  "links-make-main",
  "links-remove",
  "links-invite",
  "links-invite-first",
  "link-no-name",
  "link-unlink-ask",
  "link-next-main",
  "link-remove-ask",
  "invite-hint",
  "invite-share",
  "invite-share-text",
  "invite-copy",
  "invite-copied",
  "invite-new",
  "invite-new-ask",
];

const plain = (text: string) => text.replace(/[⁨⁩]/g, "");

describe("ID-04 copy", () => {
  it.each(LOCALES)("%s: has every message", (locale) => {
    const ids = messageIds(locale);
    expect(KEYS.filter((id) => !ids.has(id))).toEqual([]);
  });

  it("reads as written", () => {
    const en = bundleFor("en");
    const ru = bundleFor("ru");
    expect(format(en, "invite-copy")).toBe("Copy link");
    expect(format(ru, "invite-copy")).toBe("Скопировать ссылку");
    expect(format(en, "invite-copied")).toBe("Copied");
    expect(format(ru, "invite-copied")).toBe("Скопировано");
    expect(plain(format(ru, "links-main-auto", { name: "Лена" }))).toBe(
      "⭐ Основной учитель: Лена (в начале списка)",
    );
    expect(plain(format(ru, "link-next-main", { name: "Лена" }))).toBe(
      "Основным учителем станет: Лена.",
    );
  });

  it("the privacy line tells what a link shows, and the old promise is gone", () => {
    const en = format(bundleFor("en"), "settings-privacy-sharing");
    const ru = format(bundleFor("ru"), "settings-privacy-sharing");
    expect(en).toContain("A teacher on your list sees your name, your last asana and what you log");
    expect(ru).toContain("Учитель из твоего списка видит твоё имя, последнюю асану и то, что ты");
    expect(en).not.toContain("you choose what they see");
    expect(ru).not.toContain("ты выберешь, что им показывать");
  });

  it("the name hint and the delete explanation mention the lists", () => {
    expect(format(bundleFor("en"), "settings-name-hint")).toContain(
      "the name your teachers and students see here",
    );
    expect(format(bundleFor("ru"), "settings-name-hint")).toContain(
      "это имя видят твои учителя и ученики",
    );
    expect(format(bundleFor("en"), "delete-explain")).toContain("teacher and student lists");
    expect(format(bundleFor("ru"), "delete-explain")).toContain("списки учителей и учеников");
  });
});
