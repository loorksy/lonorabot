// Gallery smoke: the harness on one card (review/ui-cards only).
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { eachVariant } from "./gallery.mjs";

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
            if data['kind']=='trading_mode':
                fields['agent_id']=data['agent']
            if data['kind']=='resolve_operation':
                operation=str(uuid4())
                session.add(TradingJournalRow(operation_id=operation,owner_id=f.owner,account_id=data['account'],request_hash='ui-fixture',request={'account_id':data['account'],'action':'buy','symbol':data['symbol'],'volume':'0.10'},status='ambiguous',result={'status':'ambiguous','code':'broker_timeout','details':{'send_state':'sent','execution':{'agent_id':data['agent'],'send_authorized':True}}},submitted_at=utcnow(),updated_at=utcnow()))
                await session.flush()
                fields['operation_id']=operation
            proposal=OwnerActionProposal(**fields)
            if data['kind']=='grant_authority':
                # The draft the tool resolves: this account, this pair, every action, until
                # stopped and own positions excluded (D1).
                from lonora_contracts.owner_actions import GrantDraft
                from lonora_db.owner_actions import ALL_ACTIONS
                draft=GrantDraft(agent_id=data['agent'],account_id=data['account'],symbol_scope='selected',symbols=[data['symbol']],actions=list(ALL_ACTIONS))
                if data.get('delegation')=='full':
                    # Preselected because the owner's own message asked for full delegation.
                    draft=draft.with_delegation('full')
                row,_=await propose(session,f.owner,proposal,card_id=str(uuid4()),agent_id=data['agent'],thread_id=data['thread'],run_id=None,grant=draft)
            elif data['kind']=='trading_mode':
                # As an agent proposes its own Mandate card.
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
  // The gallery harness sets the locale and theme per variant; no init script may force them.
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

test.use({ deviceScaleFactor: 2 });

test("gallery smoke: the Mandate card, pending, agent in Ask", async ({ page, context }) => {
  test.setTimeout(300_000);
  const state = await setup(context, "ar");
  try {
    const seeded = seedCard({
      kind: "trading_mode",
      agent: state.agent.id,
      thread: state.thread.id,
    });
    await page.goto(`/app/${state.agent.id}`);
    await eachVariant(page, "smoke", "mandate-pending-ask", async (p) => {
      const card = p.locator(`[data-owner-action="${seeded.id}"]`);
      await expect(card).toHaveAttribute("data-owner-action-status", "pending");
      return card;
    });
  } finally {
    await state.cleanup();
  }
});
