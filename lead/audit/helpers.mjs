// Shared helpers for comparing the live app with the reference. Import from any script:
//   import { openApp, openRef, shot, close } from "/tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/audit/helpers.mjs";
// Run scripts with:  cd /home/user/lonorabot && env -u AI_AGENT -u CLAUDECODE node <script.mjs>
// openApp/openRef return a Playwright page. PHONE = [390, 844], DESKTOP = [1280, 800].
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire("/home/user/lonorabot/package.json");
const { chromium } = require("@playwright/test");
export const BASE = "http://localhost:8832";
export const REF_URL = "file:///home/user/lonorabot/docs/ui-reference/Lonora-Desktop-37.html";
export const PHONE = [390, 844];
export const DESKTOP = [1280, 800];
const seed = JSON.parse(readFileSync(new URL("./seed.json", import.meta.url), "utf8"));
export const SEED = { agents: seed.agents, group: seed.group, threads: seed.threads };
let browser;
async function launch() {
  browser ??= await chromium.launch({ executablePath: "/usr/bin/google-chrome", args: ["--no-sandbox"] });
  return browser;
}
async function context([width, height], theme, opts = {}) {
  return (await launch()).newContext({
    viewport: { width, height }, deviceScaleFactor: 1, timezoneId: "UTC", locale: "ar",
    colorScheme: theme, reducedMotion: "no-preference",
    hasTouch: opts.touch ?? width < 900, isMobile: false, ...opts.context,
  });
}
/** The live app, signed in as the seeded owner. `path` like "/app" or "/app/settings". */
export async function openApp(viewport = PHONE, theme = "dark", path = "/app", opts = {}) {
  const ctx = await context(viewport, theme, opts);
  await ctx.addCookies(seed.cookies.map((c) => ({ ...c, url: BASE, httpOnly: c.name === "lonora_session", sameSite: "Strict" })));
  await ctx.addInitScript((t) => { try { localStorage.setItem("lonora.locale", "ar"); localStorage.setItem("lonora.theme", t); } catch {} }, theme);
  const page = await ctx.newPage();
  await page.goto(BASE + path, { waitUntil: "networkidle" }).catch(() => {});
  return page;
}
/** The reference prototype with its own demo data. `hash` like "chats", "settings", "chat". Use page.evaluate to call its JS (e.g. go('settings')). */
export async function openRef(viewport = PHONE, theme = "dark", hash = "chats", opts = {}) {
  const ctx = await context(viewport, theme, opts);
  const page = await ctx.newPage();
  await page.goto(REF_URL, { waitUntil: "load" });
  // skip the intro/sign-in overlay and pick the theme the way the prototype stores it
  await page.evaluate((t) => { try { const k = "lonora-complete-v4"; const s = JSON.parse(localStorage.getItem(k) || "{}"); s.auth = { ...(s.auth || {}), signedIn: true, onboarded: true, name: "Ahmed" }; s.theme = t; localStorage.setItem(k, JSON.stringify(s)); } catch {} }, theme);
  await page.reload({ waitUntil: "load" });
  if (hash && hash !== "chats") await page.evaluate((h) => { location.hash = h; }, hash);
  await page.waitForTimeout(400);
  return page;
}
export async function shot(page, file, opts = {}) { await page.screenshot({ path: file, fullPage: false, ...opts }); return file; }
export async function close() { await browser?.close(); browser = undefined; }
