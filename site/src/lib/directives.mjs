// UI-05: Markdown text directives for the guides.
//   :ftl[start-open-app]            → the real button label, in the page's language, in bold
//   :ftl[day-label]{rel=today}      → a message with arguments
//   :ftl[some-key]{from=app}        → when the bot and the app both have the key
//   :cmd[log]                       → /log, checked against the bot's command menu
// An unknown key or command throws, which fails the build.
import { fileURLToPath } from "node:url";
import { LabelError, createLabels, localeOfPath, menuCommands } from "./labels.mjs";

/** @param {{ children?: { type: string, value?: string }[] }} node */
function innerText(node) {
  return (node.children ?? [])
    .map((child) => (child.type === "text" ? (child.value ?? "") : ""))
    .join("")
    .trim();
}

/**
 * A Sätteri mdast plugin entry: called once per file, returns the visitor for that file.
 * @param {{ labels?: ReturnType<typeof createLabels>, commands?: string[] }} [options]
 * @returns {(file: { fileURL?: URL }) => { name: string, textDirective(node: any): any }}
 */
export function guideDirectives(options = {}) {
  const labels = options.labels ?? createLabels();
  const commands = options.commands ?? menuCommands();

  return ({ fileURL }) => {
    // No file (a string rendered outside the collection) reads as an English page.
    const path = fileURL ? fileURLToPath(fileURL) : "(no file)";
    const locale = localeOfPath(path);
    const fail = (/** @type {string} */ message) => new LabelError(`${path}: ${message}`);

    return {
      name: "tristhana-guide-directives",
      /** @param {any} node */
      textDirective(node) {
        if (node.name === "ftl") {
          const { from, ...args } = node.attributes ?? {};
          const key = innerText(node);
          if (!key) throw fail(":ftl[] needs a message key");
          try {
            const value = labels.label(locale, key, args, from ?? undefined);
            return { type: "strong", children: [{ type: "text", value }] };
          } catch (error) {
            if (error instanceof LabelError) throw fail(error.message);
            throw error;
          }
        }
        if (node.name === "cmd") {
          const command = innerText(node);
          if (!commands.includes(command)) {
            throw fail(`:cmd[${command}] is not in the bot's command menu`);
          }
          return { type: "inlineCode", value: `/${command}` };
        }
        return undefined;
      },
    };
  };
}
