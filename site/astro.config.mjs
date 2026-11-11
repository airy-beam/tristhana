// UI-05: the public site (landing page + guides). Static output, no client framework.
import starlight from "@astrojs/starlight";
import { satteri } from "@astrojs/markdown-satteri";
import { defineConfig } from "astro/config";
import { guideDirectives } from "./src/lib/directives.mjs";

/** A sidebar group whose label is translated; page labels come from each page's own title. */
const group = (
  /** @type {string} */ en,
  /** @type {string} */ ru,
  /** @type {string} */ folder,
  /** @type {string[]} */ pages,
) => ({
  label: en,
  translations: { ru },
  items: pages.map((page) => `${folder}/${page}`),
});

export default defineConfig({
  site: "https://tristhana.app",
  trailingSlash: "always",
  markdown: {
    processor: satteri({ features: { directive: true }, mdastPlugins: [guideDirectives()] }),
  },
  integrations: [
    starlight({
      title: "Tristhana",
      description: "A companion for your Ashtanga practice, in Telegram.",
      logo: { src: "./src/assets/mark.svg", alt: "" },
      favicon: "/favicon.svg",
      defaultLocale: "root",
      locales: {
        root: { label: "English", lang: "en" },
        ru: { label: "Русский", lang: "ru" },
      },
      social: [
        { icon: "telegram", label: "Telegram", href: "https://t.me/tristhana_bot" },
        { icon: "github", label: "GitHub", href: "https://github.com/airy-beam/tristhana" },
      ],
      customCss: ["./src/styles/brand.css"],
      // No "edit this page" links, no remote fonts, no analytics: the site makes no outside requests.
      lastUpdated: false,
      credits: false,
      sidebar: [
        group("Start here", "С чего начать", "start", ["first-steps", "bot-and-app"]),
        group("For students", "Практикующим", "students", [
          "log-practice",
          "rest-and-moon-days",
          "reminders",
          "my-practice",
          "my-asanas",
          "check-in-and-diary",
          "my-teacher",
          "my-shala",
          "settings",
          "your-data",
        ]),
        group("For teachers", "Учителям", "teachers", [
          "invite-students",
          "what-you-see",
          "mark-new-asana",
          "announcements",
          "moon-days",
          "directory-line",
        ]),
        group("For shala staff", "Команде шалы", "staff", [
          "create-shala",
          "classes",
          "closures-and-swaps",
          "attendance",
          "announcements",
        ]),
        group("Reference", "Справочник", "reference", [
          "faq",
          "commands",
          "privacy",
          "moon-calculation",
          "whats-new",
        ]),
      ],
    }),
  ],
});
