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

// Lonora (supervising every agent by default), a gold agent and a watcher that
// proposed to supervise it, as supervision_change raises the card without an owner
// message (no model involved).
function seedSupervision(data) {
  const script = `
import asyncio,json,sys
sys.path.insert(0,'tests')
from uuid import uuid4
from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate
from lonora_db.agents import create_agent
from lonora_db.owner_actions import propose_supervision
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.threads import conversation_thread
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            lonora=await ensure_personal_agent(session,f.owner)
            gold=await create_agent(session,f.owner,AgentCreate(name=data['gold'],scope_mode='flexible'))
            watcher=await create_agent(session,f.owner,AgentCreate(name=data['watcher'],scope_mode='flexible'))
            thread=await conversation_thread(session,f.owner,watcher.id)
            card,_=await propose_supervision(session,f.owner,watcher.id,[gold.id],card_id=str(uuid4()),agent_id=watcher.id,thread_id=thread.id,run_id=None)
            print(json.dumps({'lonora':lonora.id,'gold':gold.id,'watcher':watcher.id,'thread':thread.id,'card':card.id}))
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
    section: "Lonora supervises your agents",
    byDefault: "by default",
    stop: "Stop",
    supervise: "Supervise",
    notSupervised: "Not supervised by Lonora",
    title: "Let it supervise?",
    allow: "Allow",
    set: "Supervision set.",
  },
  ar: {
    section: "لونورا تشرف على وكلائك",
    byDefault: "افتراضيًا",
    stop: "إيقاف",
    supervise: "إشراف",
    notSupervised: "لا تشرف عليهم لونورا",
    title: "السماح له بالإشراف؟",
    allow: "السماح",
    set: "تم تعيين الإشراف.",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: Lonora's profile stops and restores supervision, and a card sets it`, async ({
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
    const suffix = randomUUID().slice(0, 6);
    const seeded = seedSupervision({ gold: `Gold ${suffix}`, watcher: `Watcher ${suffix}` });
    try {
      await page.goto(`/bot-settings?botId=${seeded.lonora}`);
      const section = page.getByTestId("supervision-settings");
      await expect(section.getByText(text.section, { exact: true })).toBeVisible();
      await expect(section.getByText(`⁨Gold ${suffix}⁩`, { exact: true })).toBeVisible();
      await expect(section.getByText(text.byDefault, { exact: true }).first()).toBeVisible();
      if (locale === "ar")
        await section.screenshot({ path: test.info().outputPath("supervision-native-ar.png") });
      await page.getByTestId(`supervision-stop-${seeded.gold}`).click();
      await expect(section.getByText(text.notSupervised, { exact: true })).toBeVisible();
      await page.getByTestId(`supervision-add-${seeded.gold}`).click();
      await expect(page.getByTestId(`supervision-stop-${seeded.gold}`)).toBeVisible();
      const view = await (
        await context.request.get(`/api/supervision?agent_id=${seeded.gold}`)
      ).json();
      expect(view.supervised_by.map((grant) => grant.created_via)).toEqual(["owner_ui"]);

      await page.goto(`/thread?id=${seeded.thread}`);
      const card = page.getByTestId(`owner-action-${seeded.card}`);
      await expect(card.getByText(text.title, { exact: true })).toBeVisible();
      await card.getByRole("button", { name: text.allow, exact: true }).click();
      await expect(card.getByText(text.set, { exact: true })).toBeVisible();
      const after = await (
        await context.request.get(`/api/supervision?agent_id=${seeded.watcher}`)
      ).json();
      expect(after.supervises.map((grant) => grant.supervised.id)).toEqual([seeded.gold]);
    } finally {
      for (const id of [seeded.gold, seeded.watcher])
        await context.request.delete(`/api/agents/${id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });
