// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
// A setup link (https://<host>/#token=…, P1-T4) carries a one-time secret. However the page is
// opened (an installation that already has its owner, or with the owner signed in), the token
// leaves the address bar at once and is not kept in the history entry.
import { expect, test } from "../ui-test.mjs";

const credentials = {
  email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
  password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
};
const linkToken = "lonora-link-setup-token-0123456789";

test.beforeEach(async ({ context }) => {
  const status = await (await context.request.get("/api/onboarding")).json();
  if (!status.owner_initialized) {
    const created = await context.request.post("/api/onboarding", {
      data: {
        ...credentials,
        bootstrap_token: process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
      },
    });
    expect(created.status()).toBe(201);
  }
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
});

test("a setup link on an installation with its owner leaves no token in the address", async ({
  page,
}) => {
  await page.goto(`/app#token=${linkToken}`);
  await expect(page.getByRole("heading", { name: "Welcome to Lonora" })).toBeVisible();
  expect(new URL(page.url()).hash).toBe("");
});

test("a setup link opened while the owner is signed in leaves no token either", async ({
  page,
  context,
}) => {
  const login = await context.request.post("/api/auth/login", { data: credentials });
  expect(login.status()).toBe(200);
  await page.goto(`/app#token=${linkToken}`);
  await expect(page.getByRole("heading", { name: "Welcome to Lonora" })).toHaveCount(0);
  await expect.poll(() => new URL(page.url()).hash).toBe("");
});
