import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/api/schema.d.ts", "scripts"] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    settings: { react: { version: "detect" } },
  },
  react.configs.flat.recommended,
  react.configs.flat["jsx-runtime"],
  reactHooks.configs.flat.recommended,
  {
    rules: {
      // All UI text comes from Fluent (.ftl), never hard-coded in JSX (NF-01).
      "react/jsx-no-literals": ["error", { noStrings: true, ignoreProps: true }],
      // The generated API types are only used through src/api (ADR-0013).
      "no-restricted-imports": [
        "error",
        { patterns: [{ group: ["**/api/schema"], message: "Use src/api/client.ts." }] },
      ],
    },
  },
  {
    files: ["src/api/**"],
    rules: { "no-restricted-imports": "off" },
  },
  {
    files: ["**/*.test.ts", "**/*.test.tsx", "src/test-setup.ts"],
    rules: { "react/jsx-no-literals": "off" },
  },
  { files: ["eslint.config.js", "vite.config.ts"], ...tseslint.configs.disableTypeChecked },
);
