---
name: i18n-check
description: Check localization completeness. Finds hard-coded user-facing strings and keys missing in en/ru Fluent files. Use before finishing any feature that adds UI text.
disable-model-invocation: true
---
# i18n check
1. List all `.ftl` files under `backend/src/tristhana/i18n/locales/` and `miniapp/src/locales/` (adjust if the layout changed). Parse the message ids per locale.
2. Report keys present in one locale but missing in another.
3. Find keys used in code (`_("key")`, `i18n.get("key")`, `<Localized id="key">`, `l10n.getString("key")`, and so on; check the actual helper names in the code) that don't exist in the `.ftl` files, plus `.ftl` keys that are never used.
4. Grep for likely hard-coded UI strings: Cyrillic literals in `.py`/`.ts(x)` outside tests and locales, `answer("…")`/`send_message(…, "…")` with literal text, and JSX text nodes.
5. Check that Russian plural messages use Fluent selectors with `one`/`few`/`many`.
6. Output a short table of problems and offer to fix them (use the ux-writer agent for the wording).
