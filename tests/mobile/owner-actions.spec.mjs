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

const copy = {
  ar: {
    resume: "استئناف التداول",
    resumed: "استؤنف التداول.",
    resolveTitle: "الوسيط لم يؤكد هذه الصفقة",
    executed: "نُفذت",
    unknown: "غير معروفة — ارفع التعليق",
    recorded: "سُجّل: نُفذت (تصريحك، لا تأكيد من الوسيط).",
    lift: "رفع الإيقاف",
    noPauses: "لا توجد إيقافات",
  },
  en: {
    resume: "Resume trading",
    resumed: "Trading resumed.",
    resolveTitle: "The broker did not confirm this trade",
    executed: "It executed",
    unknown: "Unknown: release the hold",
    recorded: "Recorded: it executed (your statement, not broker confirmation).",
    lift: "Lift pause",
    noPauses: "No pauses",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: owner action cards in the thread act with one tap`, async ({
    page,
    context,
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
    const original = await (await context.request.get("/api/trading/controls")).json();
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
    let pause;
    try {
      for (const enabled of [true, false])
        await context.request.put("/api/trading/controls", {
          headers,
          data: { enabled, emergency_stop: false },
        });
      const resume = seedCard({ kind: "resume_trading", agent: agent.id, thread: thread.id });
      const uncertain = seedCard({
        kind: "resolve_operation",
        account: data.account,
        symbol: data.symbol,
        agent: agent.id,
        thread: thread.id,
      });
      await page.goto(`/thread?id=${thread.id}`);
      const resumeCard = page.getByTestId(`owner-action-${resume.id}`);
      await expect(resumeCard.getByText(text.resume).first()).toBeVisible();
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
      await resumeCard.getByRole("button", { name: text.resume, exact: true }).click();
      await expect(resumeCard.getByText(text.resumed, { exact: true })).toBeVisible();
      expect(await (await context.request.get("/api/trading/controls")).json()).toEqual({
        enabled: true,
        emergency_stop: false,
      });
      await resolveCard.getByRole("button", { name: text.executed, exact: true }).click();
      await expect(resolveCard.getByText(text.recorded, { exact: true })).toBeVisible();
      const journal = await (
        await context.request.get(`/api/trading/journal?account_id=${data.account}`)
      ).json();
      const row = journal.find((item) => item.operation_id === uncertain.operation_id);
      expect(row.status).toBe("resolved");
      expect(row.result.details.resolution.outcome).toBe("executed");
      // The header sheet lifts a pause with one tap too.
      const made = await context.request.post("/api/trading/restrictions", {
        headers,
        data: { account_id: data.account, action_class: "no_new_entries" },
      });
      expect(made.status()).toBe(201);
      pause = (await made.json()).id;
      await page.reload();
      await page.getByTestId("safety-pill").click();
      const sheet = page.getByTestId("safety-sheet");
      await sheet.getByRole("button", { name: text.lift, exact: true }).click();
      await expect(sheet.getByText(text.noPauses, { exact: true })).toBeVisible();
      pause = undefined;
    } finally {
      if (pause)
        await context.request.post(`/api/trading/restrictions/${pause}/revoke`, {
          headers,
          data: { reason: "" },
        });
      await context.request.put("/api/trading/controls", { headers, data: original });
      simulation({ ...data, action: "cleanup" });
    }
  });
