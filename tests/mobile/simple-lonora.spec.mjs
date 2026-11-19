// Simple Lonora acceptance on the phone (W15-ACC): the same Arabic sentences through the
// Expo composer, the scripted model behind the real runtime (tests/check_simple_lonora.py
// --ui-turn stands in for the gateway worker), and the same server cards. One sentence
// creates the agent and its grant card.
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
  createGold: "أنشئ وكيل ذهب يدير صفقاتي على حسابي بنفسه",
};
const text = {
  composer: "اكتب رسالة…",
  send: "إرسال",
  created: "أُنشئ وكيل",
  grantTitle: "يتداول بنفسه",
  authorize: "التفويض بمفتاح المرور",
};

const raised = (turn, kind) => turn.cards.filter((row) => row.kind === kind).map((row) => row.id);

test("Expo ar: one sentence creates the agent and its grant card", async ({ page, context }) => {
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
  const thread = await (
    await context.request.post(`/api/agents/${lonora.id}/conversation`, { headers, data: {} })
  ).json();
  const name = `Gold agent ${randomUUID().slice(0, 6)}`;
  let gold;
  const said = async (sentence) => {
    await page.getByRole("textbox", { name: text.composer, exact: true }).fill(sentence);
    await page.getByRole("button", { name: text.send, exact: true }).click();
    await expect(page.getByText(sentence, { exact: true }).first()).toBeVisible();
  };
  try {
    await page.goto(`/thread?id=${thread.id}`);

    // «أنشئ وكيل ذهب …»: the creation card and the grant card, the same server cards
    // the Web shows.
    await said(words.createGold);
    const created = worker({ thread: thread.id, account: data.account, symbol: data.symbol, name });
    expect(created.status).toBe("completed");
    gold = created.agent;
    expect(raised(created, "agent_created")).toHaveLength(1);
    expect(raised(created, "grant_authority")).toHaveLength(1);
    await page.reload();
    const creation = page.getByTestId(`owner-action-${raised(created, "agent_created")[0]}`);
    await expect(creation.getByText(text.created, { exact: false }).first()).toBeVisible();
    const grant = page.getByTestId(`owner-action-${raised(created, "grant_authority")[0]}`);
    await expect(grant.getByText(text.grantTitle, { exact: false }).first()).toBeVisible();
    await expect(grant.getByText(data.symbol, { exact: false }).first()).toBeVisible();
    await expect(grant.getByRole("button", { name: text.authorize, exact: true })).toBeVisible();
    await grant.screenshot({ path: test.info().outputPath("simple-lonora-grant-native-ar.png") });
  } finally {
    if (gold) await context.request.delete(`/api/agents/${gold}`, { headers });
    simulation({ ...data, action: "cleanup" });
  }
});
