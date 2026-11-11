#!/usr/bin/env node
// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: a standalone script run by hand.
/* Side by side: UI phase 2 against docs/ui-reference/Lonora-Desktop-37.html.

   The REFERENCE renders from file:// with its own localStorage demo state (`initial`). The APP is
   the production web build served by lonora-api against a fresh *_ci database that
   tests/ui-reference/seed_reference.py fills through the API with the same owner, agents, group,
   messages and unread state. Each state is captured on both sides at 390x844 and 1280x800, dark
   and light, then compared:

     <out>/<state>-<viewport>-<theme>-{ref,app}.png   the pair
     <out>/<state>-<viewport>-<theme>-diff.png        changed pixels in red over a dimmed reference
     <out>/results.json                                mismatch % per pair, a computed-style probe of
                                                       the reference's own class names on both sides,
                                                       the words each side shows that the other does
                                                       not, and every /api request the app made
     <out>/bindings.json                               the list actions done through the app's UI and
                                                       the routes they hit (no DELETE of agents,
                                                       groups or threads; «حذف» keeps the group)

   Nothing on the app side is mocked: no request is intercepted. The update bar is raised the way a
   deploy raises it (a new build.json next to the SPA); offline is the browser's offline mode.

   Usage (a fresh, migrated *_ci database; this script refuses anything else; the migration needs
   LONORA_ENCRYPTION_KEY and LONORA_BOOTSTRAP_TOKEN in the environment, the script reuses them):
     psql "$ADMIN_URL" -c "CREATE DATABASE lonora_uiref_ci OWNER lonora"
     LONORA_DATABASE_URL=postgresql+asyncpg://…/lonora_uiref_ci bash scripts/migrate.sh
     LONORA_DATABASE_URL=… LONORA_UI_TEST_BROWSER_PATH=/usr/bin/google-chrome \
       env -u AI_AGENT -u CLAUDECODE node tests/ui-reference/side-by-side.mjs [--out=DIR]
       [--only=state,state] [--viewports=390x844,1280x800] [--themes=dark,light] [--skip-build]
       [--no-bindings]
     psql "$ADMIN_URL" -c "DROP DATABASE lonora_uiref_ci"
   A database the script seeded can be reused with --no-bindings (the bindings pass hides the
   group's history and chats-scrolled adds eight agents, so a full comparison wants a fresh one).
   The app sets `inert` on the shell behind an open sheet, so with a sheet open the probe reports
   the background elements as missing on the app side: compare the dialog entries only.
*/
import { execFileSync, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdirSync, openSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { DOMAIN_PROBES, domainStates } from "./domain-states.mjs";

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
const OUT = args.out ?? join(ROOT, ".runtime/ui-reference/shots");
mkdirSync(OUT, { recursive: true });
const WEB = join(ROOT, ".runtime/ui-reference-web");
const PORT = Number(process.env.LONORA_UI_REFERENCE_PORT ?? 8832);
const BASE = `http://localhost:${PORT}`;
const VIEWPORTS = String(args.viewports ?? "390x844,1280x800")
  .split(",")
  .map((v) => v.split("x").map(Number));
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
  LONORA_CHART_RENDERER_ROOT: WEB,
  LONORA_ARTIFACT_ROOT: join(ROOT, ".runtime/ui-reference-artifacts"),
  LONORA_BOOTSTRAP_TOKEN: process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-reference-ci-only-2026",
  LONORA_ENCRYPTION_KEY:
    process.env.LONORA_ENCRYPTION_KEY ?? randomBytes(32).toString("base64url").padEnd(44, "="),
  LONORA_UI_TEST_EMAIL: "ahmed@example.com",
  LONORA_UI_TEST_PASSWORD: "ci-only-owner-password",
};
// pnpm must not see an agent session (it would rewrite AGENTS.md).
delete env.AI_AGENT;
delete env.CLAUDECODE;

/* ------------------------------------------------------------------ server, build and seed */
if (!args["skip-build"])
  execFileSync(
    "pnpm",
    [
      "--filter",
      "@lonora/web",
      "exec",
      "vite",
      "build",
      "--outDir",
      "../../.runtime/ui-reference-web",
      "--emptyOutDir",
    ],
    { cwd: ROOT, env, stdio: "inherit" },
  );
const buildFile = join(WEB, "build.json");
const servedBuild = readFileSync(buildFile, "utf8");
const serverLog = openSync(join(OUT, "server.log"), "w");
const server = spawn(join(ROOT, ".venv/bin/lonora-api"), ["--host", "127.0.0.1", "--port", PORT], {
  cwd: ROOT,
  env,
  stdio: ["ignore", serverLog, serverLog],
});
const stop = () => {
  writeFileSync(buildFile, servedBuild);
  server.kill("SIGTERM");
};
process.on("exit", stop);
for (let i = 0; ; i++) {
  try {
    if ((await fetch(`${BASE}/health`)).ok) break;
  } catch {}
  if (i > 120) throw new Error("lonora-api did not start");
  await new Promise((resolve) => setTimeout(resolve, 500));
}
const seed = JSON.parse(
  execFileSync(
    join(ROOT, ".venv/bin/python"),
    [join(ROOT, "tests/ui-reference/seed_reference.py")],
    {
      cwd: ROOT,
      env,
      input: JSON.stringify({ action: "init" }),
      encoding: "utf8",
    },
  ),
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
/* The on-screen keyboard, the same way on both sides: the visual viewport loses `window.__kb`
   pixels at the bottom and announces it with a resize, as a phone's keyboard does. */
const keyboard = () => {
  const proto = Object.getPrototypeOf(window.visualViewport);
  const height = Object.getOwnPropertyDescriptor(proto, "height");
  Object.defineProperty(proto, "height", {
    get() {
      return height.get.call(this) - (window.__kb || 0);
    },
  });
};
async function context(side, [width, height], theme, locale = "ar") {
  const ctx = await browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: 1,
    timezoneId: "UTC",
    locale: "ar",
    colorScheme: theme,
    reducedMotion: "no-preference",
  });
  await ctx.addInitScript(keyboard);
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
      ([themeValue, localeValue]) => {
        localStorage.setItem("lonora.theme", JSON.stringify(themeValue));
        localStorage.setItem("lonora.locale", localeValue);
      },
      [theme, locale],
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
    get: (path) => call("GET", path),
    post: (path, data) => call("POST", path, data ?? {}),
    put: (path, data) => call("PUT", path, data),
    del: (path) => call("DELETE", path),
  };
};
const pause = (page, ms) => page.waitForTimeout(ms);
/* Loaded: the first row painted and no skeleton left (the reference's timers, the app's queries). */
async function settle(page, ms = 450) {
  await page
    .waitForFunction(() => !document.querySelector('#app [aria-busy="true"], .sk-row, .sk'), null, {
      timeout: 8000,
    })
    .catch(() => {});
  await pause(page, ms);
}
const visible = (page, selector) => page.locator(selector).locator("visible=true").first();
const desktop = (page) => page.viewportSize().width >= 900;
const scroller = (page) =>
  desktop(page) ? "#app .desktop-threads" : "#app main#view-scroll, #app main";
async function scrollTo(page, where) {
  await page.evaluate(
    ([selector, to]) => {
      const el = document.querySelector(selector);
      if (!el) return;
      el.scrollTop = to === "end" ? el.scrollHeight : to;
      el.dispatchEvent(new Event("scroll"));
    },
    [scroller(page), where],
  );
  await pause(page, 600);
}
async function raiseKeyboard(page) {
  await page.evaluate(() => {
    window.__kb = 300;
    window.visualViewport.dispatchEvent(new Event("resize"));
  });
  await pause(page, 500);
}

/* ------------------------------------------------------------------ the states */
const MORE_AGENTS = [
  ["مراقب الأخبار", "متابعة الأخبار المهمة"],
  ["منظّم البريد", "ترتيب الرسائل والردود"],
  ["محلل البيانات", "قراءة الأرقام والتقارير"],
  ["مساعد السفر", "الحجوزات والمواعيد"],
  ["كاتب التقارير", "صياغة الملخصات"],
  ["مدرّب اللغة", "تمارين يومية"],
  ["متتبّع المصاريف", "متابعة الميزانية"],
  ["مساعد القراءة", "تلخيص الكتب"],
];
const refRun = (page, fn, arg) => page.evaluate(fn, arg);
const refRow = (page, key) => visible(page, `.thread[data-key="${key}"]`);
const appRow = (page, name) => visible(page, `.thread[data-key="${agentKey(name)}"]`);
let conversationSeeded = false;
const seedConversation = () => {
  if (conversationSeeded) return;
  execFileSync(
    join(ROOT, ".venv/bin/python"),
    [join(ROOT, "tests/ui-reference/seed_reference.py")],
    { cwd: ROOT, env, input: JSON.stringify({ action: "conversation" }), encoding: "utf8" },
  );
  conversationSeeded = true;
};
const CONVERSATION_MD =
  '## ملخص الفائدة\n- ثبّت البنك المركزي السعر هذا الأسبوع\n- تميل التوقعات إلى خفض في الربع القادم\n\n```json\n{"rate": 5.25, "next": "cut"}\n```';
async function refConversation(page) {
  await refRun(
    page,
    (md) => {
      const day = new Date();
      const at = (h, m) =>
        Date.UTC(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate(), h, m);
      S.messages.research = [
        {
          id: "c1",
          sender: "user",
          text: "لخّص لي آخر تقرير عن الفائدة",
          time: "09:10",
          at: at(9, 10),
          status: "read",
        },
        {
          id: "c2",
          sender: "agent",
          agent: "research",
          text: md,
          time: "09:11",
          at: at(9, 11),
          reactions: { user: "👍" },
        },
        {
          id: "c3",
          sender: "user",
          text: "اشرح لي الكود باختصار",
          time: "09:12",
          at: at(9, 12),
          status: "read",
          reply: { id: "c2", sender: "agent", agent: "research", text: "## ملخص الفائدة" },
        },
        {
          id: "c4",
          sender: "agent",
          agent: "research",
          kind: "error",
          err: { type: "rate" },
          time: "09:12",
          at: at(9, 12),
        },
        {
          id: "c5",
          sender: "agent",
          agent: "research",
          kind: "call",
          call: { dir: "in", missed: true },
          text: "مكالمة صوتية فائتة",
          time: "09:20",
          at: at(9, 20),
        },
      ];
      save();
    },
    CONVERSATION_MD,
  );
  await refRow(page, refKey.research).click();
  await pause(page, 700);
}
const STATES = [
  {
    // Phone: filters rest hidden above the list. Desktop: the two panes with the welcome.
    name: "chats-rest",
    ref: async () => {},
    app: async () => {},
  },
  {
    name: "filters-revealed",
    ref: (page) => scrollTo(page, 0),
    app: (page) => scrollTo(page, 0),
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
    appPath: "/app/archived",
    app: async () => {},
    appTeardown: (a) =>
      a.post("/threads/prefs", { thread_ids: [seed.threads.friend], archived: false }),
  },
  {
    name: "selection-2",
    ref: async (page) => {
      await refRow(page, refKey.gold).click({ button: "right" });
      await pause(page, 300);
      await refRow(page, refKey.lonora).click();
    },
    app: async (page) => {
      await appRow(page, "gold").click({ button: "right" });
      await pause(page, 300);
      await appRow(page, "lonora").click();
    },
  },
  {
    name: "custom-list",
    ref: async (page) => {
      await refRun(page, () => {
        S.lists = [{ id: "l1", name: "العمل", keys: ["gold", "group:team"] }];
        save();
        render();
      });
      if (!desktop(page)) await scrollTo(page, 0);
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
      if (!desktop(page)) await scrollTo(page, 0);
      await visible(page, ".list-chip").click();
    },
    appTeardown: (a, state) => a.del(`/chat-lists/${state.list}`),
  },
  {
    name: "search-browse",
    ref: (page) => visible(page, desktop(page) ? "#desktop-search" : "#search").click(),
    app: (page) => visible(page, desktop(page) ? "#desktop-search" : "#search").click(),
    wait: 1100,
  },
  {
    name: "search-results",
    ref: async (page) => {
      await visible(page, desktop(page) ? "#desktop-search" : "#search").click();
      await page.keyboard.type("الذهب");
    },
    app: async (page) => {
      await visible(page, desktop(page) ? "#desktop-search" : "#search").click();
      await page.keyboard.type("الذهب");
    },
    wait: 1400,
  },
  {
    // A bottom sheet at its content detent (phones) / the centred modal (desktop).
    name: "sheet-new-chat",
    ref: (page) => visible(page, '[data-do="new-chat"]').click(),
    app: (page) =>
      visible(
        page,
        '.topbar button[aria-label="محادثة جديدة"], .desktop-list button[aria-label="محادثة جديدة"]',
      ).click(),
    wait: 900,
  },
  {
    // The expandable sheet (the market chart) resting at its content height …
    name: "sheet-detent-rest",
    ref: (page) => refRun(page, () => chart()),
    appPath: () => `/app/${seed.agents.gold}`,
    app: async (page) => {
      await visible(page, 'button[aria-label="قائمة المحادثة"]').click();
      await pause(page, 500);
      await visible(page, "dialog .row:has-text('الشارت')").click();
    },
    wait: 1600,
  },
  {
    // … and raised to the top (⤢).
    name: "sheet-detent-expanded",
    ref: async (page) => {
      await refRun(page, () => chart());
      await pause(page, 900);
      await visible(page, "dialog .sheet-expand").click();
    },
    appPath: () => `/app/${seed.agents.gold}`,
    app: async (page) => {
      await visible(page, 'button[aria-label="قائمة المحادثة"]').click();
      await pause(page, 500);
      await visible(page, "dialog .row:has-text('الشارت')").click();
      await pause(page, 900);
      await visible(page, "dialog .sheet-expand").click();
    },
    wait: 1600,
  },
  {
    name: "new-list-keyboard",
    ref: async (page) => {
      if (!desktop(page)) await scrollTo(page, 0);
      await visible(page, ".chip-add").click();
      await pause(page, 500);
      await raiseKeyboard(page);
    },
    app: async (page) => {
      if (!desktop(page)) await scrollTo(page, 0);
      await visible(page, ".chip-add").click();
      await pause(page, 500);
      await raiseKeyboard(page);
    },
    wait: 700,
  },
  {
    // Offline: the strip with the queued count, and the message waiting with its clock.
    name: "offline-queued",
    ref: async (page, ctx) => {
      await refRow(page, refKey.lonora).click();
      await pause(page, 700);
      await ctx.setOffline(true);
      await pause(page, 300);
      await visible(page, ".composer textarea").fill("أرسل لي موجز اليوم");
      await page.keyboard.press("Enter");
    },
    appPath: () => `/app/${seed.agents.lonora}`,
    app: async (page, ctx) => {
      await ctx.setOffline(true);
      await pause(page, 300);
      await visible(page, "textarea").fill("أرسل لي موجز اليوم");
      await page.keyboard.press("Enter");
    },
    wait: 1200,
  },
  {
    name: "update-bar",
    ref: (page) => refRun(page, () => updateBar(true)),
    // A newer build is deployed while this bundle runs.
    appSetup: () => writeFileSync(buildFile, JSON.stringify({ build: "deployed-later" })),
    app: async () => {},
    appTeardown: () => writeFileSync(buildFile, servedBuild),
    wait: 1200,
  },
  {
    name: "not-found",
    ref: (page) => refRun(page, () => go("missing-page")),
    appPath: "/app/missing/page",
    app: async () => {},
  },
  /* ---- phase 3: the conversation. The research agent's chat holds the same five messages on
     both sides: a question, a Markdown answer with a code block and the owner's 👍, a reply
     quoting it, a failed reply (rate limit) and a missed call. */
  {
    name: "chat-rich",
    ref: (page) => refConversation(page),
    appSetup: () => seedConversation(),
    appPath: () => `/app/${seed.agents.research}`,
    app: async () => {},
    wait: 1200,
  },
  {
    name: "chat-msg-menu",
    ref: async (page) => {
      await refConversation(page);
      await visible(page, ".msg.theirs .md").click({ button: "right" });
    },
    appSetup: () => seedConversation(),
    appPath: () => `/app/${seed.agents.research}`,
    app: (page) => visible(page, ".msg.theirs .md").click({ button: "right" }),
    wait: 700,
  },
  {
    name: "chat-tools-sheet",
    ref: async (page) => {
      await refConversation(page);
      await visible(page, ".composer .cbtn").click();
    },
    appSetup: () => seedConversation(),
    appPath: () => `/app/${seed.agents.research}`,
    app: (page) => visible(page, ".composer .cbtn").click(),
    wait: 900,
  },
  {
    name: "chat-permission-menu",
    ref: async (page) => {
      await refRow(page, refKey.gold).click();
      await pause(page, 700);
      await visible(page, ".composer .mode-chip").click();
    },
    appPath: () => `/app/${seed.agents.gold}`,
    app: (page) => visible(page, ".composer .mode-chip").click(),
    wait: 900,
  },
  // UI phase 5: settings, usage, the lock and the auth screens (pixel % is a report only: the
  // reference's demo data and its «حول» row, plans and data actions are not in the app, Q48-Q54).
  {
    name: "settings-root",
    ref: (page) => refRun(page, () => go("settings")),
    appPath: "/app/settings",
    app: async () => {},
  },
  {
    name: "settings-owner",
    ref: (page) => refRun(page, () => go("owner")),
    appPath: "/app/owner",
    app: async () => {},
  },
  {
    name: "settings-notify",
    ref: (page) => refRun(page, () => go("notify-settings")),
    appPath: "/app/notify-settings",
    app: async () => {},
  },
  {
    name: "settings-integrations",
    ref: (page) => refRun(page, () => go("integrations")),
    appPath: "/app/integrations",
    app: async () => {},
  },
  {
    name: "settings-privacy",
    ref: (page) => refRun(page, () => go("privacy")),
    appPath: "/app/privacy",
    app: async () => {},
  },
  {
    name: "settings-storage",
    ref: (page) => refRun(page, () => go("storage")),
    appPath: "/app/storage",
    app: async () => {},
  },
  {
    name: "settings-a11y",
    ref: (page) => refRun(page, () => go("accessibility")),
    appPath: "/app/accessibility",
    app: async () => {},
  },
  {
    name: "usage",
    ref: (page) => refRun(page, () => go("usage")),
    appPath: "/app/usage",
    app: async () => {},
    wait: 900,
  },
  {
    name: "broker-form",
    ref: (page) => refRun(page, () => go("broker")),
    appPath: "/app/broker",
    app: async () => {},
  },
  {
    name: "lock",
    ref: (page) => refRun(page, () => lockOpen("set")),
    appPath: "/app/privacy",
    app: async (page) => {
      await page.getByRole("switch").first().click();
    },
  },
  // Phase 4a: the agent pages (agents.page, agent.page.*, agent.identity.form, group.*,
  // trades.page, recovery.page). Each opens straight on its route on both sides.
  {
    name: "agents-page",
    ref: (page) => refRun(page, () => go("agents")),
    appPath: "/app/agents",
    app: async () => {},
  },
  {
    name: "agent-trader",
    ref: (page) => refRun(page, () => go("agent", { agent: "gold" })),
    appPath: () => `/app/agent/${seed.agents.gold}`,
    app: async () => {},
    wait: 900,
  },
  {
    // Q38: Lonora's page has no «إيقاف الوكيل».
    name: "agent-lonora",
    ref: (page) => refRun(page, () => go("agent", { agent: "lonora" })),
    appPath: () => `/app/agent/${seed.agents.lonora}`,
    app: async () => {},
    wait: 900,
  },
  {
    name: "agent-research",
    ref: (page) => refRun(page, () => go("agent", { agent: "research" })),
    appPath: () => `/app/agent/${seed.agents.research}`,
    app: async () => {},
    wait: 900,
  },
  {
    name: "avatar-sheet",
    ref: async (page) => {
      await refRun(page, () => go("agent", { agent: "gold" }));
      await pause(page, 400);
      await visible(page, ".pencil").click();
    },
    appPath: () => `/app/agent/${seed.agents.gold}`,
    app: async (page) => {
      await pause(page, 400);
      await visible(page, ".pencil").click();
    },
    wait: 900,
  },
  {
    name: "identity-trader",
    ref: (page) => refRun(page, () => go("identity", { agent: "gold" })),
    appPath: () => `/app/identity/${seed.agents.gold}`,
    app: async () => {},
    wait: 1100,
  },
  {
    name: "group-page",
    ref: (page) => refRun(page, () => go("group", { item: "team", thread: "team" })),
    appPath: () => `/app/group/${seed.group}`,
    app: async () => {},
  },
  {
    name: "new-group",
    ref: (page) => refRun(page, () => go("new-group")),
    appPath: "/app/new-group",
    app: async () => {},
  },
  {
    name: "new-agent-templates",
    ref: (page) => refRun(page, () => go("agent-type")),
    appPath: "/app/new-agent",
    app: async () => {},
  },
  {
    name: "trades-trader",
    ref: (page) => refRun(page, () => go("trades", { agent: "gold" })),
    appPath: () => `/app/trades/${seed.agents.gold}`,
    app: async () => {},
    wait: 1100,
  },
  {
    // The app shows the broker session's real state: the seeded simulation is connected.
    name: "recovery",
    ref: (page) => refRun(page, () => go("recovery")),
    appPath: "/app/recovery",
    app: async () => {},
  },
  {
    // The topbar edge (glass fades in) and the «Lonora» title folding away. The demo's five rows
    // cannot scroll, so both sides get the same eight more agents (the app keeps them: last state).
    name: "chats-scrolled",
    ref: async (page) => {
      await refRun(
        page,
        (more) => {
          for (const [i, [name, role]] of more.entries())
            S.agents.push({ id: `more${i}`, name, role, type: "عام", symbol: "", on: true });
          render();
        },
        MORE_AGENTS,
      );
      await scrollTo(page, "end");
    },
    appSetup: async (a) => {
      const names = new Set((await a.get("/agents")).map((agent) => agent.name));
      for (const [name, role] of MORE_AGENTS)
        if (!names.has(name))
          await a.post("/agents/create", { template: "general", name, responsibility: role });
    },
    app: (page) => scrollTo(page, "end"),
  },
];
// UI phase 4b: the domain pages (seeded by seed_domain.py).
STATES.push(...domainStates({ ROOT, env, seed, refRun, visible, pause }));

