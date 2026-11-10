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

// An agent created from chat, as agent_create creates it (no model): through the
// creation service and its Undo card only.
function seedCreation(data) {
  const script = `
import asyncio,json,sys
from uuid import uuid4
sys.path.insert(0,'tests')
from check_streaming import Fixture
from lonora_agent.collaboration.agent_create import create_from_spec
from lonora_db.owner_actions import raise_created_card
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            spec={'template':'trading','name':data['name'],'responsibility':'Watch gold for the owner.','account_id':data['account'],'symbol':data['symbol'],'connection_version':None,'model':None,'report_to':[]}
            row,_=await create_from_spec(session,f.owner,spec,agent_id=str(uuid4()),created_via='owner_message',created_by_agent_id=data['agent'],source_message_id=None,run_id=None)
            card=await raise_created_card(session,f.owner,row,agent_id=data['agent'],thread_id=data['thread'],run_id=None)
            print(json.dumps({'agent':row.id,'card':card.id}))
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
  en: {
    created: "Agent created",
    level: "Trading level: Ask me",
    task: "Its task: ⁨Watch gold for the owner.⁩",
    undo: "Undo",
    undone: "Undone: the agent was removed.",
    monitoring: /^Monitoring ⁨XAUUSD⁩ until /,
    cancel: "Cancel",
    condition: /⁨XAUUSD⁩ above ⁨2100⁩/,
  },
  ar: {
    created: "أُنشئ وكيل",
    level: "مستوى التداول: يسألني أولًا",
    task: "مهمته: ⁨Watch gold for the owner.⁩",
    undo: "تراجع",
    undone: "تم التراجع: أُزيل الوكيل.",
    monitoring: /^يراقب ⁨XAUUSD⁩ حتى /,
    cancel: "إلغاء",
    condition: /⁨XAUUSD⁩ فوق ⁨2100⁩/,
  },
};

for (const locale of ["en", "ar"])
  test(`${locale}: an agent created from chat shows its card with Undo, and a watch is cancelled from the status line`, async ({
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
    await context.addInitScript((value) => {
      localStorage.setItem("lonora.locale", value);
      // «حالة الوكيل التفصيلية» is a per-device preference, off by default (Q35).
      localStorage.setItem("lonora.chatPrefs", JSON.stringify({ agentStatus: true }));
    }, locale);
    const headers = {
      "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    const made = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Creator ${randomUUID().slice(0, 6)}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(made.status()).toBe(201);
    const creator = await made.json();
    const thread = await (
      await context.request.post(`/api/agents/${creator.id}/conversation`, { headers, data: {} })
    ).json();
    try {
      const name = `Gold agent ${randomUUID().slice(0, 6)}`;
      const seeded = seedCreation({
        name,
        agent: creator.id,
        thread: thread.id,
        account: data.account,
        symbol: data.symbol,
      });
      // A watch the creator keeps until the London close; the status line names it.
      const watch = await context.request.post("/api/watches", {
        headers,
        data: {
          agent_id: creator.id,
          payload: {
            kind: "price",
            account_id: data.account,
            symbol: data.symbol,
            condition: "above",
            level: "2100",
            prompt: "Gold above 2100",
            expires_at: new Date(Date.now() + 3 * 3600_000).toISOString(),
          },
        },
      });
      expect(watch.status()).toBe(201);
      const watchId = (await watch.json()).id;
      await page.goto(`/app/${creator.id}`);
      const card = page.locator(`[data-owner-action="${seeded.card}"]`);
      await expect(card).toHaveAttribute("data-owner-action-kind", "agent_created");
      // A change made without asking is one line with «تراجع» (reference noticeMarkup).
      const line_ = card.locator(".nt-text");
      await expect(line_).toContainText(text.created);
      await expect(line_).toContainText(name);
      // The stored task, word for word: the standing instruction the agent keeps.
      await expect(line_).toContainText(text.task);
      const line = page.getByTestId("agent-status-line");
      await expect(line).toHaveText(text.monitoring);
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        expect(await line_.evaluate((row) => getComputedStyle(row).direction)).toBe("rtl");
        await card.screenshot({ path: test.info().outputPath("agent-created-ar.png") });
      }
      await card.getByRole("button", { name: text.undo, exact: true }).click();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      // The real outcome of the Undo, word for word.
      await expect(card.getByRole("status")).toHaveText(text.undone);
      expect((await context.request.get(`/api/agents/${seeded.agent}`)).status()).toBe(404);
      // The status line opens the AgentSheet; its watches row opens «المراقبات»; Cancel there.
      await line.click();
      await page.locator("#dialog .ev-row").click();
      const item = page.locator(`#dialog [data-watch="${watchId}"]`);
      await expect(item).toContainText(text.condition);
      await item.getByRole("button", { name: text.cancel, exact: true }).click();
      await expect(item).toHaveCount(0);
      const stored = await (await context.request.get(`/api/watches/${watchId}`)).json();
      expect(stored.payload.enabled).toBe(false);
      expect(stored.state.code).toBe("watch_cancelled");
      await expect(line).not.toHaveText(text.monitoring);
    } finally {
      await context.request.delete(`/api/agents/${creator.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });
