// Order lines on mobile, as on Web (Q30): one line per operation of the chat at its anchor,
// with its durable state; «Filled» only with evidence; the sheet shows the timeline and the
// evidence, never the raw operation or account id.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

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
                session.add(TradingJournalRow(operation_id=operation,owner_id=f.owner,account_id=data['account'],request_hash='ui-fixture',request={'account_id':data['account'],'action':'buy','symbol':data['symbol'],'volume':'0.10'},status='ambiguous',result={'status':'ambiguous','code':'broker_timeout','details':{'send_state':'sent','execution':{'agent_id':data['agent'],'send_authorized':True}}},submitted_at=utcnow(),updated_at=utcnow()))
                await session.flush()
                fields['operation_id']=operation
            proposal=OwnerActionProposal(**fields)
            if data['kind']=='grant_authority':
                from lonora_contracts.owner_actions import DailyLossDraft,GrantDraft
                from lonora_db.owner_actions import ALL_ACTIONS
                draft=GrantDraft(agent_id=data['agent'],account_id=data['account'],symbol_scope='selected',symbols=[data['symbol']],actions=list(ALL_ACTIONS),daily_loss=DailyLossDraft(amount='300.00',currency='USD',basis='suggested',percent='3',equity='10000'))
                if data.get('delegation')=='full':
                    # Preselected because the owner's own message asked for full delegation.
                    draft=draft.with_delegation('full')
                row,_=await propose(session,f.owner,proposal,card_id=str(uuid4()),agent_id=data['agent'],thread_id=data['thread'],run_id=None,grant=draft)
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
  const agent = await (
    await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Orders ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    })
  ).json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  return {
    data,
    agent,
    thread,
    remove: () => context.request.delete(`/api/agents/${agent.id}`, { headers }),
  };
}

test("each operation of the chat is a line at its anchor; the sheet shows the evidence", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  const now = new Date().toISOString();
  const message = (seq, content) => ({
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: seq === 1 ? null : data.agent.id,
    role: seq === 1 ? "user" : "assistant",
    seq,
    content,
    attachment_ids: [],
    reply_to: null,
    reactions: [],
    created_at: now,
  });
  const filledId = randomUUID(),
    uncertainId = randomUUID();
  const journal = [
    {
      operation_id: filledId,
      account_id: "account-raw-id",
      status: "confirmed",
      request: { action: "buy", symbol: "XAUUSD", volume: 0.1 },
      result: {
        status: "confirmed",
        broker_id: "771234",
        details: { price: 2400.5, volume: 0.1, verification: { status: "verified" } },
      },
      submitted_at: now,
      updated_at: now,
      thread_id: data.thread.id,
      timeline_seq: 1,
    },
    {
      operation_id: uncertainId,
      account_id: "account-raw-id",
      status: "ambiguous",
      request: { action: "close_position", symbol: "XAUUSD", volume: 0.05, position: "771234" },
      result: {},
      submitted_at: now,
      updated_at: now,
      thread_id: data.thread.id,
      timeline_seq: 2,
    },
    {
      operation_id: randomUUID(),
      account_id: "account-raw-id",
      status: "filled",
      request: { action: "sell", symbol: "EURUSD", volume: 1 },
      result: {},
      submitted_at: now,
      updated_at: now,
      thread_id: "another-thread",
      timeline_seq: 1,
    },
  ];
  await page.route(`**/api/threads/${data.thread.id}/messages*`, (route) =>
    route.fulfill({
      json: [message(1, "Buy gold"), message(2, "Bought."), message(3, "Closing half.")],
    }),
  );
  await page.route("**/api/trading/journal?thread_id=*", (route) =>
    route.fulfill({ json: journal }),
  );
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    const lines = page.getByTestId("order-line");
    await expect(lines).toHaveCount(2);
    await expect(page.getByText("EURUSD")).toHaveCount(0);
    const filled = page.getByRole("button", { name: /^Order Buy 0\.1 XAUUSD: Filled/ });
    await expect(filled).toBeVisible();
    const uncertain = page.getByRole("button", { name: /XAUUSD: Unconfirmed/ });
    await expect(uncertain).toBeVisible();

    await filled.click();
    await expect(page.getByText("Trade order", { exact: true })).toBeVisible();
    await expect(page.getByTestId("order-evidence")).toContainText(
      "Fill evidence: ticket 771234 · 2400.5",
    );
    await expect(page.getByTestId("order-sheet")).not.toContainText(filledId);
    await expect(page.getByTestId("order-sheet")).not.toContainText("account-raw-id");
    await page.reload();

    await uncertain.click();
    await expect(page.getByTestId("order-evidence")).toContainText(
      "«Filled» is never shown before the evidence",
    );
    await expect(page.getByTestId("order-sheet")).toContainText("No answer from the broker");
  } finally {
    await data.remove();
  }
});

test("«Resolve the operation» rests the list on the operation's own settle card", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const fixtureData = await fixture(context);
  const card = seedCard({
    kind: "resolve_operation",
    account: fixtureData.data.account,
    symbol: fixtureData.data.symbol,
    agent: fixtureData.agent.id,
    thread: fixtureData.thread.id,
  });
  const now = new Date().toISOString();
  const rows = Array.from({ length: 40 }, (_, index) => ({
    id: randomUUID(),
    thread_id: fixtureData.thread.id,
    agent_id: fixtureData.agent.id,
    role: "assistant",
    seq: index + 1,
    content: `Line ${index + 1}`,
    attachment_ids: [],
    reply_to: null,
    reactions: [],
    created_at: now,
  }));
  await page.route(`**/api/threads/${fixtureData.thread.id}/messages*`, (route) =>
    route.fulfill({ json: rows }),
  );
  await page.route("**/api/trading/journal?thread_id=*", (route) =>
    route.fulfill({
      json: [
        {
          operation_id: card.operation_id,
          account_id: fixtureData.data.account,
          status: "ambiguous",
          request: { action: "buy", symbol: fixtureData.data.symbol, volume: "0.10" },
          result: {},
          submitted_at: now,
          updated_at: now,
          thread_id: fixtureData.thread.id,
          timeline_seq: 40,
        },
      ],
    }),
  );
  try {
    await page.goto(`/thread?id=${fixtureData.thread.id}`);
    const settle = page.getByTestId(`owner-action-${card.id}`);
    // The order line is at the bottom; the settle card was raised when the chat began.
    await page.getByTestId("order-line").click();
    await expect(page.getByTestId("order-evidence")).toContainText(
      "never shown before the evidence",
    );
    await page.getByRole("button", { name: "Resolve the operation", exact: true }).click();
    await expect(page.getByTestId("order-sheet")).toHaveCount(0);
    await expect(settle).toBeInViewport();
  } finally {
    await fixtureData.remove();
  }
});