/* ------------------------------------------------------------------ probes */
/* The app reuses the reference's class names: the same selectors, measured on both sides. */
const PROBES = [
  ".chat-head",
  ".chat-name",
  ".presence",
  ".msg",
  ".msg-line",
  ".bubble",
  ".msg.mine .bubble",
  ".msg.theirs .bubble",
  ".meta",
  ".ticks",
  ".sender",
  ".quote",
  ".quote-name",
  ".reacts",
  ".md",
  ".md .md-h",
  ".code",
  ".code-head",
  ".code pre",
  ".err-card",
  ".call-bubble",
  ".date span",
  ".composer",
  ".composer-card",
  ".composer textarea",
  ".composer .cbtn",
  ".composer .mode-chip",
  ".composer .no-trade",
  ".composer .send",
  ".composer .voice",
  ".pop.msg-pop",
  ".react-row",
  ".react-btn",
  ".pop.mode-pop",
  ".pop-opt",
  ".add-tile",
  ".add-row",
  ".prefs-row",
  ".lang-select",
  ".theme-switch",
  ".signout .row",
  ".reach-opt",
  ".reach-times input",
  ".switch",
  ".u-hero",
  ".u-figure",
  ".u-kpi",
  ".u-rank-row",
  ".u-bars",
  ".store-hero",
  ".store-bar",
  ".pf-log .row",
  ".lk-key",
  ".lk-dots i",
  ".topbar",
  ".topbar header",
  ".topbar h1",
  ".header-search",
  ".header-search input",
  ".list-filters",
  ".list-filters .chip",
  ".list-filters .chip.active",
  ".chip-add",
  ".thread",
  ".thread .av-wrap",
  ".thread .line1 strong",
  ".thread .line1 time",
  ".thread .line2",
  ".thread .pv",
  ".thread .count",
  ".thread.picked",
  ".thread .pick",
  ".archive-row",
  ".arch-note",
  ".sel-bar",
  "nav",
  "nav button",
  ".nav-lens",
  ".nav-badge",
  ".large-title",
  ".float-back",
  ".desktop-rail",
  ".rail-brand",
  ".desktop-list",
  ".list-search",
  ".list-search > svg",
  ".list-search input",
  ".desktop-threads",
  ".welcome",
  ".welcome .logo-hero",
  ".welcome h2",
  ".welcome p",
  ".welcome .group",
  ".welcome .row",
  ".welcome small",
  "dialog[open]",
  "dialog[open] .sheet-top",
  "dialog[open] .handle",
  "dialog[open] h2",
  "dialog[open] .row",
  "dialog[open] input",
  "#update-bar",
  ".net-strip",
  ".state-page",
  ".state-page h2",
  ".state-page p",
  ".state-page .btn",
  "#toast",
  ".search-tabs",
  ".s-sec, .search-section",
];
const PROPS = [
  "display",
  "position",
  "font-family",
  "font-size",
  "font-weight",
  "line-height",
  "letter-spacing",
  "color",
  "background-color",
  "border-radius",
  "border-top-width",
  "border-bottom-width",
  "border-bottom-color",
  "padding-top",
  "padding-right",
  "padding-bottom",
  "padding-left",
  "margin-top",
  "margin-bottom",
  "gap",
  "box-shadow",
  "opacity",
  "transform",
  "backdrop-filter",
  "direction",
  "text-align",
  "transition-duration",
  "transition-timing-function",
  "transition-property",
];
/* Rows are measured by conversation, whatever order each side lists them in. */
const ROW_PARTS = ["", " .av-wrap", " .line1 strong", " .line1 time", " .pv", " .count"];
const rowProbes = (side) =>
  Object.entries(refKey)
    .map(([name, key]) => [name, side === "ref" ? key : agentKey(name)])
    .concat([["team", side === "ref" ? "group:team" : `group:${seed.group}`]])
    .flatMap(([name, key]) =>
      ROW_PARTS.map((part) => [`row:${name}${part}`, `.thread[data-key="${key}"]${part}`]),
    );
