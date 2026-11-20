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

const copy = {
  ar: {
    resolveTitle: "الوسيط لم يؤكد هذه الصفقة",
    executed: "نُفذت",
    unknown: "غير معروفة",
    recorded: "سُجّل: نُفذت (تصريحك، لا تأكيد من الوسيط).",
    grantTitle: "يتداول بنفسه",
    authorize: "التفويض بمفتاح المرور",
    notNow: "ليس الآن",
    dismissed: "تم التجاهل. لم يتغير شيء.",
  },
  en: {
    resolveTitle: "The broker did not confirm this trade",
    executed: "It executed",
    unknown: "Unknown",
    recorded: "Recorded: it executed (your statement, not broker confirmation).",
    grantTitle: "trade on its own",
    authorize: "Authorize with passkey",
    notNow: "Not now",
    dismissed: "Dismissed. Nothing changed.",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: owner action cards in the thread act with one tap`, async ({
    page,
    context,
    cleanup,
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
    const headers = {
      "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    const created = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native cards ${randomUUID().slice(0, 6)}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(created.status()).toBe(201);
    const agent = await created.json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    cleanup(() => simulation({ ...data, action: "cleanup" }));
    const uncertain = seedCard({
      kind: "settle_operation",
      account: data.account,
      symbol: data.symbol,
      agent: agent.id,
      thread: thread.id,
    });
    await page.goto(`/thread?id=${thread.id}`);
    const resolveCard = page.getByTestId(`owner-action-${uncertain.id}`);
    await expect(resolveCard.getByText(text.resolveTitle, { exact: true })).toBeVisible();
    await expect(resolveCard.getByText(data.symbol, { exact: false }).first()).toBeVisible();
    await expect(
      resolveCard.getByRole("button", { name: text.unknown, exact: true }),
    ).toBeVisible();
    if (locale === "ar")
      await resolveCard.screenshot({
        path: test.info().outputPath("owner-action-resolve-native-ar.png"),
      });
    const level = await (await context.request.get(`/api/agents/${agent.id}/permissions`)).json();
    expect(level.effective_level).toBe("supervised");
    await resolveCard.getByRole("button", { name: text.executed, exact: true }).click();
    await expect(resolveCard.getByText(text.recorded, { exact: true })).toBeVisible();
    const journal = await (
      await context.request.get(`/api/trading/journal?account_id=${data.account}`)
    ).json();
    const row = journal.find((item) => item.operation_id === uncertain.operation_id);
    expect(row.status).toBe("resolved");
    expect(row.result.details.resolution.outcome).toBe("executed");
  });

test("Expo ar: an expired Settle card asks again, then shows the newer card", async ({
  page,
  context,
  cleanup,
}) => {
  test.setTimeout(60000);
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
  const headers = {
    "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value,
  };
  const agent = await (
    await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Renew ${randomUUID().slice(0, 6)}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    })
  ).json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  cleanup(async () => {
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
    simulation({ ...data, action: "cleanup" });
  });

  const seeded = seedCard({
    kind: "settle_operation",
    account: data.account,
    symbol: data.symbol,
    agent: agent.id,
    thread: thread.id,
    expired: true,
  });
  await page.goto(`/thread?id=${thread.id}`);
  const card = page.getByTestId(`owner-action-${seeded.id}`);
  const renew = card.getByRole("button", { name: "طلب جديد", exact: true });
  await expect(renew).toBeVisible();
  const [renewed] = await Promise.all([
    page.waitForResponse((response) =>
      response.url().endsWith(`/api/owner-actions/${seeded.id}/renew`),
    ),
    renew.click(),
  ]);
  expect(renewed.status()).toBe(200);
  const fresh = await renewed.json();
  // The fresh card waits for the same operation; the old one now shows it, and never asks
  // again (the server would refuse a second renewal).
  await expect(page.getByTestId(`owner-action-${fresh.id}`)).toBeVisible();
  await expect(card.getByRole("button", { name: "عرض الأحدث", exact: true })).toBeVisible();
  await expect(renew).toHaveCount(0);
  // Settled, so its account can be removed: an unconfirmed operation blocks that.
  const settled = await context.request.post(`/api/owner-actions/${fresh.id}/decision`, {
    headers,
    data: { decision: "confirm", outcome: "not_executed" },
  });
  expect(settled.ok()).toBeTruthy();
});

test("Expo ar: a broker card whose connection failed says so, never that it is done", async ({
  page,
  context,
  cleanup,
}) => {
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
  const headers = {
    "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value,
  };
  const agent = await (
    await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Broker ${randomUUID().slice(0, 6)}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    })
  ).json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  cleanup(async () => {
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
    simulation({ ...data, action: "cleanup" });
  });

  // A saved broker card whose provisioning failed (D3), as /owner-actions returns it.
  const card = {
    id: randomUUID(),
    kind: "secret",
    status: "confirmed",
    status_reason: null,
    superseded_by: null,
    source: "agent",
    agent_id: agent.id,
    thread_id: thread.id,
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
  await page.goto(`/thread?id=${thread.id}`);
  const shown = page.getByTestId(`owner-action-${card.id}`);
  await expect(
    shown.getByText("تعذّر الربط. أوضحت لونورا السبب في المحادثة.", { exact: true }),
  ).toBeVisible();
  await expect(shown.getByText("حُفظت مشفّرة. لا يرى أي وكيل القيم.")).toHaveCount(0);
});

const mandate = {
  ar: { full: "وكّله", ask: "يستأذن", askNow: "الآن: يستأذن", fullNow: "الآن: وكّله" },
  en: { full: "Full", ask: "Ask", askNow: "Now: Ask", fullNow: "Now: Full" },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: the Mandate card switches the mode its button shows`, async ({
    page,
    context,
    cleanup,
  }) => {
    test.setTimeout(90000);
    const text = mandate[locale];
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
    const headers = {
      "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    const created = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native mandate ${randomUUID().slice(0, 6)}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(created.status()).toBe(201);
    const agent = await created.json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    cleanup(async () => {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    });
    const seeded = seedCard({ kind: "trading_mode", agent: agent.id, thread: thread.id });
    const decisions = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/api/owner-actions/"))
        decisions.push(request.postDataJSON());
    });
    await page.goto(`/thread?id=${thread.id}`);
    const card = page.getByTestId(`owner-action-${seeded.id}`);
    await expect(card.getByText(text.askNow, { exact: false })).toBeVisible();
    if (locale === "ar")
      await card.screenshot({
        path: test.info().outputPath("owner-action-mandate-native-ar.png"),
      });
    await card.getByRole("button", { name: text.full, exact: true }).click();
    await expect(card.getByText(text.fullNow, { exact: false })).toBeVisible();
    await card.getByRole("button", { name: text.ask, exact: true }).click();
    await expect(card.getByText(text.askNow, { exact: false })).toBeVisible();
    expect(decisions).toEqual([
      { decision: "confirm", trading_mode: "full" },
      { decision: "confirm", trading_mode: "ask" },
    ]);
  });

