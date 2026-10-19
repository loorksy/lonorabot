// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.

import { randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const database = process.env.LONORA_DATABASE_URL;
if (!database)
  throw new Error("UI tests require an explicit LONORA_DATABASE_URL for a test database.");
let parsed;
try {
  parsed = new URL(database.replace(/^postgresql\+asyncpg:/, "postgresql:"));
} catch {
  throw new Error("UI tests require a valid PostgreSQL test database URL.");
}
if (
  parsed.protocol !== "postgresql:" ||
  !/^[a-z0-9][a-z0-9_-]*_(ci|test|verify)$/i.test(decodeURIComponent(parsed.pathname.slice(1))) ||
  parsed.searchParams.has("database") ||
  parsed.searchParams.has("dbname")
)
  throw new Error("UI tests refuse a database whose name does not end in _ci, _test or _verify.");
const root = fileURLToPath(new URL(".", import.meta.url));
const mobile = process.env.LONORA_UI_TEST_APP === "mobile";
const port = mobile ? 8831 : 8830;
// WebAuthn requires a domain RP ID; localhost is its standard development exception.
const baseURL = `http://localhost:${port}`;
const output = `${root}.runtime/${mobile ? "mobile" : "web"}-ui-tests`;
const rendererOutput = mobile ? `${root}.runtime/chart-renderer-ui-tests` : output;

export default defineConfig({
  testDir: mobile ? "./tests/mobile" : "./tests/web",
  outputDir: `${root}.runtime/${mobile ? "mobile" : "web"}-playwright-results`,
  testMatch: "**/*.spec.mjs",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 7_000 },
  reporter: "list",
  use: {
    baseURL,
    viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    launchOptions: process.env.LONORA_UI_TEST_BROWSER_PATH
      ? { executablePath: process.env.LONORA_UI_TEST_BROWSER_PATH }
      : {},
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    // The development React bundle exercises StrictMode effect replay. Build it
    // separately so regression checks do not replace the production Web build.
    command: mobile
      ? "pnpm --filter @lonora/web exec vite build --outDir ../../.runtime/chart-renderer-ui-tests --emptyOutDir && pnpm --filter @lonora/mobile exec expo export --platform web --output-dir ../../.runtime/mobile-ui-tests && .venv/bin/lonora-api --host 127.0.0.1 --port 8831"
      : "pnpm --filter @lonora/web exec vite build --outDir ../../.runtime/web-ui-tests --emptyOutDir && .venv/bin/lonora-api --host 127.0.0.1 --port 8830",
    cwd: root,
    url: `${baseURL}/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...process.env,
      NODE_ENV: mobile ? "production" : "development",
      LONORA_DATABASE_URL: database,
      LONORA_COOKIE_SECURE: "false",
      LONORA_ALLOWED_ORIGIN: baseURL,
      LONORA_WEB_ROOT: output,
      LONORA_CHART_RENDERER_ROOT: rendererOutput,
      LONORA_ARTIFACT_ROOT: `${root}.runtime/ui-regression-artifacts`,
      LONORA_BOOTSTRAP_TOKEN:
        process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
      LONORA_ENCRYPTION_KEY:
        process.env.LONORA_ENCRYPTION_KEY ?? randomBytes(32).toString("base64url").padEnd(44, "="),
    },
  },
});
