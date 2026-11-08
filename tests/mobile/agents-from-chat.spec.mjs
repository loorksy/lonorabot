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

// An agent created from chat, as agent_create creates it (no model).
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
            spec={'template':'research','name':data['name'],'responsibility':'Follow economic news.','account_id':None,'symbol':None,'connection_version':None,'model':None,'report_to':[data['agent']]}
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
  ar: {
    created: "أُنشئ وكيل",
    template: "وكيل أبحاث",
    level: "مستوى التداول: لا يتداول",
    task: "مهمته: ⁨Follow economic news.⁩",
    keep: "إبقاؤه",
    kept: "أُبقي الوكيل.",
    monitoring: "يراقب",
    cancel: "إلغاء",
  },
  en: {
    created: "Agent created",
    template: "Research agent",
    level: "Trading level: No trading",
    task: "Its task: ⁨Follow economic news.⁩",
    keep: "Keep it",
    kept: "Kept.",
    monitoring: "Monitoring",
    cancel: "Cancel",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: a created agent's card and the status line's watch list`, async ({
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
    const made = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native creator ${randomUUID().slice(0, 6)}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(made.status()).toBe(201);
    const creator = await made.json();
    const thread = await (
      await context.request.post(`/api/agents/${creator.id}/conversation`, { headers, data: {} })
    ).json();
    let created;
    try {
      const name = `News agent ${randomUUID().slice(0, 6)}`;
      const seeded = seedCreation({ name, agent: creator.id, thread: thread.id });
      created = seeded.agent;
      const watch = await context.request.post("/api/watches", {
        headers,
        data: {
          agent_id: creator.id,
          payload: {
            kind: "price",
            account_id: data.account,
            symbol: data.symbol,
            condition: "below",
            level: "150",
            prompt: "Gold below 150",
            expires_at: new Date(Date.now() + 2 * 3600_000).toISOString(),
          },
        },
      });
      expect(watch.status()).toBe(201);
      const watchId = (await watch.json()).id;
      await page.goto(`/thread?id=${thread.id}`);
      const card = page.getByTestId(`owner-action-${seeded.card}`);
      await expect(card.getByText(text.created, { exact: true })).toBeVisible();
      await expect(card.getByText(`${text.template} · ⁨${name}⁩`, { exact: true })).toBeVisible();
      await expect(card.getByText(text.level, { exact: true })).toBeVisible();
      await expect(card.getByText(text.task, { exact: true })).toBeVisible();
      if (locale === "ar")
        await card.screenshot({ path: test.info().outputPath("agent-created-native-ar.png") });
      await card.getByRole("button", { name: text.keep, exact: true }).click();
      await expect(card.getByText(text.kept, { exact: true })).toBeVisible();
      expect((await context.request.get(`/api/agents/${seeded.agent}`)).status()).toBe(200);
      const live = page.getByTestId("agent-live-state");
      await expect(live.getByText(text.monitoring, { exact: false })).toBeVisible();
      await live.getByRole("button").first().click();
      const row = page.getByTestId(`agent-watch-${watchId}`);
      await expect(row).toBeVisible();
      await row.getByRole("button", { name: text.cancel, exact: true }).click();
      await expect(row).toHaveCount(0);
      const stored = await (await context.request.get(`/api/watches/${watchId}`)).json();
      expect(stored.payload.enabled).toBe(false);
    } finally {
      if (created) await context.request.delete(`/api/agents/${created}`, { headers });
      await context.request.delete(`/api/agents/${creator.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });
