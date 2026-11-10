#!/usr/bin/env node
// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: a standalone script run by hand.
/* Mobile side by side: the Expo web export of apps/mobile (served by lonora-api) against the phone
   layout (390x844, dark and light) of docs/ui-reference/Lonora-Desktop-37.html.

   The reference side and the seeding (tests/ui-reference/seed_reference.py) are those of
   side-by-side.mjs; the app side drives the React Native web DOM (data-key rows, role=navigation,
   role=searchbox, role=toolbar, role=dialog). Nothing is mocked. A state that cannot be driven on
   one side is recorded as `skipped: <reason>` instead of failing the run.

     <out>/<state>-390x844-<theme>-{ref,app,diff}.png
     <out>/results.json   mismatch % (or the skip reason) per pair
     <out>/index.md       states x theme table

   Usage (a fresh, migrated *_ci database; the migration needs LONORA_ENCRYPTION_KEY in the env):
     LONORA_DATABASE_URL=postgresql+asyncpg://…/x_ci LONORA_UI_TEST_BROWSER_PATH=/usr/bin/google-chrome \
       node tests/ui-reference/mobile-side-by-side.mjs [--out=DIR] [--only=a,b] [--themes=dark,light]
       [--web=DIR] [--chart=DIR] [--port=8833]
   The Expo export is never rebuilt here (--skip-build is the default and only mode).
*/
import { execFileSync, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdirSync, openSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("@playwright/test");

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const REF_URL = pathToFileURL(join(ROOT, "docs/ui-reference/Lonora-Desktop-37.html")).href;
const args = Object.fromEntries(
  process.argv.slice(2).map((arg) => {
    const [key, value] = arg.replace(/^--/, "").split("=");
    return [key, value ?? true];
  }),
);
const OUT = args.out ?? join(ROOT, ".runtime/mobile-ui-reference/shots");
mkdirSync(OUT, { recursive: true });
const WEB = args.web ?? join(ROOT, ".runtime/mobile-ui-tests");
const CHART = args.chart ?? join(ROOT, ".runtime/chart-renderer-ui-tests");
const PORT = Number(args.port ?? process.env.LONORA_UI_REFERENCE_PORT ?? 8833);
const BASE = `http://localhost:${PORT}`;
const VIEWPORT = [390, 844];
const THEMES = String(args.themes ?? "dark,light").split(",");
const ONLY = args.only ? new Set(String(args.only).split(",")) : null;

const database = process.env.LONORA_DATABASE_URL ?? "";
if (!/\/[a-z0-9][a-z0-9_-]*_ci(\?|$)/i.test(database))
  throw new Error("Set LONORA_DATABASE_URL to a fresh, migrated *_ci database.");
const env = {
  ...process.env,
  NODE_ENV: "production",
  LONORA_DATABASE_URL: database,
  LONORA_COOKIE_SECURE: "false",
  LONORA_ALLOWED_ORIGIN: BASE,
  LONORA_WEB_ROOT: WEB,
  LONORA_CHART_RENDERER_ROOT: CHART,
  LONORA_ARTIFACT_ROOT: join(ROOT, ".runtime/mobile-ui-reference-artifacts"),
  LONORA_BOOTSTRAP_TOKEN: process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-reference-ci-only-2026",
  LONORA_ENCRYPTION_KEY:
    process.env.LONORA_ENCRYPTION_KEY ?? randomBytes(32).toString("base64url").padEnd(44, "="),
  LONORA_UI_TEST_EMAIL: "ahmed@example.com",
  LONORA_UI_TEST_PASSWORD: "ci-only-owner-password",
};
delete env.AI_AGENT;
delete env.CLAUDECODE;

/* ------------------------------------------------------------------ server and seed */
const serverLog = openSync(join(OUT, "server.log"), "w");
const server = spawn(join(ROOT, ".venv/bin/lonora-api"), ["--host", "127.0.0.1", "--port", PORT], {
  cwd: ROOT,
  env,
  stdio: ["ignore", serverLog, serverLog],
});
const stop = () => server.kill("SIGTERM");
process.on("exit", stop);
for (let i = 0; ; i++) {
  try {
    if ((await fetch(`${BASE}/health`)).ok) break;
  } catch {}
  if (i > 120) throw new Error("lonora-api did not start");
  await new Promise((resolve) => setTimeout(resolve, 500));
}
const seed = JSON.parse(
  execFileSync(join(ROOT, ".venv/bin/python"), [join(ROOT, "tests/ui-reference/seed_reference.py")], {
    cwd: ROOT,
    env,
    input: JSON.stringify({ action: "init" }),
    encoding: "utf8",
  }),
);
const csrf = seed.cookies.find((cookie) => cookie.name === "lonora_csrf").value;
const agentKey = (name) => `agent:${seed.agents[name]}`;
const refKey = { gold: "gold", lonora: "lonora", research: "research", friend: "friend" };

/* ------------------------------------------------------------------ browser helpers */
const browser = await chromium.launch(
  process.env.LONORA_UI_TEST_BROWSER_PATH
    ? { executablePath: process.env.LONORA_UI_TEST_BROWSER_PATH }
    : {},
);
async function context(side, theme) {
  const [width, height] = VIEWPORT;
  const ctx = await browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: 1,
    timezoneId: "UTC",
    locale: "ar",
    colorScheme: theme,
    reducedMotion: "no-preference",
  });
  if (side === "app") {
    await ctx.addCookies(
      seed.cookies.map((cookie) => ({
        ...cookie,
        url: BASE,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await ctx.addInitScript(
      ([themeValue]) => {
        localStorage.setItem("lonora.theme", JSON.stringify(themeValue));
        localStorage.setItem("lonora.locale", "ar");
      },
      [theme],
    );
  }
  return ctx;
}
const api = (ctx) => {
  const call = async (method, path, data) => {
    const response = await ctx.request.fetch(`${BASE}/api${path}`, {
      method,
      headers: { "X-CSRF-Token": csrf },
      data,
    });
    if (!response.ok()) throw new Error(`${method} ${path}: ${response.status()}`);
    return response.status() === 204 ? null : response.json();
  };
  return {
    post: (path, data) => call("POST", path, data ?? {}),
    put: (path, data) => call("PUT", path, data),
    del: (path) => call("DELETE", path),
  };
};
const pause = (page, ms) => page.waitForTimeout(ms);
const visible = (page, selector) => page.locator(selector).locator("visible=true").first();

/* Reference: loaded = no skeleton left. */
async function settleRef(page, ms = 450) {
  await page
    .waitForFunction(() => !document.querySelector('#app [aria-busy="true"], .sk-row, .sk'), null, {
      timeout: 8000,
    })
    .catch(() => {});
  await pause(page, ms);
}
async function scrollRef(page, to) {
  await page.evaluate((where) => {
    const el = document.querySelector("#app main#view-scroll, #app main");
    if (!el) return;
    el.scrollTop = where === "end" ? el.scrollHeight : where;
    el.dispatchEvent(new Event("scroll"));
  }, to);
  await pause(page, 600);
}
/* App: the FlatList is the scrollable ancestor of the first row. */
async function scrollApp(page, to) {
  const found = await page.evaluate((where) => {
    let el = document.querySelector("[data-key]");
    while (el && !(el.scrollHeight > el.clientHeight + 1 && /auto|scroll/.test(getComputedStyle(el).overflowY)))
      el = el.parentElement;
    if (!el) return false;
    el.scrollTop = where === "end" ? el.scrollHeight : where;
    el.dispatchEvent(new Event("scroll"));
    return true;
  }, to);
  await pause(page, 600);
  return found;
}
const refRun = (page, fn, arg) => page.evaluate(fn, arg);
const refRow = (page, key) => visible(page, `.thread[data-key="${key}"]`);
const appRow = (page, name) => visible(page, `[data-key="${agentKey(name)}"]`);
const appSearch = (page) => page.getByRole("searchbox", { name: "بحث في Lonora" });
const tap = async (locator) => {
  await locator.click({ timeout: 8000 });
};
async function longPress(page, locator) {
  await locator.waitFor({ state: "visible", timeout: 8000 });
  const box = await locator.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await pause(page, 520);
  await page.mouse.up();
  await pause(page, 400);
}

/* ------------------------------------------------------------------ the states */
const refSearch = (page) => visible(page, "#search");
const STATES = [
  { name: "chats-rest", ref: async () => {}, app: async () => {} },
  {
    name: "filters-revealed",
    ref: (page) => scrollRef(page, 0),
    app: async (page) => {
      if (!(await scrollApp(page, 0))) throw new Error("no scrollable ancestor of [data-key] (FlatList)");
    },
  },
  {
    name: "selection-2",
    ref: async (page) => {
      await refRow(page, refKey.gold).click({ button: "right" });
      await pause(page, 300);
      await refRow(page, refKey.lonora).click();
    },
    app: async (page) => {
      await longPress(page, appRow(page, "gold"));
      await page.getByRole("toolbar").first().waitFor({ timeout: 5000 });
      await tap(appRow(page, "lonora"));
    },
  },
  {
    name: "archived",
    ref: (page) =>
      refRun(page, () => {
        S.archived = { friend: true };
        save();
        go("archived");
      }),
    appSetup: (a) =>
      a.post("/threads/prefs", { thread_ids: [seed.threads.friend], archived: true }),
    app: async (page) => {
      await tap(page.getByTestId("archive-row"));
      await pause(page, 600);
    },
    appTeardown: (a) =>
      a.post("/threads/prefs", { thread_ids: [seed.threads.friend], archived: false }),
  },
  {
    name: "custom-list",
    ref: async (page) => {
      await refRun(page, () => {
        S.lists = [{ id: "l1", name: "العمل", keys: ["gold", "group:team"] }];
        save();
        render();
      });
      await scrollRef(page, 0);
      await visible(page, ".list-chip").click();
    },
    appSetup: async (a, state) => {
      const list = await a.post("/chat-lists", { name: "العمل" });
      await a.put(`/chat-lists/${list.id}/members`, {
        thread_ids: [seed.threads.gold, seed.threads.team],
      });
      state.list = list.id;
    },
    app: async (page) => {
      await scrollApp(page, 0);
      await tap(page.getByText("العمل", { exact: true }).first());
    },
    appTeardown: (a, state) => a.del(`/chat-lists/${state.list}`),
  },
  {
    name: "search-browse",
    ref: (page) => refSearch(page).click(),
    app: (page) => tap(appSearch(page)),
    wait: 1100,
  },
  {
    name: "search-results",
    ref: async (page) => {
      await refSearch(page).click();
      await page.keyboard.type("الذهب");
    },
    app: async (page) => {
      await tap(appSearch(page));
      await page.keyboard.type("الذهب");
    },
    wait: 1400,
  },
  {
    name: "sheet-new-chat",
    ref: (page) => visible(page, '[data-do="new-chat"]').click(),
    app: (page) => tap(page.getByRole("button", { name: "محادثة جديدة" }).first()),
    wait: 900,
  },
  {
    name: "new-list-sheet",
    ref: async (page) => {
      await scrollRef(page, 0);
      await visible(page, ".chip-add").click();
      await pause(page, 500);
    },
    app: async (page) => {
      await scrollApp(page, 0);
      await tap(page.getByRole("button", { name: "قائمة جديدة" }).last());
      await page.getByRole("dialog").first().waitFor({ timeout: 5000 });
    },
    wait: 700,
  },
  {
    name: "agents",
    ref: (page) => refRun(page, () => go("agents")),
    appPath: "/agents",
    appReady: "role=navigation",
    app: async () => {},
  },
  {
    name: "new-agent-template",
    ref: (page) =>
      refRun(page, () => {
        newType = "عام";
        newSup = false;
        newAppearance = defaultAppearance();
        go("agent-type", { item: null });
      }),
    appPath: "/new",
    app: async () => {},
  },
];

/* ------------------------------------------------------------------ diff (canvas, no pixelmatch) */
const differ = await (await browser.newContext()).newPage();
async function diff(refPng, appPng) {
  return differ.evaluate(
    async ([a, b]) => {
      const load = (src) =>
        new Promise((resolve) => {
          const img = new Image();
          img.onload = () => resolve(img);
          img.src = `data:image/png;base64,${src}`;
        });
      const [ia, ib] = await Promise.all([load(a), load(b)]);
      const w = Math.max(ia.width, ib.width);
      const h = Math.max(ia.height, ib.height);
      const pixels = (img) => {
        const c = new OffscreenCanvas(w, h);
        const g = c.getContext("2d");
        g.drawImage(img, 0, 0);
        return g.getImageData(0, 0, w, h).data;
      };
      const pa = pixels(ia);
      const pb = pixels(ib);
      const out = new OffscreenCanvas(w, h);
      const g = out.getContext("2d");
      const data = g.createImageData(w, h);
      let changed = 0;
      for (let i = 0; i < pa.length; i += 4) {
        const y = (r, gg, bb) => r * 0.29889531 + gg * 0.58662247 + bb * 0.11448223;
        const iq = (r, gg, bb) => [
          r * 0.59597799 - gg * 0.2741761 - bb * 0.32180189,
          r * 0.21147017 - gg * 0.52261711 + bb * 0.31114694,
        ];
        const dy = y(pa[i], pa[i + 1], pa[i + 2]) - y(pb[i], pb[i + 1], pb[i + 2]);
        const [ia1, qa] = iq(pa[i], pa[i + 1], pa[i + 2]);
        const [ib1, qb] = iq(pb[i], pb[i + 1], pb[i + 2]);
        const delta = 0.5053 * dy * dy + 0.299 * (ia1 - ib1) ** 2 + 0.1957 * (qa - qb) ** 2;
        const grey = 255 + (y(pa[i], pa[i + 1], pa[i + 2]) - 255) * 0.1;
        if (delta > 35215 * 0.01) {
          changed++;
          data.data.set([255, 0, 0, 255], i);
        } else data.data.set([grey, grey, grey, 255], i);
      }
      g.putImageData(data, 0, 0);
      const blob = await out.convertToBlob({ type: "image/png" });
      const bytes = new Uint8Array(await blob.arrayBuffer());
      let binary = "";
      for (let i = 0; i < bytes.length; i += 0x8000)
        binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      return { mismatch: (100 * changed) / (w * h), png: btoa(binary) };
    },
    [refPng.toString("base64"), appPng.toString("base64")],
  );
}

/* ------------------------------------------------------------------ capture */
async function capture(state, side, theme) {
  const ctx = await context(side, theme);
  const page = await ctx.newPage();
  page.setDefaultTimeout(8000);
  const errors = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  const memo = {};
  const a = api(ctx);
  try {
    if (side === "ref") {
      await page.goto(REF_URL);
      await page.waitForSelector("#app main");
      await page.evaluate((value) => {
        if (S.theme !== value) {
          S.theme = value;
          save();
          render();
        }
      }, theme);
      await settleRef(page);
      await state.ref(page, ctx);
      await settleRef(page, state.wait ?? 600);
    } else {
      if (state.appSetup) await state.appSetup(a, memo);
      await page.goto(BASE + (state.appPath ?? "/"));
      await page.waitForSelector(state.appReady ?? "[data-key]", { timeout: 15000 });
      await pause(page, 800);
      await state.app(page, ctx);
      await pause(page, state.wait ?? 600);
    }
    const png = await page.screenshot({ animations: "disabled", caret: "hide" });
    return { png, errors };
  } catch (error) {
    return { error: String(error).split("\n").slice(0, 3).join(" | "), errors };
  } finally {
    if (side === "app" && state.appTeardown)
      await Promise.resolve()
        .then(() => state.appTeardown(a, memo))
        .catch(() => {});
    await ctx.close();
  }
}

const results = [];
for (const state of STATES) {
  if (ONLY && !ONLY.has(state.name)) continue;
  for (const theme of THEMES) {
    const id = `${state.name}-${VIEWPORT.join("x")}-${theme}`;
    const ref = await capture(state, "ref", theme);
    const app = await capture(state, "app", theme);
    const row = { id, state: state.name, theme };
    if (ref.png) writeFileSync(join(OUT, `${id}-ref.png`), ref.png);
    if (app.png) writeFileSync(join(OUT, `${id}-app.png`), app.png);
    if (ref.png && app.png) {
      const d = await diff(ref.png, app.png);
      writeFileSync(join(OUT, `${id}-diff.png`), Buffer.from(d.png, "base64"));
      row.mismatch = Number(d.mismatch.toFixed(2));
    } else {
      row.skipped = [ref.error && `ref: ${ref.error}`, app.error && `app: ${app.error}`]
        .filter(Boolean)
        .join("; ");
    }
    row.pageErrors = { ref: ref.errors, app: app.errors };
    results.push(row);
    console.log(`${id}: ${row.mismatch ?? "skipped"}${row.skipped ? ` (${row.skipped})` : ""}`);
  }
}
writeFileSync(join(OUT, "results.json"), JSON.stringify(results, null, 1));

const states = [...new Set(results.map((r) => r.state))];
const cell = (state, theme) => {
  const r = results.find((x) => x.state === state && x.theme === theme);
  if (!r) return "";
  return r.mismatch !== undefined ? `${r.mismatch}%` : `skipped: ${r.skipped.replaceAll("|", "/")}`;
};
writeFileSync(
  join(OUT, "index.md"),
  [
    "# Mobile vs reference (390x844), mismatch %",
    "",
    `| state | ${THEMES.join(" | ")} |`,
    `|---|${THEMES.map(() => "---").join("|")}|`,
    ...states.map((s) => `| ${s} | ${THEMES.map((t) => cell(s, t)).join(" | ")} |`),
    "",
  ].join("\n"),
);
await browser.close();
stop();
process.exit(0);
