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

// A news agent whose cards ask the owner to add a news feed (a secure form) and to trust
// another feed's site, as the tools raise them (no model involved).
function seedCards(data) {
  const script = `
import asyncio,json,sys
sys.path.insert(0,'tests')
from uuid import uuid4
from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate
from lonora_db.agents import create_agent
from lonora_db.capability_cards import credential_payload, source_payload, trust_subject
from lonora_db.owner_actions import propose_capability
from lonora_db.threads import conversation_thread
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            agent=await create_agent(session,f.owner,AgentCreate(name=data['agent'],scope_mode='flexible'))
            thread=await conversation_thread(session,f.owner,agent.id)
            subject,payload=credential_payload('news_feed',None)
            credential,_=await propose_capability(session,f.owner,'connect_credential',subject,payload,card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            domain=data['domain']
            trust,_=await propose_capability(session,f.owner,'trust_source',trust_subject('feed_domain',domain),source_payload('feed_domain',domain),card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            print(json.dumps({'agent':agent.id,'thread':thread.id,'credential':credential.id,'trust':trust.id}))
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
    connectTitle: "إضافة موجز أخبار",
    name: "الاسم",
    url: "عنوان الموجز",
    connect: "ربط",
    connected: "تم الربط. لا يرى الوكلاء إلا أنه مُعدّ.",
    trustTitle: "الوثوق بهذا المصدر؟",
    trust: "ثقة",
    trusted: "صار موثوقًا.",
    title: "القدرات",
    remove: "إزالة",
  },
  en: {
    connectTitle: "Add a news feed",
    name: "Name",
    url: "Feed URL",
    connect: "Connect",
    connected: "Connected. Agents see only that it is configured.",
    trustTitle: "Trust this source?",
    trust: "Trust",
    trusted: "Trusted.",
    title: "Capabilities",
    remove: "Remove",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: a feed form and a trust card in the chat, then Capabilities`, async ({
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
    const suffix = randomUUID().slice(0, 8);
    const site = `site-${suffix}.analyst.example`;
    const feed = `https://desk-${suffix}.news.example/rss`;
    const seeded = seedCards({ agent: `News ${suffix}`, domain: site });
    try {
      await page.goto(`/thread?id=${seeded.thread}`);
      const card = page.getByTestId(`owner-action-${seeded.credential}`);
      await expect(card.getByText(text.connectTitle, { exact: true })).toBeVisible();
      await card.getByLabel(text.name, { exact: true }).fill(`Desk ${suffix}`);
      await card.getByLabel(text.url, { exact: true }).fill(feed);
      if (locale === "ar")
        await card.screenshot({ path: test.info().outputPath("credential-native-ar.png") });
      await card.getByRole("button", { name: text.connect, exact: true }).click();
      await expect(card.getByText(text.connected, { exact: true })).toBeVisible();

      const trust = page.getByTestId(`owner-action-${seeded.trust}`);
      await expect(trust.getByText(text.trustTitle, { exact: true })).toBeVisible();
      await expect(trust).toContainText(`⁨${site}⁩`);
      await trust.getByRole("button", { name: text.trust, exact: true }).click();
      await expect(trust.getByText(text.trusted, { exact: true })).toBeVisible();

      await page.goto("/integrations");
      await expect(page.getByText(text.title, { exact: true }).first()).toBeVisible();
      const report = await (await context.request.get("/api/capabilities")).json();
      const added = report.integrations.find((item) => item.name === `Desk ${suffix}`);
      expect(added.type).toBe("news_feed");
      expect(added.domain).toBe(`desk-${suffix}.news.example`);
      const trusted = report.trusted_sources.find((item) => item.identifier === site);
      expect(trusted.added_via).toBe("owner_card");
      const row = page.getByTestId(`integration-${added.id}`);
      await expect(row).toContainText(`⁨Desk ${suffix}⁩`);
      if (locale === "ar")
        await page.screenshot({ path: test.info().outputPath("capabilities-native-ar.png") });
      await row.getByRole("button", { name: text.remove, exact: true }).click();
      await expect(row).toHaveCount(0);
    } finally {
      await context.request.delete(`/api/agents/${seeded.agent}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });
