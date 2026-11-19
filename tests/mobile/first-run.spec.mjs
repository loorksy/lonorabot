// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
// Sign-in on mobile, as Web's AuthFlow: a server with no owner yet (GET /onboarding) shows
// «إعداد Lonora»: email, password (12 characters at least) and the setup token create the
// owner (POST /onboarding), then the app signs in with the same credentials.
import { expect, test } from "@playwright/test";

const credentials = {
  email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
  password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
};
const token = process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026";

// The server's owner, created once as the other suites do: the sign-in that follows the
// (routed) first run is a real one.
async function ownerExists(context) {
  const status = await (await context.request.get("/api/onboarding")).json();
  if (!status.owner_initialized) {
    const created = await context.request.post("/api/onboarding", {
      data: { ...credentials, bootstrap_token: token },
    });
    expect(created.status()).toBe(201);
  }
}

test.beforeEach(async ({ context }) => {
  await ownerExists(context);
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
});

test("a server with no owner shows the setup form; it creates the owner, then signs in", async ({
  page,
}) => {
  const created = [];
  await page.route("**/api/onboarding", (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: { owner_initialized: created.length > 0 } });
    created.push(route.request().postDataJSON());
    return route.fulfill({ status: 201, json: { owner_initialized: true } });
  });
  await page.goto("/");
  await expect(page.getByText("Set up Lonora", { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(credentials.email);
  const create = page.getByRole("button", { name: "Create workspace", exact: true });
  // A password shorter than the server accepts never leaves the device.
  await page.getByLabel("Password · at least 12 characters", { exact: true }).fill("short");
  await page.getByLabel("Setup token", { exact: true }).fill(token);
  await expect(create).toBeDisabled();
  await page
    .getByLabel("Password · at least 12 characters", { exact: true })
    .fill(credentials.password);
  const signedIn = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/auth/login") && response.request().method() === "POST",
  );
  await create.click();
  expect((await signedIn).status()).toBe(200);
  expect(created).toEqual([{ ...credentials, bootstrap_token: token }]);
  await expect(page.getByText("Set up Lonora", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Create workspace" })).toHaveCount(0);
});

test("a wrong setup token says so and keeps the form", async ({ page }) => {
  await page.route("**/api/onboarding", (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ json: { owner_initialized: false } })
      : route.fulfill({ status: 403, json: { code: "invalid_bootstrap_token" } }),
  );
  await page.goto("/");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(credentials.email);
  await page
    .getByLabel("Password · at least 12 characters", { exact: true })
    .fill(credentials.password);
  await page.getByLabel("Setup token", { exact: true }).fill("x".repeat(24));
  await page.getByRole("button", { name: "Create workspace", exact: true }).click();
  await expect(page.getByText("The setup code is incorrect.", { exact: true })).toBeVisible();
  await expect(page.getByText("Set up Lonora", { exact: true })).toBeVisible();
});

test("a server that has its owner shows sign-in, with no setup token", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
  await expect(page.getByLabel("Setup token", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Use your server address.", { exact: true })).toBeVisible();
});

test("a retry after the owner was created (then the sign-in failed) signs in", async ({ page }) => {
  await page.route("**/api/onboarding", (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ json: { owner_initialized: false } })
      : route.fulfill({ status: 409, json: { code: "owner_already_initialized" } }),
  );
  await page.goto("/");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(credentials.email);
  await page
    .getByLabel("Password · at least 12 characters", { exact: true })
    .fill(credentials.password);
  await page.getByLabel("Setup token", { exact: true }).fill(token);
  const signedIn = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/auth/login") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Create workspace", exact: true }).click();
  expect((await signedIn).status()).toBe(200);
  await expect(page.getByText("Set up Lonora", { exact: true })).toHaveCount(0);
});
