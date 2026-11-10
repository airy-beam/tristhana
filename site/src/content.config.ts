import { defineCollection } from "astro:content";
import { z } from "astro/zod";
import { docsLoader } from "@astrojs/starlight/loaders";
import { docsSchema } from "@astrojs/starlight/schema";

export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        // UI-05: requirement IDs a page documents; `guide-update <ID>` finds its pages by these.
        features: z.array(z.string().regex(/^[A-Z]{2}-\d{2}$/)).default([]),
      }),
    }),
  }),
};
