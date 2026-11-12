// «تجربة المحادثة» on mobile, from the conversation's menu: the switches persist on the device
// and the conversation honours them (here: @ suggestions and the agent's activity line).
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

async function fixture(context) {
  const data = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init", empty: true }),
      encoding: "utf8",
    }),
  );
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const create = async (name) => {
    const agent = await (
      await context.request.post("/api/agents", {
        headers,
        data: { name, trading_account_id: data.account, trading_symbol: data.symbol },
      })
    ).json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    return { agent, thread };
  };
  return { create, remove: (id) => context.request.delete(`/api/agents/${id}`, { headers }) };
}

test("the chat experience switches persist and the conversation follows them", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  const one = await data.create(`Prefs ${randomUUID().slice(0, 6)}`),
    two = await data.create(`Peer ${randomUUID().slice(0, 6)}`);
  try {
    await page.goto(`/thread?id=${one.thread.id}`);
    const composer = page.getByRole("textbox", { name: "Message…", exact: true });
    await composer.fill("@Pe");
    await expect(
      page.getByRole("button", { name: `@${two.agent.name}`, exact: true }),
    ).toBeVisible();
    await composer.fill("");

    await page.getByRole("button", { name: "Agent actions", exact: true }).click();
    await page.getByText("Chat experience", { exact: true }).click();
    await expect(page.getByText("The agent's work steps", { exact: true })).toBeVisible();
    await page.getByRole("switch", { name: "@ suggestions" }).click();
    await page.reload();

    await composer.fill("@Pe");
    await expect(page.getByRole("button", { name: `@${two.agent.name}`, exact: true })).toHaveCount(
      0,
    );
    expect(
      await page.evaluate(() => JSON.parse(localStorage.getItem("lonora.chatPrefs")).assist),
    ).toBe(false);
  } finally {
    await data.remove(one.agent.id);
    await data.remove(two.agent.id);
  }
});
