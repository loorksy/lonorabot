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
            if data['kind']=='resume_trading':
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
    recorded: "Recorded: it did not execute (your statement, not broker confirmation).",
    lift: "Lift pause",
  },
  ar: {
    resumeTitle: "استئناف التداول",
    resumeButton: "استئناف التداول",
    resumed: "استؤنف التداول.",
    resolveTitle: "الوسيط لم يؤكد هذه الصفقة",
    notExecuted: "لم تُنفذ",
    recorded: "سُجّل: لم تُنفذ (تصريحك، لا تأكيد من الوسيط).",
    lift: "رفع الإيقاف",
  },
};

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
