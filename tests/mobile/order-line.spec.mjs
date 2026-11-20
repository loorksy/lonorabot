// Order lines on mobile, as on Web (Q30): one line per operation of the chat at its anchor,
// with its durable state, except a confirmed one, which is its Execution Receipt (10.3);
// «Filled» only with evidence; the sheet shows the timeline and the evidence, never the raw
// operation or account id.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "../ui-test.mjs";

const genui = (command, input = {}) =>
  JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_genui_browser.py", command], {
      input: JSON.stringify(input),
      encoding: "utf8",
    }),
  );

// Cards as the runtime raises them (no model): through lonora_db.owner_actions only.
function seedCard(data) {
  const script = `
import asyncio,json,sys
from uuid import uuid4
sys.path.insert(0,'tests')
from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_db.owner_actions import raise_system_card
from lonora_db.schema import TradingJournalRow
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            fields={'kind':data['kind']}
            operation=str(uuid4())
            session.add(TradingJournalRow(operation_id=operation,owner_id=f.owner,account_id=data['account'],request_hash='ui-fixture',request={'account_id':data['account'],'action':'buy','symbol':data['symbol'],'volume':'0.10'},status='ambiguous',result={'status':'ambiguous','code':'broker_timeout','details':{'send_state':'sent','execution':{'agent_id':data['agent'],'send_authorized':True}}},submitted_at=utcnow(),updated_at=utcnow()))
            await session.flush()
            fields['operation_id']=operation
            proposal=OwnerActionProposal(**fields)
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

test("each operation of the chat is a line at its anchor, a confirmed one only its receipt; the sheet shows the evidence", async ({
  page,
  context,
  cleanup,
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
    uncertainId = randomUUID(),
    confirmedId = randomUUID();
  const journal = [
    {
      // Broker-confirmed: shown once, as its Execution Receipt, never as an order line.
      operation_id: confirmedId,
      account_id: "account-raw-id",
      status: "confirmed",
      request: { action: "buy", symbol: "XAGUSD", volume: 2 },
      result: {
        status: "confirmed",
        broker_id: "771230",
        details: { price: 30.5, volume: 2, verification: { status: "verified" } },
      },
      submitted_at: now,
      updated_at: now,
      thread_id: data.thread.id,
      timeline_seq: 1,
    },
    {
      // Settled by the owner's statement that it was executed: «Filled» on that evidence.
      operation_id: filledId,
      account_id: "account-raw-id",
      status: "resolved",
      request: { action: "buy", symbol: "XAUUSD", volume: 0.1 },
      result: {
        status: "resolved",
        details: { resolution: { source: "owner", outcome: "executed" } },
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
  await page.route("**/api/trading/receipts?thread_id=*", (route) =>
    route.fulfill({
      json: [
        {
          operation_id: confirmedId,
          thread_id: data.thread.id,
          timeline_seq: 1,
          agent_id: data.agent.id,
          created_at: now,
          kind: "fill",
          action: "buy",
          symbol: "XAGUSD",
          ticket: "771230",
          volume: "2",
          price: "30.5",
          partial: false,
          reason: null,
          verification: "verified",
        },
      ],
    }),
  );
  cleanup(() => data.remove());
  await page.goto(`/thread?id=${data.thread.id}`);
  const lines = page.getByTestId("order-line");
  const receipts = page.getByTestId("execution-receipt");
  await expect(receipts).toHaveCount(1);
  await expect(receipts).toContainText("XAGUSD");
  await expect(lines).toHaveCount(2);
  await expect(lines.filter({ hasText: "XAGUSD" })).toHaveCount(0);
  await expect(page.getByText("EURUSD")).toHaveCount(0);
  const filled = page.getByRole("button", { name: /^Order Buy 0\.1 XAUUSD: Filled/ });
  await expect(filled).toBeVisible();
  const uncertain = page.getByRole("button", { name: /XAUUSD: Unconfirmed/ });
  await expect(uncertain).toBeVisible();

  await filled.click();
  await expect(page.getByText("Trade order", { exact: true })).toBeVisible();
  await expect(page.getByTestId("order-evidence")).toHaveText(
    "Recorded from your statement, not broker confirmation",
  );
  await expect(page.getByTestId("order-sheet")).not.toContainText(filledId);
  await expect(page.getByTestId("order-sheet")).not.toContainText("account-raw-id");
  await page.reload();

  await uncertain.click();
  await expect(page.getByTestId("order-evidence")).toContainText(
    "«Filled» is never shown before the evidence",
  );
  await expect(page.getByTestId("order-sheet")).toContainText("No answer from the broker");
});

test("the open sheet follows its operation's current state, and closes once it is confirmed", async ({
  page,
  context,
  cleanup,
}) => {
  test.setTimeout(90000);
  const data = await fixture(context);
  const now = new Date().toISOString();
  const ambiguous = {
    operation_id: randomUUID(),
    account_id: "account-raw-id",
    status: "ambiguous",
    request: { action: "buy", symbol: "XAUUSD", volume: 0.1 },
    result: {},
    submitted_at: now,
    updated_at: now,
    thread_id: data.thread.id,
    timeline_seq: 1,
  };
  let row = ambiguous;
  await page.route(`**/api/threads/${data.thread.id}/messages*`, (route) =>
    route.fulfill({
      json: [
        {
          id: randomUUID(),
          thread_id: data.thread.id,
          agent_id: null,
          role: "user",
          seq: 1,
          content: "Buy gold",
          attachment_ids: [],
          reply_to: null,
          reactions: [],
          created_at: now,
        },
      ],
    }),
  );
  await page.route("**/api/trading/journal?thread_id=*", (route) => route.fulfill({ json: [row] }));
  cleanup(() => data.remove());
  await page.goto(`/thread?id=${data.thread.id}`);
  await page.getByRole("button", { name: /XAUUSD: Unconfirmed/ }).click();
  const evidence = page.getByTestId("order-evidence");
  await expect(evidence).toContainText("«Filled» is never shown before the evidence");
  // The owner settles it as executed: the next read redraws the open sheet from it.
  row = {
    ...ambiguous,
    status: "resolved",
    result: {
      status: "resolved",
      details: { resolution: { source: "owner", outcome: "executed" } },
    },
  };
  await expect(evidence).toHaveText("Recorded from your statement, not broker confirmation", {
    timeout: 30000,
  });
  // Confirmed, it is its Execution Receipt: no line, and the sheet closes.
  row = { ...ambiguous, status: "confirmed", result: { status: "confirmed" } };
  await expect(page.getByTestId("order-sheet")).toHaveCount(0, { timeout: 30000 });
  await expect(page.getByTestId("order-line")).toHaveCount(0);
});

test("«Resolve the operation» rests the list on the operation's own settle card", async ({
  page,
  context,
  cleanup,
}) => {
  test.setTimeout(60000);
  const fixtureData = await fixture(context);
  const card = seedCard({
    kind: "settle_operation",
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
  cleanup(() => fixtureData.remove());
  const actions = page.waitForResponse((r) => r.url().includes("/api/owner-actions?thread_id="));
  await page.goto(`/thread?id=${fixtureData.thread.id}`);
  // The sheet is drawn from the cards the chat has read: open it once they are in.
  await actions;
  const settle = page.getByTestId(`owner-action-${card.id}`);
  // The order line is at the bottom; the settle card was raised when the chat began.
  await page.getByTestId("order-line").click();
  await expect(page.getByTestId("order-evidence")).toContainText("never shown before the evidence");
  await page.getByRole("button", { name: "Resolve the operation", exact: true }).click();
  await expect(page.getByTestId("order-sheet")).toHaveCount(0);
  await expect(settle).toBeInViewport();
});

test("«Resolve the operation» reaches the settle card drawn in the agent's message (a slot)", async ({
  page,
  context,
  cleanup,
}) => {
  test.setTimeout(90000);
  const fixture = genui("setup");
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const headers = {
    "X-CSRF-Token": fixture.cookies.find((row) => row.name === "lonora_csrf").value,
  };
  const input = { thread_id: fixture.thread.id, connection: fixture.connection };
  const ids = genui("records", input);
  genui("slots", { ...input, card: "settle", record: ids.settle });
  const saved = await (
    await context.request.get(`/api/threads/${fixture.thread.id}/messages`)
  ).json();
  const card = (
    await (await context.request.get(`/api/owner-actions?thread_id=${fixture.thread.id}`)).json()
  ).find((row) => row.id === ids.settle);
  const now = new Date().toISOString();
  const last = Math.max(...saved.map((row) => row.seq));
  const filler = Array.from({ length: 40 }, (_, index) => ({
    id: randomUUID(),
    thread_id: fixture.thread.id,
    agent_id: fixture.agent.id,
    role: "assistant",
    seq: last + index + 1,
    content: `Line ${index + 1}`,
    attachment_ids: [],
    reply_to: null,
    reactions: [],
    created_at: now,
  }));
  await page.route(`**/api/threads/${fixture.thread.id}/messages*`, (route) =>
    route.fulfill({ json: [...saved, ...filler] }),
  );
  await page.route("**/api/trading/journal?thread_id=*", (route) =>
    route.fulfill({
      json: [
        {
          operation_id: card.facts.operation.operation_id,
          account_id: fixture.connection,
          status: "ambiguous",
          request: { action: "sell", symbol: "XAGUSD", volume: "1" },
          result: {},
          submitted_at: now,
          updated_at: now,
          thread_id: fixture.thread.id,
          timeline_seq: last + 40,
        },
      ],
    }),
  );
  const actions = page.waitForResponse((r) => r.url().includes("/api/owner-actions?thread_id="));
  cleanup(() => context.request.delete(`/api/agents/${fixture.agent.id}`, { headers }));
  await page.goto(`/thread?id=${fixture.thread.id}`);
  await actions;
  const slot = page.getByTestId("ui-slot-settle");
  await page.getByTestId("order-line").click();
  const resolve = page.getByRole("button", { name: "Resolve the operation", exact: true });
  await expect(resolve).toBeVisible();
  await resolve.click();
  await expect(page.getByTestId("order-sheet")).toHaveCount(0);
  await expect(slot).toBeInViewport();
  // The card has no row of its own: the one settle card on the page is the slot's.
  await expect(page.getByTestId(`owner-action-${ids.settle}`)).toHaveCount(1);
  await expect(slot.getByTestId(`owner-action-${ids.settle}`)).toHaveCount(1);
});
