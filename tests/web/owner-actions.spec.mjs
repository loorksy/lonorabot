import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "../ui-test.mjs";

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
from datetime import timedelta
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
            if data['kind']=='trading_mode':
                fields['agent_id']=data['agent']
            if data['kind']=='settle_operation':
                operation=str(uuid4())
                session.add(TradingJournalRow(operation_id=operation,owner_id=f.owner,account_id=data['account'],request_hash='ui-fixture',request={'account_id':data['account'],'action':'buy','symbol':data['symbol'],'volume':'0.10'},status='ambiguous',result={'status':'ambiguous','code':'broker_timeout','details':{'send_state':'sent','execution':{'agent_id':data['agent'],'send_authorized':True}}},submitted_at=utcnow(),updated_at=utcnow()))
                await session.flush()
                fields['operation_id']=operation
            proposal=OwnerActionProposal(**fields)
            if data['kind']=='trading_mode':
                # As an agent proposes its own Mandate card.
                row,_=await propose(session,f.owner,proposal,card_id=str(uuid4()),agent_id=data['agent'],thread_id=data['thread'],run_id=None)
            else:
                row=await raise_system_card(session,f.owner,proposal,agent_id=data['agent'],thread_id=data['thread'],run_id=None)
            if data.get('expired'):
                # A stored card whose server lifetime ran out while the outcome stays unknown.
                row.expires_at=utcnow()-timedelta(minutes=1)
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
  return {
    data,
    headers,
    account,
    agent,
    thread,
    async cleanup() {
      // Every test's own agent goes; leaked ones count against the agent-creation cap.
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    },
  };
}

const copy = {
  en: {
    settleKind: "Unconfirmed operation",
    resolveTitle: "The broker did not confirm this trade",
    hold: "New risk on this market is held until it settles; exits stay allowed.",
    renew: "New request",
    notExecuted: "It did not execute",
    unknown: "Unknown",
    recorded: "Recorded: it did not execute (your statement, not broker confirmation).",
    grantTitle: "trade on its own",
    authorize: "Authorize with passkey",
    includeOwn: "Include positions I opened myself",
    password: "Account password",
    register: "Register this device first",
    signed: "Signed. It trades on its own inside this grant.",
    ownExcluded: "Positions you opened yourself are excluded",
  },
  ar: {
    settleKind: "عملية غير مؤكَّدة",
    resolveTitle: "الوسيط لم يؤكد هذه الصفقة",
    hold: "المخاطرة الجديدة على هذا السوق معلّقة حتى تُحسم؛ يبقى الخروج متاحًا.",
    renew: "طلب جديد",
    latest: "عرض الأحدث",
    notExecuted: "لم تُنفذ",
    unknown: "غير معروفة",
    recorded: "سُجّل: لم تُنفذ (تصريحك، لا تأكيد من الوسيط).",
    grantTitle: "يتداول بنفسه",
    authorize: "التفويض بمفتاح المرور",
    includeOwn: "اشمل المراكز التي فتحتها بنفسي",
    password: "كلمة مرور الحساب",
    register: "سجّل هذا الجهاز أولًا",
    signed: "وُقّع. يتداول بنفسه ضمن هذا التفويض.",
    ownExcluded: "لا يشمل المراكز التي فتحتها بنفسك",
  },
};

const mandateCopy = {
  en: {
    title: "Trading mode",
    full: "Full",
    ask: "Ask",
    askNow: "Now: Ask",
    fullNow: "Now: Full",
  },
  ar: {
    title: "التفويض",
    full: "وكّله",
    ask: "يستأذن",
    askNow: "الآن: يستأذن",
    fullNow: "الآن: وكّله",
  },
};

