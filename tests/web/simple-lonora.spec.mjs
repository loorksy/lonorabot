// Simple Lonora acceptance on the Web (W15-ACC): the owner types Arabic in the real
// composer, a scripted model answers through the real agent runtime (tests/
// check_simple_lonora.py --ui-turn stands in for the gateway worker), and the owner taps
// the cards in the conversation. Each journey takes the taps the vision says, and the
// header pill, the cards and the stored records say the same thing.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "../ui-test.mjs";

function python(args, data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", args, { input: JSON.stringify(data), encoding: "utf8" }),
  );
}
const simulation = (data) => python(["tests/check_chart_browser.py"], data);
const worker = (data) => python(["tests/check_simple_lonora.py", "--ui-turn"], data);

const words = {
  createGold: "أنشئ وكيل ذهب يدير صفقاتي على حسابي بنفسه",
  buyOnce: "اشترِ 0.1 ذهب على حسابي بوقف خسارة 150",
};
const text = {
  approvalTitle: "طلب تداول",
  approve: "موافقة",
  full: "وكّله",
  ask: "يستأذن",
};

const raised = (turn, kind) => turn.cards.filter((row) => row.kind === kind).map((row) => row.id);

test("ar: one sentence creates a gold agent; one tap approves a trade, one tap sets Full", async ({
  page,
  context,
  cleanup,
}) => {
  test.setTimeout(180000);
  const data = simulation({ action: "init", empty: true });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const lonora = (await (await context.request.get("/api/agents")).json()).find(
    (row) => row.role === "personal",
  );
  expect(lonora).toBeTruthy();
  const lonoraThread = await (
    await context.request.post(`/api/agents/${lonora.id}/conversation`, { headers, data: {} })
  ).json();
  const name = `Gold agent ${randomUUID().slice(0, 6)}`;
  let gold;
  const taps = { create: 0, approve: 0 };
  const said = async (sentence) => {
    const composer = page.locator("textarea");
    await composer.fill(sentence);
    await composer.press("Enter");
    await expect(page.getByText(sentence, { exact: true }).first()).toBeVisible();
  };
  const decisions = [];
  page.on("request", (request) => {
    const url = request.url();
    if (
      request.method() === "POST" &&
      (url.endsWith("/decision") || url.includes("/trading/execute"))
    )
      decisions.push(new URL(url).pathname);
  });
  cleanup(async () => {
    if (gold) await context.request.delete(`/api/agents/${gold}`, { headers });
    simulation({ ...data, action: "cleanup" });
  });
  // 1. «أنشئ وكيل ذهب …»: the agent and its Mandate card, with no question asked.
  await page.goto(`/app/${lonora.id}`);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await said(words.createGold);
  const created = worker({
    thread: lonoraThread.id,
    account: data.account,
    symbol: data.symbol,
    name,
  });
  expect(created.status, `creation run ${created.error_code}`).toBe("completed");
  gold = created.agent;
  expect(gold).toBeTruthy();
  expect(raised(created, "agent_created")).toHaveLength(0);
  expect(raised(created, "grant_authority")).toHaveLength(0);
  const [mandateId] = raised(created, "trading_mode");
  expect(raised(created, "trading_mode")).toHaveLength(1);
  const mandateRow = (
    await (await context.request.get(`/api/owner-actions?thread_id=${lonoraThread.id}`)).json()
  ).find((row) => row.id === mandateId);
  expect(mandateRow.facts.agent.name).toBe(name);
  expect(mandateRow.facts.trading_mode).toBe("ask");
  const mandate = page.locator(`[data-owner-action="${mandateRow.id}"]`);
  await expect(mandate).toHaveAttribute("data-owner-action-status", "pending");
  await expect(mandate.getByRole("button", { name: text.full, exact: true })).toBeVisible();
  await mandate.screenshot({ path: test.info().outputPath("simple-lonora-mandate-ar.png") });

  // 2. Before the tap the agent asks: one approval card, one tap.
  const goldThread = await (
    await context.request.post(`/api/agents/${gold}/conversation`, { headers, data: {} })
  ).json();
  await page.goto(`/app/agent/${gold}`);
  await expect(page.locator("main .badge")).toContainText(text.ask);
  await page.goto(`/app/${gold}`);
  await said(words.buyOnce);
  const asked = worker({ thread: goldThread.id, account: data.account, symbol: data.symbol });
  expect(asked.status).toBe("waiting_input");
  const approval = page.locator("[data-trade-approval]").last();
  await expect(approval).toContainText(data.symbol);
  await approval.getByRole("button", { name: text.approve, exact: true }).click();
  taps.approve += 1;
  await expect(approval.getByRole("button", { name: text.approve, exact: true })).toHaveCount(0);
  const traded = worker({ thread: goldThread.id, account: data.account, symbol: data.symbol });
  expect(traded.status).toBe("completed");
  await page.reload();
  // The confirmed order is shown once, as its Execution Receipt (10.3).
  await expect(page.locator("[data-execution-receipt]").last()).toBeVisible();

  // 3. One tap on the Mandate card sets Full. No passkey.
  await page.goto(`/app/${lonora.id}`);
  const card = page.locator(`[data-owner-action="${mandateRow.id}"]`);
  await card.getByRole("button", { name: text.full, exact: true }).click();
  taps.create += 1;
  await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
  const agent = await (await context.request.get(`/api/agents/${gold}`)).json();
  expect(agent.trading_mode).toBe("full");
  const permission = await (await context.request.get(`/api/agents/${gold}/permissions`)).json();
  expect(permission.effective_level).toBe("supervised");
  expect(permission.active_authorities).toEqual([]);
  await page.goto(`/app/agent/${gold}`);
  await expect(page.locator("main .badge")).toContainText(text.full);

  // One confirmation each; nothing else was sent.
  expect(taps).toEqual({ create: 1, approve: 1 });
  expect(decisions.filter((path) => path.includes("/trading/execute"))).toEqual([]);
});
