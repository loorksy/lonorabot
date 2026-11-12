import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { seedSecretCard } from "./secret-card-fixture.mjs";

function simulation(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

const copy = {
  en: {
    title: "Secret",
    asked: "Asked by",
    save: "Save",
    saved: "Saved encrypted. No agent sees the values.",
    notNow: "Not now",
  },
  ar: {
    title: "بيانات سرّية",
    asked: "يطلبها",
    save: "حفظ",
    saved: "حُفظت مشفّرة. لا يرى أي وكيل القيم.",
    notNow: "ليس الآن",
  },
};

for (const locale of ["ar", "en"])
  test(`${locale}: a Secret card saves the owner's values to its own route only`, async ({
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
    const key = `EXCHANGE_KEY_${suffix}`;
    const user = `EXCHANGE_USER_${suffix}`;
    const secret = `live-${randomUUID()}`;
    const agent = `Keys ${suffix}`;
    const seeded = seedSecretCard({
      agent,
      label: "مفاتيح المنصّة",
      fields: [
        { key, label: "مفتاح API" },
        { key: user, label: "اسم المستخدم", secret: false },
      ],
    });
    const posted = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/api/"))
        posted.push({ url: new URL(request.url()).pathname, body: request.postData() ?? "" });
    });
    await page.goto(`/app/${seeded.agent}`);
    const card = page.locator(`[data-owner-action="${seeded.card}"]`);
    await expect(card).toHaveAttribute("data-owner-action-kind", "secret");
    await expect(card.locator(".oa-kind")).toHaveText(text.title);
    await expect(card).toContainText("⁨مفاتيح المنصّة⁩");
    await expect(card).toContainText(`${text.asked} ⁨${agent}⁩`);
    const keyInput = card.locator(`input[name="${key}"]`);
    await expect(keyInput).toHaveAttribute("type", "password");
    await expect(keyInput).toHaveAttribute("dir", "ltr");
    await expect(card.locator(`input[name="${user}"]`)).toHaveAttribute("type", "text");
    await expect(card.getByRole("button", { name: text.notNow, exact: true })).toBeVisible();
    if (locale === "ar") {
      await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
      await card.screenshot({ path: test.info().outputPath("secret-card-ar.png") });
    }
    await keyInput.fill(secret);
    await card.locator(`input[name="${user}"]`).fill("trader");
    await card.getByRole("button", { name: text.save, exact: true }).click();
    await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
    await expect(card.getByRole("status")).toHaveText(text.saved);
    await expect(card.locator("input")).toHaveCount(0);
    // The value went only to the card's own route, never to a chat or decision route.
    const carrying = posted.filter((item) => item.body.includes(secret)).map((item) => item.url);
    expect(carrying).toEqual([`/api/owner-actions/${seeded.card}/secret`]);
    // The owner's secrets list names, never values.
    const listed = await (await context.request.get("/api/secrets")).json();
    expect(listed.map((item) => item.name)).toEqual(expect.arrayContaining([key, user]));
    expect(JSON.stringify(listed)).not.toContain(secret);
    for (const item of listed.filter((row) => [key, user].includes(row.name)))
      await context.request.delete(`/api/secrets/${item.id}`, {
        headers: { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value },
      });
  });
