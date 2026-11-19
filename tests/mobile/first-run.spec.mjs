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

test("the answer belongs to its address: a new address is checked again before anything is sent", async ({
  page,
  baseURL,
}) => {
  const other = baseURL.replace("localhost", "127.0.0.1");
  await page.route("**/api/onboarding", (route) =>
    new URL(route.request().url()).hostname === "127.0.0.1"
      ? route.fulfill({
          json: { owner_initialized: false },
          headers: { "access-control-allow-origin": "*" },
        })
      : route.fallback(),
  );
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
  const field = page.getByRole("textbox", { name: "Lonora server URL", exact: true });
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(credentials.email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await field.fill(other);
  // Until the new address answers, nothing can be sent.
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeDisabled();
  await expect(page.getByText("Set up Lonora", { exact: true })).toBeVisible();
  // Back to the first server: sign-in again, and the check did not cancel the sign-in.
  await field.fill(baseURL);
  const signIn = page.getByRole("button", { name: "Sign in", exact: true });
  await expect(signIn).toBeEnabled();
  const signedIn = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/auth/login") && response.request().method() === "POST",
  );
  await signIn.click();
  expect((await signedIn).status()).toBe(200);
});

test("a sign-in that fails asks the server again: a first run missed by the check appears", async ({
  page,
}) => {
  let initialized = true;
  await page.route("**/api/onboarding", (route) =>
    route.fulfill({ json: { owner_initialized: initialized } }),
  );
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({ status: 401, json: { code: "unauthorized" } }),
  );
  await page.goto("/");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(credentials.email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  const signIn = page.getByRole("button", { name: "Sign in", exact: true });
  await expect(signIn).toBeEnabled();
  initialized = false;
  await signIn.click();
  await expect(page.getByText("Set up Lonora", { exact: true })).toBeVisible();
});

test("a setup token shorter than the server's says so, and the submit key sends nothing the button would not", async ({
  page,
}) => {
  const sent = [];
  await page.route("**/api/onboarding", (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: { owner_initialized: false } });
    sent.push(route.request().postDataJSON());
    return route.fulfill({ status: 422, json: { code: "invalid_request" } });
  });
  await page.goto("/");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(credentials.email);
  const password = page.getByLabel("Password · at least 12 characters", { exact: true });
  const field = page.getByLabel("Setup token", { exact: true });
  const create = page.getByRole("button", { name: "Create workspace", exact: true });
  await password.fill("short");
  await field.fill(token);
  await expect(create).toBeDisabled();
  await field.press("Enter");
  await password.fill(credentials.password);
  await field.fill(token.slice(0, 10));
  await expect(create).toBeEnabled();
  await create.click();
  const short = page.getByText(
    "The setup token is at least 24 characters. Copy all of it from your server configuration.",
    { exact: true },
  );
  await expect(short).toBeVisible();
  await field.press("Enter");
  await expect(short).toBeVisible();
  expect(sent).toEqual([]);
});

test("the submit key sends nothing while the address is still being checked", async ({
  page,
  baseURL,
}) => {
  let release = () => undefined;
  let held = null;
  await page.route("**/api/onboarding", async (route) => {
    if (held) await held;
    return route.fallback();
  });
  const logins = [];
  await page.route("**/api/auth/login", (route) => {
    logins.push(route.request().method());
    return route.fallback();
  });
  await page.goto("/");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(credentials.email);
  const password = page.getByLabel("Password", { exact: true });
  await password.fill(credentials.password);
  const signIn = page.getByRole("button", { name: "Sign in", exact: true });
  await expect(signIn).toBeEnabled();
  // The same server written another way is another address: it is checked again.
  held = new Promise((resolve) => {
    release = resolve;
  });
  await page
    .getByRole("textbox", { name: "Lonora server URL", exact: true })
    .fill(`${new URL(baseURL).origin}/`);
  await password.press("Enter");
  await expect(signIn).toBeDisabled();
  expect(logins).toEqual([]);
  release();
  await expect(signIn).toBeEnabled();
  expect(logins).toEqual([]);
  // Once the address has answered, the same key does send.
  const signedIn = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/auth/login") && response.request().method() === "POST",
  );
  await password.press("Enter");
  expect((await signedIn).status()).toBe(200);
  expect(logins).toEqual(["POST"]);
});

test("the submit key sends nothing while a sign-in is under way", async ({ page }) => {
  let release = () => undefined;
  const held = new Promise((resolve) => {
    release = resolve;
  });
  const logins = [];
  await page.route("**/api/auth/login", async (route) => {
    logins.push(route.request().method());
    await held;
    return route.fulfill({ status: 401, json: { code: "unauthorized" } });
  });
  await page.goto("/");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(credentials.email);
  const password = page.getByLabel("Password", { exact: true });
  await password.fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect.poll(() => logins).toEqual(["POST"]);
  await expect(page.getByRole("button", { name: "Connecting", exact: true })).toBeDisabled();
  await password.press("Enter");
  release();
  await expect(
    page.getByText("Check your credentials or sign in again.", { exact: true }),
  ).toBeVisible();
  expect(logins).toEqual(["POST"]);
});

test("a setup that fails asks the server again: an owner created meanwhile shows sign-in", async ({
  page,
}) => {
  let initialized = false;
  await page.route("**/api/onboarding", (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: { owner_initialized: initialized } });
    // Created elsewhere after the check: the token is right, but this is not that owner.
    initialized = true;
    return route.fulfill({ status: 409, json: { code: "owner_already_initialized" } });
  });
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({ status: 401, json: { code: "unauthorized" } }),
  );
  await page.goto("/");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(credentials.email);
  await page
    .getByLabel("Password · at least 12 characters", { exact: true })
    .fill(credentials.password);
  await page.getByLabel("Setup token", { exact: true }).fill(token);
  await page.getByRole("button", { name: "Create workspace", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
  await expect(page.getByText("Set up Lonora", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Setup token", { exact: true })).toHaveCount(0);
  await expect(
    page.getByText("Check your credentials or sign in again.", { exact: true }),
  ).toBeVisible();
});

test("a setup that fails while the server is unreachable keeps the setup form and its token", async ({
  page,
}) => {
  let down = false;
  await page.route("**/api/onboarding", (route) => {
    if (route.request().method() === "GET" && !down)
      return route.fulfill({ json: { owner_initialized: false } });
    down = true;
    return route.abort("connectionrefused");
  });
  await page.goto("/");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(credentials.email);
  await page
    .getByLabel("Password · at least 12 characters", { exact: true })
    .fill(credentials.password);
  const field = page.getByLabel("Setup token", { exact: true });
  await field.fill(token);
  const recheckFailed = page.waitForEvent(
    "requestfailed",
    (request) => request.method() === "GET" && request.url().endsWith("/api/onboarding"),
  );
  await page.getByRole("button", { name: "Create workspace", exact: true }).click();
  await expect(
    page.getByText("Could not connect to the server. Check its address and your network.", {
      exact: true,
    }),
  ).toBeVisible();
  // The check asked after the failure cannot reach the server either: what it knew stays.
  await recheckFailed;
  await page.waitForTimeout(300);
  await expect(page.getByText("Set up Lonora", { exact: true })).toBeVisible();
  await expect(field).toHaveValue(token);
  await expect(page.getByRole("button", { name: "Create workspace", exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toHaveCount(0);
});

test("an answer that is not Lonora's keeps sign-in", async ({ page }) => {
  await page.route("**/api/onboarding", (route) => route.fulfill({ json: {} }));
  await page.goto("/");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(credentials.email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
  await expect(page.getByLabel("Setup token", { exact: true })).toHaveCount(0);
});
