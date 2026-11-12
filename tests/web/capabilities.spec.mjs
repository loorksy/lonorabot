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

// A news agent whose card asks the owner to connect Brave web search (a Secret card), as
// the tool raises it with no model involved, and a news feed's site it trusted on the
// owner's own words (no card: VISION 10.3.2).
function seedCards(data) {
  const script = `
import asyncio,json,sys
sys.path.insert(0,'tests')
from uuid import uuid4
from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate
from lonora_db.agents import create_agent
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_db.owner_actions import propose
from lonora_db.schema import SkillRow
from lonora_db.threads import conversation_thread
from lonora_db.trusted_sources import trust_source
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            agent=await create_agent(session,f.owner,AgentCreate(name=data['agent'],scope_mode='flexible'))
            thread=await conversation_thread(session,f.owner,agent.id)
            credential,_=await propose(session,f.owner,OwnerActionProposal(kind='secret',target='brave_search'),card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            await trust_source(session,f.owner,'feed_domain',data['domain'],via='owner_message',agent_id=agent.id)
            skill=data['skill']
            session.add(SkillRow(id=str(uuid4()),owner_id=f.owner,agent_id=agent.id,version=1,payload={'name':skill,'content':'---\\nname: '+skill+'\\ndescription: Short sourced notes.\\n---\\nUse cited evidence only.\\n','enabled':True,'manifest':{'id':skill,'version':'1.0.0','title':skill,'description':'Short sourced notes.','source':'installed','activation':{'mode':'explicit'}}}))
            print(json.dumps({'agent':agent.id,'thread':thread.id,'credential':credential.id}))
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
    connected: "Connected. No agent sees what you typed.",
    domains: "News domains",
    undoVersion: "Undo this version",
  },
  ar: {
    connectTitle: "ربط بحث Brave",
    connect: "ربط",
    connected: "تم الربط. لا يرى أي وكيل ما كتبته.",
    domains: "نطاقات الأخبار",
    undoVersion: "التراجع عن هذا الإصدار",
  },
};

for (const locale of ["en", "ar"])
  test(`${locale}: a Secret card and a site trusted from chat, then Capabilities shows them`, async ({
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
    const names = [];
    try {
      await page.goto(`/app/${seeded.agent}`);
      const card = page.locator(`[data-owner-action="${seeded.credential}"]`);
      await expect(card).toHaveAttribute("data-owner-action-kind", "secret");
      await expect(card.locator(".oa-kind")).toHaveText(text.connectTitle);
      const key = card.locator('input[name="API_KEY"]');
      await expect(key).toHaveAttribute("type", "password");
      await expect(key).toHaveAttribute("dir", "ltr");
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await card.screenshot({ path: test.info().outputPath("credential-card-ar.png") });
      }
      await key.fill(secret);
      const answer = page.waitForResponse((response) => response.url().endsWith("/secret"));
      await card.getByRole("button", { name: text.connect, exact: true }).click();
      const saved = await (await answer).json();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card.getByRole("status")).toHaveText(text.connected);
      // The value went only to the card's own route, never to a decision or the chat.
      const carrying = posted.filter((item) => item.body.includes(secret)).map((item) => item.url);
      expect(carrying).toEqual([`/api/owner-actions/${seeded.credential}/secret`]);
      created.push(saved.result.integration_id);
      names.push(...saved.result.saved);

      // Trusting the site raised no card: the credential card is the conversation's only one.
      const cards = await (
        await context.request.get(`/api/owner-actions?thread_id=${seeded.thread}`)
      ).json();
      expect(cards.map((item) => item.kind)).toEqual(["secret"]);

      // «التكاملات» (phase 5): the trusted news domain is in its sheet, and the skill its
      // agent wrote can be undone once from its row.
      await page.goto("/app/integrations");
      await page.getByRole("button", { name: new RegExp(text.domains) }).click();
      await expect(page.locator("dialog").getByText(domain, { exact: true })).toBeVisible();
      if (locale === "ar")
        await page.locator("dialog").screenshot({ path: test.info().outputPath("domains-ar.png") });
      await page.keyboard.press("Escape");
      const written = page.locator(".cap-skill").filter({ hasText: skill });
      await expect(written).toBeVisible();
      await written.getByRole("button", { name: text.undoVersion }).click();
      await expect(written).toHaveClass(/off/);
      await expect(written.getByRole("button", { name: text.undoVersion })).toHaveCount(0);
      const catalog = await (
        await context.request.get(`/api/agents/${seeded.agent}/skills/catalog/${skill}`)
      ).json();
      expect(catalog.code).toBe("skill_version_revoked");
      await expect(page.getByText(secret)).toHaveCount(0);
    } finally {
      for (const id of created)
        await context.request.delete(`/api/integrations/${id}`, { headers });
      const secrets = await (await context.request.get("/api/secrets")).json();
      for (const item of secrets.filter((row) => names.includes(row.name)))
        await context.request.delete(`/api/secrets/${item.id}`, { headers });
      await context.request.delete(`/api/agents/${seeded.agent}`, { headers });
    }
  });
