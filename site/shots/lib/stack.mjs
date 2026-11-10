// UI-05: a private copy of the product for screenshots: its own database, its own backend on
// its own port and its own Mini App dev server. It never reads backend/.env, never talks to
// the real dev bot, and is thrown away after the run.
import { execFileSync, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

export const DEMO = {
  container: process.env.SHOTS_PG_CONTAINER ?? "tristhana-pg",
  database: "tristhana_demo",
  databaseUrl:
    process.env.SHOTS_DATABASE_URL ?? "postgresql://postgres:dev@127.0.0.1:5432/tristhana_demo",
  apiPort: 8010,
  appPort: 5183,
  secret: "demo-shots",
};
export const API = `http://127.0.0.1:${DEMO.apiPort}`;
export const APP = `http://localhost:${DEMO.appPort}`;

function resetDatabase() {
  // Only ever a database whose name says it is the demo one.
  if (!/_demo$/.test(DEMO.database) || !DEMO.databaseUrl.endsWith(`/${DEMO.database}`)) {
    throw new Error("the shots database must be named *_demo");
  }
  const psql = (/** @type {string} */ sql) =>
    execFileSync("podman", ["exec", DEMO.container, "psql", "-U", "postgres", "-qc", sql], {
      stdio: ["ignore", "ignore", "inherit"],
    });
  psql(`DROP DATABASE IF EXISTS ${DEMO.database} WITH (FORCE)`);
  psql(`CREATE DATABASE ${DEMO.database}`);
}

async function waitFor(/** @type {string} */ url, /** @type {string} */ what, seconds = 60) {
  for (let i = 0; i < seconds * 4; i++) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {
      // not up yet
    }
    await new Promise((done) => setTimeout(done, 250));
  }
  throw new Error(`${what} did not start within ${seconds} s (${url})`);
}

/** Starts everything; resolves to a function that stops it. */
export async function startStack(log = console.log) {
  // A neutral working directory, so the backend finds no `.env` and uses only what follows.
  const cwd = mkdtempSync(join(tmpdir(), "tristhana-shots-"));
  const base = { PATH: process.env.PATH ?? "", HOME: process.env.HOME ?? "" };
  const backendEnv = {
    ...base,
    APP_ENV: "dev",
    LOG_FORMAT: "console",
    LOG_LEVEL: "WARNING",
    DATABASE_URL: DEMO.databaseUrl,
    DEV_INIT_DATA: "true",
    TELEGRAM_MODE: "webhook",
    // Not a real token: the bot answers through the webhook response and never reaches Telegram
    // (the one call it does try, answering a tap, fails harmlessly).
    TELEGRAM_BOT_TOKEN: "1234567:demo-token-not-real",
    TELEGRAM_WEBHOOK_SECRET: DEMO.secret,
    TELEGRAM_BOT_USERNAME: "tristhana_bot",
    MINIAPP_URL: "https://tristhana.web.app",
    FIELD_ENCRYPTION_KEYS: `1:${randomBytes(32).toString("base64")}`,
    INTERNAL_TICK_TOKEN: DEMO.secret,
  };
  const uv = ["run", "--project", join(REPO, "backend")];

  log("demo database: reset and migrate");
  resetDatabase();
  execFileSync("uv", [...uv, "tristhana-migrate"], {
    cwd,
    env: { ...base, DATABASE_URL: DEMO.databaseUrl },
    stdio: ["ignore", "ignore", "pipe"],
  });

  /** @type {import("node:child_process").ChildProcess[]} */
  const children = [];
  const start = (
    /** @type {string} */ command,
    /** @type {string[]} */ args,
    /** @type {import("node:child_process").SpawnOptions} */ options,
  ) => {
    // Own process group, so stopping also stops what uv and npm started.
    const child = spawn(command, args, { ...options, detached: true, stdio: "ignore" });
    children.push(child);
  };
  const stop = () => {
    for (const child of children) {
      try {
        if (child.pid) process.kill(-child.pid, "SIGTERM");
      } catch {
        // already gone
      }
    }
  };

  try {
    const serve = `import uvicorn; uvicorn.run("tristhana.main:app", host="127.0.0.1", port=${DEMO.apiPort}, log_config=None)`;
    start("uv", [...uv, "python", "-c", serve], { cwd, env: backendEnv });
    start("npm", ["run", "dev", "--", "--port", String(DEMO.appPort), "--strictPort"], {
      cwd: join(REPO, "miniapp"),
      env: { ...base, DEV_API_TARGET: API },
    });
    await waitFor(`${API}/api/v1/health/db`, "the demo backend");
    await waitFor(APP, "the Mini App dev server");
    // One scheduler tick computes the stored moon calendars (MD-03); without it the demo
    // world has no moon days. Nobody has reminders due, so it sends nothing.
    const tick = await fetch(`${API}/internal/tick`, {
      method: "POST",
      headers: { "X-Tristhana-Tick-Token": DEMO.secret },
    });
    if (!tick.ok) throw new Error(`the first tick failed (${tick.status})`);
    log(`demo stack up: API ${API}, Mini App ${APP}`);
  } catch (error) {
    stop();
    throw error;
  }
  return stop;
}
