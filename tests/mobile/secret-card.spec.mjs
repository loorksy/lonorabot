import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { seedSecretCard } from "../web/secret-card-fixture.mjs";

function simulation(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

const copy = {
  ar: { title: "بيانات سرّية", save: "حفظ", saved: "حُفظت مشفّرة. لا يرى أي وكيل القيم." },
  en: { title: "Secret", save: "Save", saved: "Saved encrypted. No agent sees the values." },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: a Secret card in the chat saves to its own route`, async ({
    page,
    context,
  }) => {
    test.setTimeout(90000);
    const text = copy[locale];
    const data = simulation({ action: "init", empty: true });
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    const suffix = randomUUID().slice(0, 8).toUpperCase();
    const key = `NATIVE_KEY_${suffix}`;
    const secret = `live-${randomUUID()}`;
    const seeded = seedSecretCard({
      agent: `Keys ${suffix}`,
      label: "مفتاح الخادم",
      fields: [{ key, label: "كلمة المرور" }],
    });
    const posted = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/api/"))
        posted.push({ url: new URL(request.url()).pathname, body: request.postData() ?? "" });
    });
    await page.goto(`/thread?id=${seeded.thread}`);
    const card = page.getByTestId(`owner-action-${seeded.card}`);
    await expect(card.getByText(text.title, { exact: true })).toBeVisible();
    await expect(card.getByTestId("owner-action-form-secret")).toBeVisible();
    const save = card.getByRole("button", { name: text.save, exact: true });
    await expect(save).toBeDisabled();
    await card.getByLabel("كلمة المرور", { exact: true }).fill(secret);
    if (locale === "ar")
      await card.screenshot({ path: test.info().outputPath("secret-card-native-ar.png") });
    await save.click();
    await expect(card.getByText(text.saved, { exact: true })).toBeVisible();
    const carrying = posted.filter((item) => item.body.includes(secret)).map((item) => item.url);
    expect(carrying).toEqual([`/api/owner-actions/${seeded.card}/secret`]);
    const listed = await (await context.request.get("/api/secrets")).json();
    const saved = listed.find((item) => item.name === key);
    expect(saved).toBeTruthy();
    await context.request.delete(`/api/secrets/${saved.id}`, {
      headers: { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value },
    });
  });

const signInCopy = {
  ar: { address: "عنوان الخادم", connect: "ربط" },
  en: { address: "Server URL", connect: "Connect" },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: an MCP server that has the owner sign in opens its page in the browser`, async ({
    page,
    context,
  }) => {
    test.setTimeout(90000);
    const text = signInCopy[locale];
    const data = simulation({ action: "init", empty: true });
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    const suffix = randomUUID().slice(0, 8).toUpperCase();
    const seeded = seedSecretCard({
      agent: `Files ${suffix}`,
      target: "mcp_server",
      name: "Files",
    });
    const signIn = `https://auth.example.test/authorize?client_id=lonora&state=${suffix}`;
    const sent = [];
    await page.route("**/api/owner-actions/*/secret", async (route) => {
      sent.push(JSON.parse(route.request().postData() ?? "{}"));
      await route.fulfill({ json: { id: seeded.card, status: "pending", sign_in_url: signIn } });
    });
    await context.route("https://auth.example.test/**", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: "<title>Sign in</title><p>Sign in to Files</p>",
      }),
    );
    await page.goto(`/thread?id=${seeded.thread}`);
    const card = page.getByTestId(`owner-action-${seeded.card}`);
    await expect(card.getByTestId("owner-action-form-secret")).toBeVisible();
    await card.getByLabel(text.address, { exact: true }).fill("https://files.example.test/mcp");
    const opened = context.waitForEvent("page");
    await card.getByRole("button", { name: text.connect, exact: true }).click();
    // The browser opens the server's page; the callback brings the owner back to the app.
    const browser = await opened;
    await browser.waitForURL(signIn);
    expect(sent).toEqual([{ values: { URL: "https://files.example.test/mcp" }, return_to: "app" }]);
  });