for (const locale of ["en", "ar"])
  test(`${locale}: the Mandate card shows the mode now and one button for the other mode`, async ({
    page,
    context,
    cleanup,
  }) => {
    test.setTimeout(60000);
    const text = mandateCopy[locale];
    const state = await setup(context, locale);
    cleanup(async () => {
      await state.cleanup();
    });

    const seeded = seedCard({
      kind: "trading_mode",
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
    await expect(card.locator(".oa-kind")).toHaveText(text.title);
    await expect(card).toContainText(text.askNow);
    // One button, for the other mode.
    await expect(card.locator("[data-owner-action-button]")).toHaveCount(1);
    if (locale === "ar") {
      await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
      await card.screenshot({ path: test.info().outputPath("owner-action-mandate-ar.png") });
    }
    const line = page.locator(".msg.k-oa", { has: card }).locator(".msg-line");
    const before = (await line.boundingBox()).width;
    await card.getByRole("button", { name: text.full, exact: true }).click();
    await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
    await expect(card).toContainText(text.fullNow);
    // A tapped Mandate card keeps its frame and its width (10.2.2, v38).
    expect((await line.boundingBox()).width).toBe(before);
    // Still the agent's switch: the button now shows Ask, and applies exactly Ask.
    await card.getByRole("button", { name: text.ask, exact: true }).click();
    await expect(card).toContainText(text.askNow);
    await expect(card.getByRole("button", { name: text.full, exact: true })).toBeVisible();
    expect(decisions).toEqual([
      { decision: "confirm", trading_mode: "full" },
      { decision: "confirm", trading_mode: "ask" },
    ]);
  });

for (const locale of ["en", "ar"])
  test(`${locale}: an uncertain trade card settles with one answer and never resends`, async ({
    page,
    context,
    cleanup,
  }) => {
    test.setTimeout(60000);
    const text = copy[locale];
    const state = await setup(context, locale);
    cleanup(async () => {
      await state.cleanup();
    });

    const seeded = seedCard({
      kind: "settle_operation",
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
    // v38: the kind in the head, the broker's silence as the title; no timer.
    await expect(card.locator(".oa-kind")).toHaveText(text.settleKind);
    await expect(card.locator(".oa-title")).toHaveText(text.resolveTitle);
    await expect(card.locator(".oa-exp")).toHaveCount(0);
    await expect(card.locator("[data-owner-action-button]")).toHaveCount(3);
    await expect(card.locator('[data-owner-action-button="unknown"]')).toHaveText(text.unknown);
    // The hint keeps the true safety sentence: new risk on this market stays held while the
    // outcome is unknown, and exits stay allowed (admission; 6).
    await expect(card.locator(".oa-hint")).toContainText(text.hold);
    await expect(card.getByText(state.data.symbol)).toBeVisible();
    if (locale === "ar") {
      await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
      // The first answer starts the row on the reading side: right in Arabic.
      const [first, next] = await Promise.all([
        card.locator('[data-owner-action-button="executed"]').boundingBox(),
        card.locator('[data-owner-action-button="not_executed"]').boundingBox(),
      ]);
      expect(first && next && first.x > next.x).toBeTruthy();
      await card.screenshot({ path: test.info().outputPath("owner-action-resolve-ar.png") });
    }
    await card.getByRole("button", { name: text.notExecuted, exact: true }).click();
    await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
    await expect(card.getByRole("status")).toHaveText(text.recorded);
    // Never folded (10.2.2): the answered card keeps its frame, in an unchanged wrapper.
    await expect(card.locator(".oa-kind")).toHaveText(text.settleKind);
    await expect(card.locator(".oa-title")).toHaveText(text.resolveTitle);
    await expect(card.getByText(state.data.symbol)).toBeVisible();
    await expect(page.locator(".msg.k-oa", { has: card })).toHaveCount(1);
    await expect(page.locator(".oa-line, .msg.k-line")).toHaveCount(0);
    const journal = await (
      await context.request.get(`/api/trading/journal?account_id=${state.account}`)
    ).json();
    const row = journal.find((item) => item.operation_id === seeded.operation_id);
    expect(row.status).toBe("resolved");
    expect(row.result.details.resolution.outcome).toBe("not_executed");
    expect(row.result.details.resolution.broker_confirmed).toBe(false);
    expect(sent).toEqual([]);
  });

test("ar: an expired Settle card keeps its frame and asks again from inside it", async ({
  page,
  context,
  cleanup,
}) => {
  const text = copy.ar;
  const state = await setup(context, "ar");
  cleanup(async () => {
    await state.cleanup();
  });

  const seeded = seedCard({
    kind: "settle_operation",
    account: state.account,
    symbol: state.data.symbol,
    agent: state.agent.id,
    thread: state.thread.id,
    expired: true,
  });
  await page.goto(`/app/${state.agent.id}`);
  const card = page.locator(`[data-owner-action="${seeded.id}"]`);
  await expect(card).toHaveAttribute("data-owner-action-status", "expired");
  // Never folded (10.2.2): its kind, title and operation, with «طلب جديد» inside the frame.
  await expect(card.locator(".oa-kind")).toHaveText(text.settleKind);
  await expect(card.locator(".oa-title")).toHaveText(text.resolveTitle);
  await expect(card.getByText(state.data.symbol)).toBeVisible();
  await expect(page.locator(".msg.k-oa", { has: card })).toHaveCount(1);
  const [renewed] = await Promise.all([
    page.waitForResponse((response) =>
      response.url().endsWith(`/api/owner-actions/${seeded.id}/renew`),
    ),
    card.locator(".oa-actions").getByRole("button", { name: text.renew, exact: true }).click(),
  ]);
  expect(renewed.status()).toBe(200);
  // «طلب جديد» asks again: a fresh card for the same operation waits; nothing is decided.
  const fresh = await renewed.json();
  expect(fresh.id).not.toBe(seeded.id);
  expect(fresh.kind).toBe("settle_operation");
  expect(fresh.status).toBe("pending");
  expect(fresh.facts.operation.operation_id).toBe(seeded.operation_id);
  // Once renewed, the old card shows the newer one, never «طلب جديد» again (which the
  // server would refuse).
  await page.reload();
  await expect(card).toHaveAttribute("data-owner-action-status", "expired");
  await expect(card.getByRole("button", { name: text.renew, exact: true })).toHaveCount(0);
  await expect(card.getByRole("button", { name: text.latest, exact: true })).toBeVisible();
  await expect(page.locator(`[data-owner-action="${fresh.id}"]`)).toHaveCount(1);
});

test("ar: a broker card whose connection failed shows its failed end state inside the frame", async ({
  page,
  context,
  cleanup,
}) => {
  const state = await setup(context, "ar");
  cleanup(async () => {
    await state.cleanup();
  });

  // A saved broker card whose provisioning failed (D3), as /owner-actions returns it.
  const card = {
    id: randomUUID(),
    kind: "secret",
    status: "confirmed",
    status_reason: null,
    superseded_by: null,
    source: "agent",
    agent_id: state.agent.id,
    thread_id: state.thread.id,
    run_id: null,
    timeline_seq: 1,
    facts: {
      several_accounts: false,
      secret: {
        label: "70000001 @ Exness-MT5Trial16",
        fields: [{ key: "PASSWORD", label: "كلمة مرور التداول", secret: true }],
        destination: "broker",
        agent_name: "Lonora",
        account: { login: "70000001", server: "Exness-MT5Trial16", platform: "mt5" },
      },
    },
    requires_passkey: false,
    result: { provisioning: "failed" },
    expires_at: null,
    decided_at: new Date().toISOString(),
    decided_via: "owner",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  await page.route("**/api/owner-actions?*", (route) => route.fulfill({ json: [card] }));
  await page.goto(`/app/${state.agent.id}`);
  const frame = page.locator(`[data-owner-action="${card.id}"]`);
  await expect(frame).toHaveAttribute("data-owner-action-kind", "secret");
  // Never folded, and its end state is the failure in the neutral tint, never «Done».
  await expect(page.locator(".oa-line")).toHaveCount(0);
  const done = frame.locator(".oa-done");
  await expect(done).toHaveText("تعذّر الربط. أوضحت لونورا السبب في المحادثة.");
  await expect(done).toHaveClass(/\bbad\b/);
  await expect(done).toHaveAttribute("data-owner-action-failed", "true");
});
