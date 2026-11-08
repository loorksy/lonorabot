import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function simulation(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

// Cards as the runtime raises them (no model): through lonora_db.owner_actions only.
function seedCard(data) {
  const script = `
import asyncio,json,sys
from uuid import uuid4
sys.path.insert(0,'tests')
from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_db.owner_actions import propose,raise_system_card
from lonora_db.schema import TradingJournalRow
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            fields={'kind':data['kind']}
            if data['kind']=='resolve_operation':
                operation=str(uuid4())
                session.add(TradingJournalRow(operation_id=operation,owner_id=f.owner,account_id=data['account'],request_hash='ui-fixture',request={'account_id':data['account'],'action':'buy','symbol':data['symbol'],'volume':'0.10'},status='ambiguous',execution_mode='live',result={'status':'ambiguous','code':'broker_timeout','details':{'send_state':'sent','execution':{'agent_id':data['agent'],'send_authorized':True}}},submitted_at=utcnow(),updated_at=utcnow()))
                await session.flush()
                fields['operation_id']=operation
            proposal=OwnerActionProposal(**fields)
            if data['kind']=='grant_authority':
                # The draft the tool resolves: this account, this pair, every action, until
                # stopped, own positions excluded and a 3% daily loss (D1), suggested, or
                # from the owner's sentence when the account already has its own limit.
                from lonora_contracts.owner_actions import DailyLossDraft,GrantDraft
                from lonora_db.owner_actions import ALL_ACTIONS
                draft=GrantDraft(agent_id=data['agent'],account_id=data['account'],symbol_scope='selected',symbols=[data['symbol']],actions=list(ALL_ACTIONS),daily_loss=DailyLossDraft(amount='300.00',currency='USD',basis=data.get('basis','suggested'),percent='3',equity='10000'))
                row,_=await propose(session,f.owner,proposal,card_id=str(uuid4()),agent_id=data['agent'],thread_id=data['thread'],run_id=None,grant=draft)
            elif data['kind']=='resume_trading':
                # As an agent proposes it when the owner asks to resume.
                row,_=await propose(session,f.owner,proposal,card_id=str(uuid4()),agent_id=data['agent'],thread_id=data['thread'],run_id=None)
            else:
                row=await raise_system_card(session,f.owner,proposal,agent_id=data['agent'],thread_id=data['thread'],run_id=None)
            print(json.dumps({'id':row.id if row else None,'operation_id':fields.get('operation_id')}))
    finally:
        await f.close(cleanup=False)
asyncio.run(main())
`;
  return JSON.parse(
    execFileSync(".venv/bin/python", ["-c", script], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

async function setup(context, locale) {
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
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const original = await (await context.request.get("/api/trading/controls")).json();
  const connected = await context.request.post("/api/trading/connections", {
    headers,
    data: { provider: "simulation", account_id: `cards-${randomUUID()}`, enabled: true },
  });
  expect(connected.status()).toBe(201);
  const account = (await connected.json()).id;
  const imported = await context.request.post(`/api/trading/connections/${account}/simulation`, {
    headers,
    data: {
      snapshot: {
        balance: "10000",
        currency: "USD",
        instruments: [
          {
            symbol: data.symbol,
            digits: 2,
            tick_size: "0.01",
            volume_min: "0.01",
            volume_max: "100",
            volume_step: "0.01",
          },
        ],
        quotes: {
          [data.symbol]: {
            symbol: data.symbol,
            bid: "160",
            ask: "161",
            observed_at: new Date().toISOString(),
            source: "simulation/ui-fixture",
          },
        },
      },
    },
  });
  expect(imported.ok()).toBeTruthy();
  const agentResponse = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Gold agent ${randomUUID().slice(0, 6)}`,
      trading_account_id: account,
      trading_symbol: data.symbol,
    },
  });
  expect(agentResponse.status()).toBe(201);
  const agent = await agentResponse.json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  const controls = async (value) => {
    const response = await context.request.put("/api/trading/controls", { headers, data: value });
    expect(response.ok()).toBeTruthy();
  };
  return {
    data,
    headers,
    account,
    agent,
    thread,
    controls,
    read: async () => (await context.request.get("/api/trading/controls")).json(),
    async cleanup() {
      await controls(original);
      simulation({ ...data, action: "cleanup" });
    },
  };
}

const copy = {
  en: {
    resumeTitle: "Resume trading",
    resumeButton: "Resume trading",
    resumed: "Trading resumed.",
    resolveTitle: "The broker did not confirm this trade",
    notExecuted: "It did not execute",
    unknown: "Unknown: release the hold",
    recorded: "Recorded: it did not execute (your statement, not broker confirmation).",
    lift: "Lift pause",
    grantTitle: "trade on its own",
    authorize: "Authorize with passkey",
    resumeToo: "Resume trading too",
    includeOwn: "Include positions I opened myself",
    password: "Account password",
    register: "Register this device first",
    signed: "Signed. It trades on its own inside this grant.",
    dailyLoss: "Daily loss limit",
    keepLimit: "Keep my current limit",
    ownExcluded: "Positions you opened yourself are excluded",
    arrow: "→",
  },
  ar: {
    resumeTitle: "استئناف التداول",
    resumeButton: "استئناف التداول",
    resumed: "استؤنف التداول.",
    resolveTitle: "الوسيط لم يؤكد هذه الصفقة",
    notExecuted: "لم تُنفذ",
    unknown: "غير معروفة — ارفع التعليق",
    recorded: "سُجّل: لم تُنفذ (تصريحك، لا تأكيد من الوسيط).",
    lift: "رفع الإيقاف",
    grantTitle: "يتداول بنفسه",
    authorize: "التفويض بمفتاح المرور",
    resumeToo: "استأنف التداول أيضًا",
    includeOwn: "اشمل المراكز التي فتحتها بنفسي",
    password: "كلمة مرور الحساب",
    register: "سجّل هذا الجهاز أولًا",
    signed: "وُقّع. يتداول بنفسه ضمن هذا التفويض.",
    dailyLoss: "حد الخسارة اليومية",
    keepLimit: "أبقِ حدي الحالي",
    ownExcluded: "لا يشمل المراكز التي فتحتها بنفسك",
    arrow: "←",
  },
};

for (const locale of ["en", "ar"])
  test(`${locale}: a grant card signs with one passkey tap, registering the device inline`, async ({
    page,
    context,
  }) => {
    test.setTimeout(90000);
    const text = copy[locale];
    const state = await setup(context, locale);
    // A fresh authenticator: remove only the disposable owner's prior credentials.
    for (const device of await (await context.request.get("/api/auth/devices")).json())
      expect(
        (
          await context.request.delete(`/api/auth/devices/${device.id}`, { headers: state.headers })
        ).ok(),
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
    try {
      // The owner's own Stop: the card's Resume switch waits for the owner.
      await state.controls({ enabled: true, emergency_stop: false });
      await state.controls({ enabled: false, emergency_stop: false });
      // The owner's own 500 daily loss limit; the sentence asked for 3% (300).
      const limit = await context.request.put(
        `/api/trading/accounts/${state.account}/execution-policy`,
        { headers: state.headers, data: { risk: { currency: "USD", max_daily_loss: "500" } } },
      );
      expect(limit.ok()).toBeTruthy();
      const seeded = seedCard({
        kind: "grant_authority",
        account: state.account,
        symbol: state.data.symbol,
        agent: state.agent.id,
        thread: state.thread.id,
        basis: "requested",
      });
      const bodies = [];
      page.on("request", (request) => {
        if (request.method() === "POST" && request.url().includes(`/owner-actions/${seeded.id}/`))
          bodies.push([new URL(request.url()).pathname.split("/").pop(), request.postDataJSON()]);
      });
      await page.goto(`/app/${state.agent.id}`);
      const card = page.locator(`[data-owner-action="${seeded.id}"]`);
      await expect(card).toHaveAttribute("data-owner-action-status", "pending");
      await expect(card.locator("strong")).toContainText(text.grantTitle);
      await expect(card.locator("strong")).toContainText(state.agent.name);
      await expect(card.getByText(state.data.symbol)).toBeVisible();
      // One line from the owner's own limit to the lower one, and the opt-out keeps it.
      const daily = card.getByText(text.dailyLoss, { exact: false });
      await expect(daily).toBeVisible();
      await expect(daily).toContainText(`500⁩ ${text.arrow} ⁨300.00 USD`);
      await expect(card.getByRole("checkbox", { name: text.keepLimit })).not.toBeChecked();
      // The switch states the owner's own positions; no fixed line contradicts it.
      await expect(card.getByText(text.ownExcluded, { exact: true })).toHaveCount(0);
      // D1: the owner's own positions are excluded unless switched on; Resume waits for
      // the owner after the owner's own Stop.
      const own = card.getByRole("checkbox", { name: text.includeOwn });
      const resume = card.getByRole("checkbox", { name: text.resumeToo });
      await expect(own).not.toBeChecked();
      await expect(resume).not.toBeChecked();
      await resume.check();
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await card.screenshot({ path: test.info().outputPath("owner-action-grant-ar.png") });
      }
      const authorize = card.getByRole("button", { name: text.authorize, exact: true });
      await authorize.click();
      // First time on this device: the same card asks for the password and registers it.
      await card.getByLabel(text.password, { exact: true }).fill("ci-only-owner-password");
      await card.getByRole("button", { name: text.register, exact: true }).click();
      await expect(card.getByLabel(text.password, { exact: true })).toHaveCount(0);
      await authorize.click();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card.getByRole("status")).toHaveText(text.signed);
      await expect(card.getByRole("button")).toHaveCount(0);
      const challenges = bodies.filter(([kind]) => kind === "challenge").map(([, body]) => body);
      expect(challenges.at(-1)).toEqual({ allow_manual_positions: false });
      const decision = bodies.find(([kind]) => kind === "decision")?.[1];
      expect(decision.decision).toBe("confirm");
      expect(decision.resume_trading).toBe(true);
      expect(decision.money_limit).toBe("apply");
      expect(decision.proof?.challenge_id).toBeTruthy();
      const permission = await (
        await context.request.get(`/api/agents/${state.agent.id}/permissions`)
      ).json();
      expect(permission.effective_level).toBe("autonomous");
      expect(permission.active_authorities[0].envelope.allow_manual_positions).toBe(false);
      expect(await state.read()).toEqual({ enabled: true, emergency_stop: false });
      const policy = await (
        await context.request.get(`/api/trading/accounts/${state.account}/execution-policy`)
      ).json();
      expect(Number(policy.risk.max_daily_loss)).toBe(300);
    } finally {
      await state.cleanup();
    }
  });

for (const locale of ["en", "ar"])
  test(`${locale}: a Resume card in the conversation resumes trading with one tap`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    const text = copy[locale];
    const state = await setup(context, locale);
    try {
      await state.controls({ enabled: true, emergency_stop: false });
      await state.controls({ enabled: false, emergency_stop: true });
      const seeded = seedCard({
        kind: "resume_trading",
        agent: state.agent.id,
        thread: state.thread.id,
      });
      const decisions = [];
      page.on("request", (request) => {
        if (request.method() === "POST" && request.url().includes("/api/owner-actions/"))
          decisions.push(request.postDataJSON());
      });
      await page.goto(`/app/${state.agent.id}`);
      const card = page.locator(`[data-owner-action="${seeded.id}"]`);
      await expect(card).toHaveAttribute("data-owner-action-status", "pending");
      await expect(card.locator("strong")).toHaveText(text.resumeTitle);
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        // The primary action starts the row on the reading side: right in Arabic.
        const [resume, later] = await Promise.all([
          card.locator('[data-owner-action-button="confirm"]').boundingBox(),
          card.locator('[data-owner-action-button="cancel"]').boundingBox(),
        ]);
        expect(resume && later && resume.x > later.x).toBeTruthy();
        await card.screenshot({ path: test.info().outputPath("owner-action-resume-ar.png") });
      }
      await card.getByRole("button", { name: text.resumeButton, exact: true }).click();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card.getByRole("status")).toHaveText(text.resumed);
      await expect(card.getByRole("button")).toHaveCount(0);
      expect(decisions).toEqual([{ decision: "confirm" }]);
      expect(await state.read()).toEqual({ enabled: true, emergency_stop: false });
      // The conversation confirms the change in one server-written line.
      await expect(
        // Written in the conversation's language (Arabic until the owner writes in English).
        page.getByText(/Trading resumed\. Each agent|استؤنف التداول\. يبقى/),
      ).toBeVisible();
    } finally {
      await state.cleanup();
    }
  });

for (const locale of ["en", "ar"])
  test(`${locale}: an uncertain trade card settles with one answer and never resends`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    const text = copy[locale];
    const state = await setup(context, locale);
    try {
      const seeded = seedCard({
        kind: "resolve_operation",
        account: state.account,
        symbol: state.data.symbol,
        agent: state.agent.id,
        thread: state.thread.id,
      });
      const sent = [];
      await page.route("**/api/trading/execute", async (route) => {
        sent.push(route.request().postDataJSON());
        await route.continue();
      });
      await page.goto(`/app/${state.agent.id}`);
      const card = page.locator(`[data-owner-action="${seeded.id}"]`);
      await expect(card.locator("strong")).toHaveText(text.resolveTitle);
      await expect(card.locator("[data-owner-action-button]")).toHaveCount(3);
      // "Unknown" says that it releases the hold; it never reads as "wait".
      await expect(card.locator('[data-owner-action-button="unknown"]')).toHaveText(text.unknown);
      await expect(card.getByText(state.data.symbol)).toBeVisible();
      if (locale === "ar")
        await card.screenshot({ path: test.info().outputPath("owner-action-resolve-ar.png") });
      await card.getByRole("button", { name: text.notExecuted, exact: true }).click();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card.getByRole("status")).toHaveText(text.recorded);
      const journal = await (
        await context.request.get(`/api/trading/journal?account_id=${state.account}`)
      ).json();
      const row = journal.find((item) => item.operation_id === seeded.operation_id);
      expect(row.status).toBe("resolved");
      expect(row.result.details.resolution.outcome).toBe("not_executed");
      expect(row.result.details.resolution.broker_confirmed).toBe(false);
      expect(sent).toEqual([]);
    } finally {
      await state.cleanup();
    }
  });

test("the safety sheet lifts a pause with one tap", async ({ page, context }) => {
  test.setTimeout(60000);
  const state = await setup(context, "en");
  try {
    const created = await context.request.post("/api/trading/restrictions", {
      headers: state.headers,
      data: { account_id: state.account, action_class: "no_new_entries" },
    });
    expect(created.status()).toBe(201);
    const pause = (await created.json()).id;
    await page.goto(`/app/${state.agent.id}`);
    await page.getByTestId("safety-pill").click();
    const sheet = page.getByTestId("safety-sheet");
    await sheet.locator(`[data-lift-restriction="${pause}"]`).click();
    await expect(sheet.getByText("No pauses", { exact: true })).toBeVisible();
    const current = await (
      await context.request.get(`/api/trading/restrictions?account_id=${state.account}`)
    ).json();
    expect(current.map((row) => row.id)).not.toContain(pause);
  } finally {
    await state.cleanup();
  }
});