async function probe(page, side, extra = []) {
  return page.evaluate(
    ([selectors, props]) => {
      const out = {};
      for (const entry of selectors) {
        const [label, selector] = Array.isArray(entry) ? entry : [entry, entry];
        const el = [...document.querySelectorAll(selector)].find((node) => {
          const r = node.getBoundingClientRect();
          return r.width > 0 && r.height > 0 && !node.closest("[inert],[aria-hidden=true]");
        });
        if (!el) continue;
        const r = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        out[label] = {
          rect: [r.x, r.y, r.width, r.height].map((n) => Math.round(n)),
          count: document.querySelectorAll(selector).length,
          ...Object.fromEntries(props.map((p) => [p, style.getPropertyValue(p)])),
        };
      }
      return out;
    },
    [[...PROBES, ...extra, ...rowProbes(side)], PROPS],
  );
}
function probeDiff(ref, app) {
  const rows = [];
  for (const selector of new Set([...Object.keys(ref), ...Object.keys(app)])) {
    const a = ref[selector];
    const b = app[selector];
    if (!a || !b) {
      rows.push({ selector, missing: a ? "app" : "ref" });
      continue;
    }
    const diffs = {};
    for (const key of Object.keys(a)) {
      if (key === "font-family") continue;
      if (
        key === "border-bottom-color" &&
        a["border-bottom-width"] === "0px" &&
        b["border-bottom-width"] === "0px"
      )
        continue;
      if (key === "count" && selector.startsWith("row:")) continue;
      const same =
        key === "rect"
          ? a.rect.every((n, i) => Math.abs(n - b.rect[i]) <= 1)
          : String(a[key]) === String(b[key]);
      if (!same) diffs[key] = { ref: a[key], app: b[key] };
    }
    if (Object.keys(diffs).length) rows.push({ selector, diffs });
  }
  return rows;
}
/* Every word a side shows (text and accessible names), to catch a changed Arabic term. */
async function words(page) {
  return page.evaluate(() => {
    const seen = new Set();
    const roots = [document.querySelector("#app"), document.querySelector("dialog[open]")];
    for (const extra of ["#toast", "#update-bar", "#headsup"])
      roots.push(document.querySelector(extra));
    for (const root of roots.filter(Boolean)) {
      const walker = document.createTreeWalker(
        root,
        NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,
      );
      for (let node = walker.currentNode; node; node = walker.nextNode()) {
        const el = node.nodeType === 1 ? node : node.parentElement;
        if (!el || el.closest('[aria-hidden="true"],[inert],.pager-ghost,template,script,style'))
          continue;
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        const text =
          node.nodeType === 3
            ? node.textContent
            : [el.getAttribute("aria-label"), el.getAttribute("placeholder")]
                .filter(Boolean)
                .join(" ");
        for (const word of (text || "").split(/[\s·«»:,.؟?!()]+/))
          if (/[؀-ۿ]/.test(word)) seen.add(word);
      }
    }
    return [...seen];
  });
}

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
        // pixelmatch's YIQ colour distance, threshold 0.1 of the maximum.
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
async function capture(state, side, viewport, theme) {
  const ctx = await context(side, viewport, theme);
  const page = await ctx.newPage();
  const requests = [];
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
      await settle(page);
      await state.ref(page, ctx);
    } else {
      page.on("requestfinished", async (request) => {
        const url = new URL(request.url());
        if (!url.pathname.startsWith("/api/")) return;
        const response = await request.response();
        requests.push({
          method: request.method(),
          path: url.pathname + url.search,
          status: response?.status(),
          fromServiceWorker: response?.fromServiceWorker() ?? false,
        });
      });
      if (state.appSetup) await state.appSetup(a, memo);
      const path =
        typeof state.appPath === "function" ? state.appPath() : (state.appPath ?? "/app");
      await page.goto(BASE + path);
      await page.waitForSelector("#app main", { timeout: 15000 });
      await settle(page);
      await state.app(page, ctx);
    }
    await settle(page, state.wait ?? 600);
    const png = await page.screenshot({ animations: "disabled", caret: "hide" });
    // The domain pages' own classes are probed on their states only.
    const extra = state.domain ? DOMAIN_PROBES : [];
    return {
      png,
      probe: await probe(page, side, extra),
      words: await words(page),
      requests,
      errors,
    };
  } catch (error) {
    return { error: String(error), requests, errors };
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
  for (const viewport of VIEWPORTS) {
    for (const theme of THEMES) {
      const id = `${state.name}-${viewport.join("x")}-${theme}`;
      const ref = await capture(state, "ref", viewport, theme);
      const app = await capture(state, "app", viewport, theme);
      const row = { id, state: state.name, viewport: viewport.join("x"), theme };
      if (ref.png) writeFileSync(join(OUT, `${id}-ref.png`), ref.png);
      if (app.png) writeFileSync(join(OUT, `${id}-app.png`), app.png);
      if (ref.png && app.png) {
        const d = await diff(ref.png, app.png);
        writeFileSync(join(OUT, `${id}-diff.png`), Buffer.from(d.png, "base64"));
        row.mismatch = Number(d.mismatch.toFixed(2));
        row.probe = probeDiff(ref.probe, app.probe);
        const refWords = new Set(ref.words);
        const appWords = new Set(app.words);
        row.words = {
          refOnly: ref.words.filter((w) => !appWords.has(w)),
          appOnly: app.words.filter((w) => !refWords.has(w)),
        };
      }
      row.errors = { ref: ref.error ?? null, app: app.error ?? null };
      row.pageErrors = { ref: ref.errors, app: app.errors };
      row.requests = app.requests;
      results.push(row);
      console.log(
        `${id}: ${row.mismatch ?? "—"}%${ref.error || app.error ? ` ${ref.error ?? ""} ${app.error ?? ""}` : ""}`,
      );
    }
  }
}
writeFileSync(join(OUT, "results.json"), JSON.stringify(results, null, 1));

