// Simple Lonora acceptance on the Web (W15-ACC): the owner types Arabic in the real
// composer, a scripted model answers through the real agent runtime (tests/
// check_simple_lonora.py --ui-turn stands in for the gateway worker), and the owner taps
// the cards in the conversation. Each journey takes the taps the vision says, and the
// header pill, the cards and the stored records say the same thing.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function python(args, data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", args, { input: JSON.stringify(data), encoding: "utf8" }),
  );
}
const simulation = (data) => python(["tests/check_chart_browser.py"], data);
const worker = (data) => python(["tests/check_simple_lonora.py", "--ui-turn"], data);

const words = {
  createGold: "أنشئ وكيل ذهب يدير صفقاتي على حسابي بنفسه، وخسارة يومية قصوى 2%",
  buyOnce: "اشترِ 0.1 ذهب على حسابي بوقف خسارة 150",
};
const text = {
  approvalTitle: "طلب تداول",
  approve: "موافقة",
  authorize: "التفويض بمفتاح المرور",
  password: "كلمة مرور الحساب",
  register: "سجّل هذا الجهاز أولًا",
  signed: "وُقّع. يتداول بنفسه ضمن هذا التفويض.",
  onItsOwn: "يتداول باستقلال",
  dailyLoss: "الخسارة اليومية",
  asks: "يسألك قبل كل صفقة",
};

const raised = (turn, kind) => turn.cards.filter((row) => row.kind === kind).map((row) => row.id);

/* The trading line of an agent: «الحالة والأمان» from the chat's ⋮ menu (the reference pins
   nothing under the header in a normal state). */
async function modeLine(page) {
  await page.getByRole("button", { name: /^(Chat menu|قائمة المحادثة)$/ }).click();
  await page
    .getByRole("menuitem", {
      name: /^(Status and safety|الحالة والأمان|Trading and safety|التداول والأمان)$/,
    })
    .click();
  return page.getByTestId("agent-mode-line");
}

test("ar: one sentence creates a gold agent; one tap approves a trade, one passkey signs the grant", async ({
  page,
  context,
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
  // enroll: the one-time device registration on a device with no passkey yet.
  const taps = { create: 0, enroll: 0, approve: 0 };
  const said = async (sentence) => {
    const composer = page.locator("textarea");
    await composer.fill(sentence);
    await composer.press("Enter");
    await expect(page.getByText(sentence, { exact: true }).first()).toBeVisible();
  };
  // A fresh authenticator: the first passkey on this device registers inline.
  for (const device of await (await context.request.get("/api/auth/devices")).json())
    expect(
      (await context.request.delete(`/api/auth/devices/${device.id}`, { headers })).ok(),
    ).toBeTruthy();
  const cdp = await context.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  const decisions = [];
  page.on("request", (request) => {
    const url = request.url();
    if (
      request.method() === "POST" &&
      (url.endsWith("/decision") || url.includes("/trading/execute"))
    )
      decisions.push(new URL(url).pathname);
  });
  try {
    // 1. «أنشئ وكيل ذهب …»: the agent and its grant card, with no question asked.
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
    // One creation card (Undo) and one grant card; nothing else to answer.
    expect(raised(created, "agent_created")).toHaveLength(1);
    const [grantId] = raised(created, "grant_authority");
    expect(raised(created, "grant_authority")).toHaveLength(1);
    const grantRow = (
      await (await context.request.get(`/api/owner-actions?thread_id=${lonoraThread.id}`)).json()
    ).find((row) => row.id === grantId);
    expect(grantRow.facts.grant.agent_name).toBe(name);
    expect(grantRow.facts.money.daily_loss.proposed).toBe("200.00");
    const createdCard = page
      .locator('[data-owner-action-kind="agent_created"]')
      .filter({ hasText: name });
    await expect(createdCard).toBeVisible();
    const grant = page.locator(`[data-owner-action="${grantRow.id}"]`);
    await expect(grant).toHaveAttribute("data-owner-action-status", "pending");
    await expect(grant.getByText(data.symbol).first()).toBeVisible();
    await expect(grant).toContainText("200.00");
    await grant.screenshot({ path: test.info().outputPath("simple-lonora-grant-ar.png") });

    // 2. Before any grant the agent asks: one approval card, one tap.
    const goldThread = await (
      await context.request.post(`/api/agents/${gold}/conversation`, { headers, data: {} })
    ).json();
    await page.goto(`/app/${gold}`);
    // Ask me until the grant: the pill says it asks before each trade.
    await expect(await modeLine(page)).toContainText(text.asks);
    await page.keyboard.press("Escape");
    // The sheet slides away before the conversation behind it takes input again.
    await expect(page.locator("#app")).not.toHaveAttribute("inert", "");
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
    await expect(page.locator('[data-trade-result="confirmed"]').last()).toBeVisible();

    // 3. One passkey tap signs the grant. On a device with no passkey yet the
    //    same card first asks for the password and registers the device; registering
    //    continues straight into the passkey prompt for this decision (no second tap).
    await page.goto(`/app/${lonora.id}`);
    const card = page.locator(`[data-owner-action="${grantRow.id}"]`);
    const authorize = card.getByRole("button", { name: text.authorize, exact: true });
    await authorize.click();
    taps.create += 1;
    await card.getByLabel(text.password, { exact: true }).fill("ci-only-owner-password");
    await card.getByRole("button", { name: text.register, exact: true }).click();
    taps.enroll += 1;
    await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
    await expect(card.getByRole("status")).toHaveText(text.signed);
    const permission = await (await context.request.get(`/api/agents/${gold}/permissions`)).json();
    expect(permission.effective_level).toBe("autonomous");
    expect(permission.active_authorities[0].envelope.allow_manual_positions).toBe(false);
    // The gold agent's pill says what the card signed: its pair and the daily loss.
    await page.goto(`/app/${gold}`);
    const pill = await modeLine(page);
    await expect(pill).toContainText(text.onItsOwn);
    await expect(pill).toContainText(data.symbol);
    await expect(pill).toContainText(text.dailyLoss);
    await expect(pill).toContainText("200.00 USD");

    // The vision's counts: one confirmation each; nothing else was sent.
    expect(taps).toEqual({ create: 1, enroll: 1, approve: 1 });
    expect(decisions.filter((path) => path.includes("/trading/execute"))).toEqual([]);
  } finally {
    if (gold) await context.request.delete(`/api/agents/${gold}`, { headers });
    simulation({ ...data, action: "cleanup" });
  }
});
