// UI-05: talks to the demo backend the way the two real clients do. The Mini App side signs
// initData through the dev-only endpoint; the bot side posts Telegram updates to the webhook
// and reads the bot's answer from the response body (ADR-0012), so every text and button in a
// screenshot comes from the real handlers.

/** @typedef {{ id: number, name: string, lang: "en" | "ru" }} DemoUser */
/** @typedef {{ method: string, text?: string, reply_markup?: { inline_keyboard?: { text: string, callback_data?: string, url?: string, web_app?: unknown }[][] } }} BotReply */

export class DemoError extends Error {}

/** @param {{ api: string, secret: string, fetch?: typeof fetch, firstUpdate?: number }} options */
export function createClient({ api, secret, fetch: fetchFn = fetch, firstUpdate = 1000 }) {
  /** @type {Map<number, string>} */
  const signed = new Map();
  // The bot ignores an update id it has already seen, so a second client on the same stack
  // starts higher.
  let updateId = firstUpdate;
  let messageId = 100;

  const from = (/** @type {DemoUser} */ user) => ({
    id: user.id,
    is_bot: false,
    first_name: user.name,
    language_code: user.lang,
  });
  const chat = (/** @type {DemoUser} */ user) => ({
    id: user.id,
    type: "private",
    first_name: user.name,
  });

  async function initData(/** @type {DemoUser} */ user) {
    let value = signed.get(user.id);
    if (!value) {
      const query = new URLSearchParams({
        lang: user.lang,
        first_name: user.name,
        user_id: String(user.id),
      });
      const response = await fetchFn(`${api}/dev/telegram-init-data?${query}`);
      if (!response.ok) {
        throw new DemoError(`dev sign-in is off (${response.status}): is this a demo backend?`);
      }
      value = /** @type {{ init_data: string }} */ (await response.json()).init_data;
      signed.set(user.id, value);
    }
    return value;
  }

  /**
   * One REST call as `user`.
   * @param {DemoUser} user
   * @param {string} method
   * @param {string} path below /api/v1
   * @param {unknown} [body]
   */
  async function call(user, method, path, body) {
    const response = await fetchFn(`${api}/api/v1${path}`, {
      method,
      headers: {
        Authorization: `tma ${await initData(user)}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      throw new DemoError(`${method} ${path} → ${response.status} ${await response.text()}`);
    }
    return response.status === 204 ? null : response.json();
  }

  /** @returns {Promise<BotReply>} */
  async function update(/** @type {Record<string, unknown>} */ payload) {
    const response = await fetchFn(`${api}/telegram/webhook`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Bot-Api-Secret-Token": secret,
      },
      body: JSON.stringify({ update_id: ++updateId, ...payload }),
    });
    const text = await response.text();
    if (!response.ok || !text) {
      throw new DemoError(
        `the bot gave no reply (${response.status}) to ${JSON.stringify(payload)}`,
      );
    }
    return JSON.parse(text);
  }

  /** `user` sends a message (a command when it starts with "/"). */
  function say(/** @type {DemoUser} */ user, /** @type {string} */ text) {
    const command = /^\/\w+/.exec(text);
    return update({
      message: {
        message_id: ++messageId,
        date: Math.floor(Date.now() / 1000),
        chat: chat(user),
        from: from(user),
        text,
        ...(command
          ? { entities: [{ type: "bot_command", offset: 0, length: command[0].length }] }
          : {}),
      },
    });
  }

  /** `user` taps the button of `reply` whose label contains `label`, or button number `label`. */
  function tap(
    /** @type {DemoUser} */ user,
    /** @type {BotReply} */ reply,
    /** @type {string | number} */ label,
  ) {
    const buttons = (reply.reply_markup?.inline_keyboard ?? []).flat();
    const tappable = buttons.filter((b) => b.callback_data);
    const button =
      typeof label === "number"
        ? tappable[label - 1]
        : (tappable.find((b) => b.text === label) ?? tappable.find((b) => b.text.includes(label)));
    if (!button) {
      throw new DemoError(
        `no button "${label}" among: ${buttons.map((b) => b.text).join(" · ") || "(none)"}`,
      );
    }
    return update({
      callback_query: {
        id: String(++updateId),
        chat_instance: "demo",
        from: from(user),
        data: button.callback_data,
        message: {
          message_id: ++messageId,
          date: Math.floor(Date.now() / 1000),
          chat: chat(user),
          from: { id: 1, is_bot: true, first_name: "Tristhana" },
          text: reply.text ?? "",
        },
      },
    });
  }

  return { call, say, tap };
}