/* ------------------------------------------------------------------ bindings */
/* The list actions done the owner's way on the desktop (English labels), with the routes they hit.
   Runs last: «حذف» hides the group's history for good. */
if (!args["no-bindings"]) {
  const ctx = await context("app", [1280, 800], "dark", "en");
  const page = await ctx.newPage();
  const a = api(ctx);
  const log = [];
  page.on("requestfinished", async (request) => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/")) return;
    if (request.method() === "GET" && !url.pathname.startsWith("/api/search")) return;
    log.push({
      method: request.method(),
      path: url.pathname + url.search,
      body: request.postData(),
      status: (await request.response())?.status(),
    });
  });
  const row = (name) =>
    page.locator(
      `.desktop-list .thread[data-key="${name.startsWith("group") ? name : agentKey(name)}"]`,
    );
  const bar = () => page.getByRole("toolbar", { name: "Selected chats" });
  const select = async (name) => {
    await row(name).click({ button: "right" });
    await bar().waitFor();
  };
  const tool = (name) => bar().getByRole("button", { name, exact: true });
  const more = async (item) => {
    await tool("More").click();
    await page.getByRole("menuitem", { name: item }).click();
  };
  const steps = [];
  const step = async (name, run) => {
    const from = log.length;
    try {
      await run();
      await pause(page, 700);
      steps.push({ step: name, requests: log.slice(from) });
    } catch (error) {
      steps.push({ step: name, error: String(error), requests: log.slice(from) });
      await page.keyboard.press("Escape").catch(() => {});
    }
  };
  await page.goto(`${BASE}/app`);
  await row("gold").waitFor();
  await step("pin", async () => {
    await select("gold");
    await tool("Pin").click();
  });
  await step("unpin", async () => {
    await select("gold");
    await tool("Unpin").click();
  });
  await step("mute", async () => {
    await select("gold");
    await tool("Mute notifications").click();
  });
  await step("unmute", async () => {
    await select("gold");
    await tool("Unmute").click();
  });
  await step("archive then undo", async () => {
    await select("research");
    await tool("Archive").click();
    await page.locator("#toast").getByRole("button", { name: "Undo" }).click();
  });
  await step("mark read/unread", async () => {
    await select("lonora");
    await more(/Mark as (read|unread)/);
  });
  await step("favourite", async () => {
    await select("friend");
    await more(/Add to favourites/);
  });
  await step("unfavourite", async () => {
    await select("friend");
    await more(/Remove from favourites/);
  });
  await step("keep archived setting", async () => {
    await a.post("/threads/prefs", { thread_ids: [seed.threads.friend], archived: true });
    await page.goto(`${BASE}/app/archived`);
    await page.getByRole("switch", { name: "Keep chats archived" }).click();
    await pause(page, 500);
    await page.getByRole("switch", { name: "Keep chats archived" }).click();
    await a.post("/threads/prefs", { thread_ids: [seed.threads.friend], archived: false });
    await page.goto(`${BASE}/app`);
    await row("gold").waitFor();
  });
  await step("new list", async () => {
    await page.locator(".desktop-list .chip-add").click();
    await page.locator("dialog[open] input").first().fill("القائمة");
    await page
      .locator("dialog[open] form button[type=submit], dialog[open] .btn.primary")
      .first()
      .click();
    await pause(page, 600);
    await page.locator("dialog[open] [role=checkbox]").first().click();
    await page.locator("dialog[open] .btn.primary").last().click();
  });
  await step("delete list (chip menu) then undo", async () => {
    await page
      .locator(".desktop-list .list-chip", { hasText: "القائمة" })
      .click({ button: "right" });
    await page.getByRole("menuitem", { name: "Delete the list" }).click();
    await page.locator("#toast").getByRole("button", { name: "Undo" }).click();
    await pause(page, 600);
    await page.locator(".desktop-list .list-filters .chip").first().click();
  });
  await step("search", async () => {
    await page.locator("#desktop-search").fill("الذهب");
    await pause(page, 900);
    await page.locator("#desktop-search").fill("");
  });
  await step("read all (list menu)", async () => {
    await page.getByRole("button", { name: "List options" }).click();
    await page.getByRole("menuitem", { name: "Mark all as read" }).click();
  });
  await step("«حذف» on the group", async () => {
    await select(`group:${seed.group}`);
    await tool("Delete").click();
    await page.locator("dialog[open] .btn.danger, dialog[open] button.danger").last().click();
  });
  const groups = await a.get("/groups");
  const agents = await a.get("/agents");
  const report = {
    steps,
    deletes: log.filter((entry) => entry.method === "DELETE"),
    forbiddenDeletes: log.filter(
      (entry) => entry.method === "DELETE" && /^\/api\/(agents|groups|threads)\//.test(entry.path),
    ),
    groupStays: groups.some((group) => group.id === seed.group),
    agentsStay: Object.values(seed.agents).every((id) => agents.some((agent) => agent.id === id)),
  };
  writeFileSync(join(OUT, "bindings.json"), JSON.stringify(report, null, 1));
  console.log(
    `bindings: ${steps.filter((s) => s.error).length} step errors; forbidden deletes ${report.forbiddenDeletes.length}; group stays ${report.groupStays}`,
  );
  await ctx.close();
}
await browser.close();
stop();
process.exit(0);
