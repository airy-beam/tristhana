// UI-05: draws one bot message as a small HTML page: the text bubble and its inline buttons.
// It is plainly a drawing in the site's own style, not a copy of Telegram's interface.

/** @typedef {import("./client.mjs").BotReply} BotReply */

const escape = (/** @type {string} */ text) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** Bot texts use Telegram's HTML subset (<b>, <i>, <a>, <code>); anything else is shown as text. */
function messageHtml(/** @type {string} */ text) {
  return escape(text)
    .replace(/&lt;(\/?)(b|i|u|s|code)&gt;/g, "<$1$2>")
    .replace(/&lt;a href=&quot;[^&]*&quot;&gt;/g, '<span class="link">')
    .replace(/&lt;\/a&gt;/g, "</span>")
    .replace(/(^|\s)(\/[a-z_]+)/g, '$1<span class="link">$2</span>');
}

/**
 * @param {BotReply} reply
 * @param {{ said?: string, lang?: string }} [options] `said`: what the person sent, drawn above
 */
export function botHtml(reply, options = {}) {
  const rows = reply.reply_markup?.inline_keyboard ?? [];
  const keyboard = rows
    .map(
      (row) =>
        `<div class="row">${row
          .map((button) => `<span class="button">${escape(button.text)}</span>`)
          .join("")}</div>`,
    )
    .join("");
  const said = options.said ? `<div class="said">${escape(options.said)}</div>` : "";
  return `<!doctype html>
<html lang="${options.lang ?? "en"}">
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; }
  body { font: 16px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif;
    background: #efe7d6; color: #1c1f4d; padding: 16px; width: 390px; }
  #shot { display: flex; flex-direction: column; gap: 6px; }
  .said { align-self: flex-end; background: #dfe1f8; border-radius: 16px 16px 4px 16px;
    padding: 8px 12px; margin-bottom: 4px; max-width: 80%; }
  .bubble { align-self: flex-start; background: #fbf7ee; border-radius: 16px 16px 16px 4px;
    padding: 10px 12px; max-width: 92%; white-space: pre-wrap; overflow-wrap: anywhere;
    box-shadow: 0 1px 1px rgb(28 31 77 / 12%); }
  .link { color: #3d43a6; }
  .keyboard { display: flex; flex-direction: column; gap: 4px; width: 92%; }
  .row { display: flex; gap: 4px; }
  .button { flex: 1; text-align: center; padding: 9px 6px; border-radius: 8px;
    background: rgb(28 31 77 / 10%); font-size: 14.5px; min-width: 0; }
</style>
<div id="shot">${said}<div class="bubble">${messageHtml(reply.text ?? "")}</div>${
    keyboard ? `<div class="keyboard">${keyboard}</div>` : ""
  }</div>
</html>
`;
}
