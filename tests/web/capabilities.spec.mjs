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

// A news agent whose cards ask the owner: connect Brave web search (a secure form) and
// trust a news feed's site; as the tools raise them, with no model involved.
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
from lonora_db.schema import SkillRow
from lonora_db.threads import conversation_thread
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            agent=await create_agent(session,f.owner,AgentCreate(name=data['agent'],scope_mode='flexible'))
            thread=await conversation_thread(session,f.owner,agent.id)
            subject,payload=credential_payload('brave_search',None)
            credential,_=await propose_capability(session,f.owner,'connect_credential',subject,payload,card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            domain=data['domain']
            trust,_=await propose_capability(session,f.owner,'trust_source',trust_subject('feed_domain',domain),source_payload('feed_domain',domain),card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            skill=data['skill']
            session.add(SkillRow(id=str(uuid4()),owner_id=f.owner,agent_id=agent.id,version=1,payload={'name':skill,'content':'---\\nname: '+skill+'\\ndescription: Short sourced notes.\\n---\\nUse cited evidence only.\\n','enabled':True,'manifest':{'id':skill,'version':'1.0.0','title':skill,'description':'Short sourced notes.','source':'installed','activation':{'mode':'explicit'}}}))
            print(json.dumps({'agent':agent.id,'credential':credential.id,'trust':trust.id}))
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
    connectTitle: "Connect Brave web search",
    connect: "Connect",
    connected: "Connected. Agents see only that it is configured.",
    trustTitle: "Trust this source?",
    trust: "Trust",
    trusted: "Trusted.",
    tab: "Capabilities",
    github: "All public GitHub repositories",
    remove: "Remove",
    restore: "Restore",
    search: "Web search: Ready",
    undo: "Undo",
    undone: "undone",
  },
  ar: {
    connectTitle: "ربط بحث Brave",
    connect: "ربط",
    connected: "تم الربط. لا يرى الوكلاء إلا أنه مُعدّ.",
    trustTitle: "الوثوق بهذا المصدر؟",
    trust: "ثقة",
    trusted: "صار موثوقًا.",
    tab: "القدرات",
    github: "كل المستودعات العامة على GitHub",
    remove: "إزالة",
    restore: "استعادة",
    search: "البحث على الويب: جاهز",
    undo: "تراجع",
    undone: "تم التراجع",
  },
};

for (const locale of ["en", "ar"])
  test(`${locale}: a secure credential card and a trust card, then Capabilities shows them`, async ({
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
    const secret = `brave-key-${randomUUID()}`;
    const domain = `feeds-${suffix}.analyst.example`;
    const skill = `notes-${suffix}`;
    const seeded = seedCards({ agent: `News ${suffix}`, domain, skill });
    const posted = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/api/"))
        posted.push({ url: new URL(request.url()).pathname, body: request.postData() ?? "" });
    });
    const created = [];
    try {
      await page.goto(`/app/${seeded.agent}`);
      const card = page.locator(`[data-owner-action="${seeded.credential}"]`);
      await expect(card).toHaveAttribute("data-owner-action-kind", "connect_credential");
      await expect(card.locator(".oa-kind")).toHaveText(text.connectTitle);
      const key = card.locator('input[name="secret"]');
      await expect(key).toHaveAttribute("type", "password");
      await expect(key).toHaveAttribute("dir", "ltr");
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await card.screenshot({ path: test.info().outputPath("credential-card-ar.png") });
      }
      await key.fill(secret);
      await card.getByRole("button", { name: text.connect, exact: true }).click();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card.getByRole("status")).toHaveText(text.connected);
      // The value went only to the secrets route, never to the card or the chat.
      const carrying = posted.filter((item) => item.body.includes(secret)).map((item) => item.url);
      expect(carrying).toEqual(["/api/integrations/secrets"]);
      const decision = posted.find((item) => item.url.endsWith("/decision"));
      expect(JSON.parse(decision.body).connected.resource).toBe("integration");
      created.push(JSON.parse(decision.body).connected.id);

      const trust = page.locator(`[data-owner-action="${seeded.trust}"]`);
      await expect(trust.locator(".oa-kind")).toHaveText(text.trustTitle);
      await expect(trust).toContainText(`⁨${domain}⁩`);
      await trust.getByRole("button", { name: text.trust, exact: true }).click();
      await expect(trust).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(trust.getByRole("status")).toHaveText(text.trusted);

      await page.goto("/app?settings=capabilities");
      await page.getByRole("button", { name: text.tab, exact: true }).click();
      const view = page.locator("[data-capabilities]");
      await expect(view.locator('[data-capability="web_search"]')).toHaveText(text.search);
      const site = view.locator('[data-trusted-source="feed_domain"]').filter({ hasText: domain });
      await expect(site).toBeVisible();
      const github = view.locator('[data-trusted-source="github"]');
      await expect(github).toContainText(text.github);
      if (locale === "ar")
        await view.screenshot({ path: test.info().outputPath("capabilities-ar.png") });
      await github.getByRole("button", { name: text.remove, exact: true }).click();
      await expect(github.getByRole("button", { name: text.restore, exact: true })).toBeVisible();
      await github.getByRole("button", { name: text.restore, exact: true }).click();
      await expect(github.getByRole("button", { name: text.remove, exact: true })).toBeVisible();
      // Undo a Skill its agent wrote: the line says it is undone and offers no second Undo.
      const written = view.locator(`[data-capability-skill="${skill}"]`);
      await expect(written).toContainText(`⁨${skill}⁩`);
      await written.getByRole("button", { name: text.undo, exact: true }).click();
      await expect(written).toContainText(text.undone);
      await expect(written.getByRole("button", { name: text.undo, exact: true })).toHaveCount(0);
      const catalog = await (
        await context.request.get(`/api/agents/${seeded.agent}/skills/catalog/${skill}`)
      ).json();
      expect(catalog.code).toBe("skill_version_revoked");
      await expect(page.getByText(secret)).toHaveCount(0);
    } finally {
      for (const id of created)
        await context.request.delete(`/api/integrations/${id}`, { headers });
      await context.request.delete(`/api/agents/${seeded.agent}`, { headers });
    }
  });
